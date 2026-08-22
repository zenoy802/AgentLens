from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from loguru import logger
from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import (
    ConflictError,
    IdempotencyConflictError,
    NotFoundError,
    SnapshotRowError,
    ValidationError,
)
from app.models.named_query import NamedQuery
from app.models.trace_contract import TraceContract as TraceContractModel
from app.schemas.common import CursorPagination
from app.schemas.datetime import ensure_utc
from app.schemas.trace_contract import (
    TraceContract,
    TraceContractCreate,
    TraceContractListResponse,
    TraceContractRead,
    TraceContractValidationResult,
    TraceValidationIssue,
    trace_contract_adapter,
)
from app.services.trace_contract import (
    canonical_json_bytes,
    compile_contract,
    normalize_source_rows,
)

_MAX_VALIDATION_ERRORS = 20
_MAX_CANONICAL_PREVIEW = 5
_MAX_IDEMPOTENCY_KEY_LENGTH = 200
_MAX_CURSOR_LENGTH = 4096


class TraceContractService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        payload: TraceContractCreate,
        *,
        idempotency_key: str | None = None,
    ) -> TraceContractModel:
        self._get_query_or_raise(payload.named_query_id)
        compiled = compile_contract(payload.definition)
        definition_payload = compiled.definition.model_dump(mode="json")
        request_sha256 = _sha256(canonical_json_bytes(payload.model_dump(mode="json")))
        normalized_key = _normalize_idempotency_key(idempotency_key)
        if normalized_key is not None:
            existing = self.session.scalar(
                select(TraceContractModel).where(
                    TraceContractModel.idempotency_key == normalized_key
                )
            )
            if existing is not None:
                if existing.request_sha256 != request_sha256:
                    raise IdempotencyConflictError(detail={"resource": "trace_contract"})
                return existing

        version = (
            self.session.scalar(
                select(func.max(TraceContractModel.version)).where(
                    TraceContractModel.named_query_id == payload.named_query_id,
                    TraceContractModel.name == payload.name,
                )
            )
            or 0
        ) + 1
        now = datetime.now(UTC)
        contract = TraceContractModel(
            id=str(uuid4()),
            name=payload.name,
            named_query_id=payload.named_query_id,
            version=version,
            definition=definition_payload,
            definition_sha256=_sha256(canonical_json_bytes(definition_payload)),
            idempotency_key=normalized_key,
            request_sha256=request_sha256,
            created_at=now,
            updated_at=now,
        )
        self.session.add(contract)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            if normalized_key is not None:
                existing = self.session.scalar(
                    select(TraceContractModel).where(
                        TraceContractModel.idempotency_key == normalized_key
                    )
                )
                if existing is not None:
                    if existing.request_sha256 == request_sha256:
                        return existing
                    raise IdempotencyConflictError(detail={"resource": "trace_contract"}) from exc
            raise ConflictError(
                code="TRACE_CONTRACT_CREATE_CONFLICT",
                message="Trace contract version could not be allocated; retry the request.",
            ) from exc
        logger.info(
            "Trace contract created: contract_id={} query_id={} version={} definition_hash={}",
            contract.id,
            contract.named_query_id,
            contract.version,
            contract.definition_sha256[:12],
        )
        return contract

    def get(self, contract_id: str) -> TraceContractModel:
        contract = self.session.get(TraceContractModel, contract_id)
        if contract is None:
            raise NotFoundError(
                code="TRACE_CONTRACT_NOT_FOUND",
                message="Trace contract not found.",
                detail={"trace_contract_id": contract_id},
            )
        return contract

    def list(
        self,
        *,
        named_query_id: int | None,
        include_archived: bool,
        cursor: str | None,
        limit: int,
    ) -> TraceContractListResponse:
        filters: list[Any] = []
        if named_query_id is not None:
            filters.append(TraceContractModel.named_query_id == named_query_id)
        if not include_archived:
            filters.append(TraceContractModel.archived_at.is_(None))
        cursor_value = _decode_cursor(cursor)
        if cursor_value is not None:
            created_at, resource_id = cursor_value
            filters.append(
                or_(
                    TraceContractModel.created_at < created_at,
                    (
                        (TraceContractModel.created_at == created_at)
                        & (TraceContractModel.id < resource_id)
                    ),
                )
            )
        statement: Select[tuple[TraceContractModel]] = (
            select(TraceContractModel)
            .where(*filters)
            .order_by(TraceContractModel.created_at.desc(), TraceContractModel.id.desc())
            .limit(limit + 1)
        )
        rows = list(self.session.scalars(statement))
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = _encode_cursor(items[-1].created_at, items[-1].id) if has_more else None
        return TraceContractListResponse(
            items=[self.to_read(contract) for contract in items],
            pagination=CursorPagination(limit=limit, next_cursor=next_cursor),
        )

    def to_read(self, contract: TraceContractModel) -> TraceContractRead:
        definition = trace_contract_adapter.validate_python(contract.definition)
        query = self.session.get(NamedQuery, contract.named_query_id)
        return TraceContractRead(
            id=contract.id,
            name=contract.name,
            named_query_id=contract.named_query_id,
            named_query_name=None if query is None else query.name,
            version=contract.version,
            definition=definition,
            definition_sha256=contract.definition_sha256,
            created_at=ensure_utc(contract.created_at),
            updated_at=ensure_utc(contract.updated_at),
            archived_at=(
                None if contract.archived_at is None else ensure_utc(contract.archived_at)
            ),
        )

    def validate_rows(
        self,
        definition: TraceContract,
        rows: Sequence[Mapping[str, object]],
        *,
        query_id: int,
        row_identities: Sequence[str],
    ) -> TraceContractValidationResult:
        compiled = compile_contract(definition)
        if not rows:
            return TraceContractValidationResult(
                valid=False,
                source_row_count=0,
                valid_run_count=0,
                error_count=1,
                errors=[TraceValidationIssue(code="SNAPSHOT_ROW_INVALID", reason="sample_empty")],
                diagnostics=[],
                pairing_key_field_coverage=0.0,
                canonical_preview=[],
            )
        try:
            batch = normalize_source_rows(
                rows,
                compiled,
                query_id=query_id,
                row_identities=row_identities,
            )
        except SnapshotRowError as exc:
            issue = _validation_issue(exc)
            return TraceContractValidationResult(
                valid=False,
                source_row_count=len(rows),
                valid_run_count=0,
                error_count=1,
                errors=[issue],
                diagnostics=[],
                pairing_key_field_coverage=0.0,
                canonical_preview=[],
            )
        diagnostics = batch.diagnostics[:_MAX_VALIDATION_ERRORS]
        return TraceContractValidationResult(
            valid=True,
            source_row_count=batch.source_row_count,
            valid_run_count=batch.valid_run_count,
            error_count=0,
            errors=[],
            diagnostics=diagnostics,
            pairing_key_field_coverage=batch.pairing_key_field_coverage,
            canonical_preview=batch.runs[:_MAX_CANONICAL_PREVIEW],
        )

    def _get_query_or_raise(self, query_id: int) -> NamedQuery:
        query = self.session.get(NamedQuery, query_id)
        if query is None:
            raise NotFoundError(
                code="QUERY_NOT_FOUND",
                message="Named query not found.",
                detail={"query_id": query_id},
            )
        return query


