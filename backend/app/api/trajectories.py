from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.execute import get_query_service
from app.core.errors import AppError
from app.schemas.common import WarningRead
from app.schemas.trajectory import TrajectoryAggregateRequest, TrajectoryAggregateResponse
from app.schemas.view_config import TrajectoryConfig
from app.services.query_service import ExecutionOutcome, QueryService
from app.services.trajectory_service import aggregate
from app.services.view_config_service import view_config_service

router = APIRouter(prefix="/queries/{query_id}", tags=["trajectories"])

_PRIMARY_ROW_IDENTITY_KEY = "_row_identity"
_FALLBACK_ROW_IDENTITY_KEY = "_agent_lens_row_identity"


@router.post("/trajectories", response_model=TrajectoryAggregateResponse)
def aggregate_query_trajectories(
    query_id: int,
    service: Annotated[QueryService, Depends(get_query_service)],
    payload: TrajectoryAggregateRequest | None = None,
) -> TrajectoryAggregateResponse:
    active_payload = payload or TrajectoryAggregateRequest()
    query = service.get(query_id)
    trajectory_config = _resolve_trajectory_config(query_id, service, active_payload)
    connection = query.connection
    outcome = service.execute_readonly(
        query,
        timeout=(
            active_payload.timeout
            if active_payload.timeout is not None
            else connection.default_timeout
        ),
        row_limit=(
            active_payload.row_limit
            if active_payload.row_limit is not None
            else connection.default_row_limit
        ),
    )
    row_identity_key = _select_row_identity_key(outcome.execution_result.rows)
    trajectories, aggregate_warnings = aggregate(
        outcome.execution_result.rows,
        trajectory_config,
        row_identity_key=row_identity_key,
        row_identities=outcome.row_identities,
    )
    warnings = _build_execution_warnings(outcome, row_identity_key) + aggregate_warnings
    return TrajectoryAggregateResponse(trajectories=trajectories, warnings=warnings)


def _resolve_trajectory_config(
    query_id: int,
    service: QueryService,
    payload: TrajectoryAggregateRequest,
) -> TrajectoryConfig:
    if payload.use_saved_config:
        view_config = view_config_service.get(service.session, query_id)
        if view_config.trajectory_config is None:
            raise AppError(
                code="TRAJECTORY_CONFIG_MISSING",
                message="Saved view_config.trajectory_config is required.",
                http_status=status.HTTP_400_BAD_REQUEST,
                detail={"query_id": query_id},
            )
        return view_config.trajectory_config

    if payload.trajectory_config is None:
        raise AppError(
            code="TRAJECTORY_CONFIG_REQUIRED",
            message="trajectory_config is required when use_saved_config=false.",
            http_status=status.HTTP_400_BAD_REQUEST,
            detail={"query_id": query_id},
        )
    return payload.trajectory_config


def _build_execution_warnings(
    outcome: ExecutionOutcome,
    row_identity_key: str,
) -> list[WarningRead]:
    warnings = list(outcome.warnings)
    if row_identity_key != _PRIMARY_ROW_IDENTITY_KEY:
        warnings.append(
            WarningRead(
                code="ROW_IDENTITY_KEY_COLLISION",
                message=(
                    "Result rows already contain _row_identity; AgentLens row identity was "
                    f"returned as {row_identity_key}."
                ),
                detail={
                    "requested_key": _PRIMARY_ROW_IDENTITY_KEY,
                    "fallback_key": row_identity_key,
                },
            )
        )

    if outcome.execution_result.truncated:
        warnings.append(
            WarningRead(
                code="RESULT_TRUNCATED",
                message="Result was truncated because it exceeded the row limit.",
            )
        )
    return warnings


def _select_row_identity_key(rows: list[dict[str, object]]) -> str:
    if not any(_PRIMARY_ROW_IDENTITY_KEY in row for row in rows):
        return _PRIMARY_ROW_IDENTITY_KEY
    if not any(_FALLBACK_ROW_IDENTITY_KEY in row for row in rows):
        return _FALLBACK_ROW_IDENTITY_KEY

    used_fallback_suffixes = {
        key for row in rows for key in row if key.startswith(f"{_FALLBACK_ROW_IDENTITY_KEY}_")
    }
    suffix = 2
    while True:
        candidate = f"{_FALLBACK_ROW_IDENTITY_KEY}_{suffix}"
        if candidate not in used_fallback_suffixes:
            return candidate
        suffix += 1
