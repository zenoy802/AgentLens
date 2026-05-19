from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.executor_registry import get_executor_service
from app.db.session import get_db_session
from app.models.named_query import NamedQuery
from app.schemas.common import WarningRead
from app.schemas.execution import (
    ColumnRead,
    ExecuteRequest,
    ExecutionInfo,
    ExecutionResult,
)
from app.services.query_executor import ExecutionProgressEvent, ExecutorService
from app.services.query_service import ExecutionOutcome, QueryService

router = APIRouter(prefix="", tags=["execute"])

_PRIMARY_ROW_IDENTITY_KEY = "_row_identity"
_FALLBACK_ROW_IDENTITY_KEY = "_agent_lens_row_identity"


def get_query_service(
    session: Annotated[Session, Depends(get_db_session)],
    executor_service: Annotated[ExecutorService, Depends(get_executor_service)],
) -> QueryService:
    return QueryService(session, executor_service)


@router.post(
    "/execute",
    response_model=ExecutionResult,
)
def execute_sql(
    payload: ExecuteRequest,
    service: Annotated[QueryService, Depends(get_query_service)],
) -> ExecutionResult:
    if not payload.save_as_temporary:
        raise AppError(
            code="QUERY_UNSUPPORTED_EXECUTION_MODE",
            message="Only save_as_temporary=true is supported.",
            http_status=status.HTTP_400_BAD_REQUEST,
        )

    query = service.create_temporary_query(payload.connection_id, payload.sql)
    timeout, row_limit = _resolve_execution_limits(
        query,
        timeout=payload.timeout,
        row_limit=payload.row_limit,
    )
    try:
        outcome = service.execute_and_record(query, timeout=timeout, row_limit=row_limit)
    except Exception:
        try:
            service.delete(query.id)
        except Exception as cleanup_exc:
            logger.warning(
                "Failed to clean up failed temporary query {}: {}",
                query.id,
                cleanup_exc,
            )
        raise
    return build_execution_result_response(query=query, outcome=outcome, is_temporary=True)


@router.post("/execute/stream")
def execute_sql_stream(
    payload: ExecuteRequest,
    service: Annotated[QueryService, Depends(get_query_service)],
) -> StreamingResponse:
    if not payload.save_as_temporary:
        raise AppError(
            code="QUERY_UNSUPPORTED_EXECUTION_MODE",
            message="Only save_as_temporary=true is supported.",
            http_status=status.HTTP_400_BAD_REQUEST,
        )

    def stream_events() -> Iterator[str]:
        query: NamedQuery | None = None
        try:
            query = service.create_temporary_query(payload.connection_id, payload.sql)
            timeout, row_limit = _resolve_execution_limits(
                query,
                timeout=payload.timeout,
                row_limit=payload.row_limit,
            )
            yield from stream_query_execution_events(
                query=query,
                service=service,
                timeout=timeout,
                row_limit=row_limit,
                is_temporary=True,
            )
        except Exception as exc:
            if query is not None:
                try:
                    service.delete(query.id)
                except Exception as cleanup_exc:
                    logger.warning(
                        "Failed to clean up failed temporary query {}: {}",
                        query.id,
                        cleanup_exc,
                    )
            yield _sse_event("error", _build_stream_error_payload(exc))

    return StreamingResponse(stream_events(), media_type="text/event-stream")


def stream_query_execution_events(
    *,
    query: NamedQuery,
    service: QueryService,
    timeout: int,
    row_limit: int,
    is_temporary: bool,
) -> Iterator[str]:
    for item in service.execute_and_record_stream(query, timeout=timeout, row_limit=row_limit):
        if isinstance(item, ExecutionProgressEvent):
            yield _sse_event(
                item.kind,
                {"odps_logview_url": item.odps_logview_url},
            )
        else:
            yield _sse_event(
                "result",
                build_execution_result_response(
                    query=query,
                    outcome=item,
                    is_temporary=is_temporary,
                ),
            )


def build_execution_result_response(
    *,
    query: NamedQuery,
    outcome: ExecutionOutcome,
    is_temporary: bool,
) -> ExecutionResult:
    execution_result = outcome.execution_result
    warnings = list(outcome.warnings)
    identity_key = _select_row_identity_key(execution_result.rows)
    if identity_key != _PRIMARY_ROW_IDENTITY_KEY:
        warnings.append(
            WarningRead(
                code="ROW_IDENTITY_KEY_COLLISION",
                message=(
                    "Result rows already contain _row_identity; AgentLens row identity was "
                    f"returned as {identity_key}."
                ),
                detail={
                    "requested_key": _PRIMARY_ROW_IDENTITY_KEY,
                    "fallback_key": identity_key,
                },
            )
        )

    if execution_result.truncated:
        warnings.append(
            WarningRead(
                code="RESULT_TRUNCATED",
                message="Result was truncated because it exceeded the row limit.",
            )
        )

    rows = [
        {**row, identity_key: row_identity}
        for row, row_identity in zip(
            execution_result.rows,
            outcome.row_identities,
            strict=True,
        )
    ]
    columns = [
        ColumnRead(
            name=column.name,
            sql_type=column.sql_type,
            inferred_type=column.inferred_type,
        )
        for column in execution_result.columns
    ]
    return ExecutionResult(
        query_id=query.id,
        is_temporary=is_temporary,
        execution=ExecutionInfo(
            executed_at=outcome.executed_at,
            duration_ms=execution_result.duration_ms,
            row_count=len(execution_result.rows),
            truncated=execution_result.truncated,
        ),
        columns=columns,
        rows=rows,
        suggested_field_renders=outcome.suggested_field_renders,
        suggested_trajectory_config=outcome.suggested_trajectory_config,
        warnings=warnings,
    )


def _resolve_execution_limits(
    query: NamedQuery,
    *,
    timeout: int | None,
    row_limit: int | None,
) -> tuple[int, int]:
    connection = query.connection
    return (
        timeout if timeout is not None else connection.default_timeout,
        row_limit if row_limit is not None else connection.default_row_limit,
    )


def _select_row_identity_key(rows: list[dict[str, object]]) -> str:
    used_keys = {key for row in rows for key in row}
    if _PRIMARY_ROW_IDENTITY_KEY not in used_keys:
        return _PRIMARY_ROW_IDENTITY_KEY
    if _FALLBACK_ROW_IDENTITY_KEY not in used_keys:
        return _FALLBACK_ROW_IDENTITY_KEY

    suffix = 2
    while True:
        candidate = f"{_FALLBACK_ROW_IDENTITY_KEY}_{suffix}"
        if candidate not in used_keys:
            return candidate
        suffix += 1


def _sse_event(event_name: str, payload: object) -> str:
    encoded_payload = json.dumps(jsonable_encoder(payload), ensure_ascii=False)
    return f"event: {event_name}\ndata: {encoded_payload}\n\n"


def _build_stream_error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, AppError):
        return {
            "error": {
                "code": exc.code,
                "message": exc.message,
                "detail": exc.detail,
            }
        }
    logger.exception("Unhandled streaming execution exception: {}", exc)
    return {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "Internal server error.",
            "detail": None,
        }
    }