def _validation_issue(exc: SnapshotRowError) -> TraceValidationIssue:
    detail = exc.detail or {}
    raw_path = detail.get("path")
    raw_index = detail.get("source_row_index")
    return TraceValidationIssue(
        code=exc.code,
        reason=str(detail.get("reason", "row_invalid")),
        path=raw_path if isinstance(raw_path, str) else None,
        source_row_index=raw_index if isinstance(raw_index, int) else None,
    )


def _normalize_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > _MAX_IDEMPOTENCY_KEY_LENGTH:
        raise ValidationError(
            code="IDEMPOTENCY_KEY_INVALID",
            message="Idempotency key must be between 1 and 200 characters.",
        )
    return normalized


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _encode_cursor(created_at: datetime, resource_id: str) -> str:
    payload = canonical_json_bytes(
        {"created_at": ensure_utc(created_at).isoformat(), "id": resource_id}
    )
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if cursor is None:
        return None
    if len(cursor) > _MAX_CURSOR_LENGTH:
        raise ValidationError(code="CURSOR_INVALID", message="Pagination cursor is invalid.")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        resource_id = str(payload["id"])
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(
            code="CURSOR_INVALID",
            message="Pagination cursor is invalid.",
        ) from exc
    return ensure_utc(created_at), resource_id
