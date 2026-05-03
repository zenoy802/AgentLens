from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError
from app.models.connection import Connection
from app.models.label import LabelRecord, LabelSchema
from app.models.llm import LLMAnalysis
from app.models.misc import QueryHistory
from app.models.named_query import NamedQuery
from app.models.view_config import ViewConfig
from app.schemas.common import Pagination, WarningRead
from app.schemas.datetime import ensure_utc
from app.schemas.query import (
    NamedQueryCreate,
    NamedQueryListResponse,
    NamedQueryPromote,
    NamedQueryRead,
    NamedQueryUpdate,
)
from app.schemas.render import FieldRender
from app.services.query_executor import ExecutorResult, ExecutorService
from app.services.render_suggestion_service import suggest
from app.services.row_identity_service import compute

_TEMPORARY_QUERY_TTL_DAYS = 7
_NAMED_QUERY_TTL_DAYS = 90


@dataclass(slots=True)
class ExecutionOutcome:
    execution_result: ExecutorResult
    suggested_field_renders: dict[str, FieldRender]
    row_identities: list[str]
    executed_at: datetime
    warnings: list[WarningRead]


class QueryService:
    def __init__(self, session: Session, executor_service: ExecutorService) -> None:
        self.session = session
        self._executor_service = executor_service

    def create_temporary_query(self, connection_id: int, sql: str) -> NamedQuery:
        self._get_connection_or_raise(connection_id)
        query = NamedQuery(
            connection_id=connection_id,
            name=None,
            sql_text=sql,
            is_named=False,
            expires_at=_utcnow() + timedelta(days=_TEMPORARY_QUERY_TTL_DAYS),
        )
        query.view_config = ViewConfig(field_renders="{}", table_config="{}")
        query.label_schema = LabelSchema(fields="[]")
        self.session.add(query)
        self.session.commit()
        self.session.refresh(query)
        return query

    def create_named_query(self, payload: NamedQueryCreate) -> NamedQuery:
        self._get_connection_or_raise(payload.connection_id)
        query = NamedQuery(
            connection_id=payload.connection_id,
            name=payload.name,
            description=payload.description,
            sql_text=payload.sql_text,
            is_named=True,
            expires_at=self._resolve_named_expiration(payload),
        )
        query.view_config = ViewConfig(field_renders="{}", table_config="{}")
        query.label_schema = LabelSchema(fields="[]")
        self.session.add(query)
        self._commit_or_raise_name_conflict()
        self.session.refresh(query)
        return query

    def execute_and_record(
        self,
        query: NamedQuery,
        *,
        timeout: int,
        row_limit: int,
    ) -> ExecutionOutcome:
        connection = self._get_connection_or_raise(query.connection_id)
        view_config = self._get_or_create_view_config(query)
        query_id = query.id
        connection_id = query.connection_id
        sql_text = query.sql_text

        try:
            execution_result = self._executor_service.execute(
                connection,
                sql_text,
                timeout=timeout,
                row_limit=row_limit,
            )
            warnings: list[WarningRead] = []
            self._append_row_identity_config_warnings(
                view_config,
                execution_result,
                warnings,
            )
            row_identities = [
                compute(row, view_config.row_identity_column) for row in execution_result.rows
            ]
            self._append_duplicate_row_identity_warning(row_identities, warnings)
            suggested_field_renders = suggest(
                execution_result.columns,
                self.session,
                warnings=warnings,
            )
        except Exception as exc:
            self.session.rollback()
            self._record_query_history(
                query_id=query_id,
                connection_id=connection_id,
                sql_text=sql_text,
                status="failed",
                error_message=_error_message(exc),
            )
            self.session.commit()
            raise

        executed_at = _utcnow()
        query.last_executed_at = executed_at
        self._record_query_history(
            query_id=query.id,
            connection_id=query.connection_id,
            sql_text=query.sql_text,
            row_count=len(execution_result.rows),
            duration_ms=execution_result.duration_ms,
            status="success",
            executed_at=executed_at,
        )
        self.session.commit()
        self.session.refresh(query)
        return ExecutionOutcome(
            execution_result=execution_result,
            suggested_field_renders=suggested_field_renders,
            row_identities=row_identities,
            executed_at=executed_at,
            warnings=warnings,
        )

    def execute_readonly(
        self,
        query: NamedQuery,
        *,
        timeout: int,
        row_limit: int,
    ) -> ExecutionOutcome:
        connection = self._get_connection_or_raise(query.connection_id)
        view_config = self._get_or_create_view_config(query)

        try:
            execution_result = self._executor_service.execute(
                connection,
                query.sql_text,
                timeout=timeout,
                row_limit=row_limit,
            )
            warnings: list[WarningRead] = []
            self._append_row_identity_config_warnings(
                view_config,
                execution_result,
                warnings,
            )
            row_identities = [
                compute(row, view_config.row_identity_column) for row in execution_result.rows
            ]
            self._append_duplicate_row_identity_warning(row_identities, warnings)
            suggested_field_renders = suggest(
                execution_result.columns,
                self.session,
                warnings=warnings,
            )
        except Exception:
            self.session.rollback()
            raise

        return ExecutionOutcome(
            execution_result=execution_result,
            suggested_field_renders=suggested_field_renders,
            row_identities=row_identities,
            executed_at=_utcnow(),
            warnings=warnings,
        )

    def get(self, query_id: int) -> NamedQuery:
        query = self.session.get(NamedQuery, query_id)
        if query is None:
            raise NotFoundError(
                code="NOT_FOUND",
                message="Named query not found.",
                detail={"query_id": query_id},
            )
        return query

    def list_queries(
        self,
        *,
        connection_id: int | None = None,
        is_named: bool | None = None,
        search: str | None = None,
        include_expired: bool = False,
        order_by: str = "created_at",
        page: int,
        page_size: int,
    ) -> NamedQueryListResponse:
        filters = []
        if connection_id is not None:
            filters.append(NamedQuery.connection_id == connection_id)
        if is_named is not None:
            filters.append(NamedQuery.is_named.is_(is_named))
        if search:
            pattern = f"%{search}%"
            filters.append(
                or_(
                    NamedQuery.name.ilike(pattern),
                    NamedQuery.description.ilike(pattern),
                    NamedQuery.sql_text.ilike(pattern),
                )
            )
        if not include_expired:
            now = _utcnow()
            filters.append(or_(NamedQuery.expires_at.is_(None), NamedQuery.expires_at >= now))

        count_stmt: Select[tuple[int]] = (
            select(func.count()).select_from(NamedQuery).where(*filters)
        )
        total_records = self.session.scalar(count_stmt) or 0
        total_pages = max((total_records + page_size - 1) // page_size, 1)

        label_counts = (
            select(
                LabelRecord.query_id.label("query_id"),
                func.count(LabelRecord.id).label("label_record_count"),
            )
            .group_by(LabelRecord.query_id)
            .subquery()
        )
        analysis_counts = (
            select(
                LLMAnalysis.query_id.label("query_id"),
                func.count(LLMAnalysis.id).label("llm_analysis_count"),
            )
            .group_by(LLMAnalysis.query_id)
            .subquery()
        )
        label_record_count = func.coalesce(label_counts.c.label_record_count, 0)
        llm_analysis_count = func.coalesce(analysis_counts.c.llm_analysis_count, 0)

        stmt: Select[tuple[NamedQuery, str, int, int]] = (
            select(
                NamedQuery,
                Connection.name,
                label_record_count,
                llm_analysis_count,
            )
            .join(Connection, NamedQuery.connection_id == Connection.id)
            .outerjoin(label_counts, label_counts.c.query_id == NamedQuery.id)
            .outerjoin(analysis_counts, analysis_counts.c.query_id == NamedQuery.id)
            .where(*filters)
        )
        if order_by == "last_executed_at":
            stmt = stmt.order_by(NamedQuery.last_executed_at.desc(), NamedQuery.id.desc())
        else:
            stmt = stmt.order_by(NamedQuery.created_at.desc(), NamedQuery.id.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = self.session.execute(stmt).all()
        return NamedQueryListResponse(
            items=[
                self.build_read(
                    query,
                    connection_name=connection_name,
                    label_record_count=int(label_count),
                    llm_analysis_count=int(analysis_count),
                )
                for query, connection_name, label_count, analysis_count in rows
            ],
            pagination=Pagination(
                page=page,
                page_size=page_size,
                total=total_records,
                total_pages=total_pages,
            ),
        )

    def build_read(
        self,
        query: NamedQuery,
        *,
        connection_name: str | None = None,
        label_record_count: int | None = None,
        llm_analysis_count: int | None = None,
    ) -> NamedQueryRead:
        resolved_connection_name = connection_name
        if resolved_connection_name is None:
            resolved_connection_name = self._get_connection_or_raise(query.connection_id).name

        resolved_label_record_count = label_record_count
        if resolved_label_record_count is None:
            resolved_label_record_count = (
                self.session.scalar(
                    select(func.count(LabelRecord.id)).where(LabelRecord.query_id == query.id)
                )
                or 0
            )

        resolved_llm_analysis_count = llm_analysis_count
        if resolved_llm_analysis_count is None:
            resolved_llm_analysis_count = (
                self.session.scalar(
                    select(func.count(LLMAnalysis.id)).where(LLMAnalysis.query_id == query.id)
                )
                or 0
            )

        return NamedQueryRead(
            id=query.id,
            connection_id=query.connection_id,
            connection_name=resolved_connection_name,
            name=query.name,
            description=query.description,
            sql_text=query.sql_text,
            is_named=query.is_named,
            created_at=query.created_at,
            updated_at=query.updated_at,
            last_executed_at=query.last_executed_at,
            expires_at=query.expires_at,
            label_record_count=resolved_label_record_count,
            llm_analysis_count=resolved_llm_analysis_count,
        )

    def update(self, query_id: int, payload: NamedQueryUpdate) -> NamedQuery:
        query = self.get(query_id)
        updates = payload.model_dump(exclude_unset=True)
        if "expires_at" in updates:
            updates["expires_at"] = _to_storage_datetime(updates["expires_at"])
        if "name" in updates and not query.is_named:
            raise ConflictError(
                code="QUERY_TEMPORARY_NAME_UPDATE_FORBIDDEN",
                message="Temporary queries can only be named through promote.",
                detail={"query_id": query.id},
            )

        for field_name in ("name", "description", "expires_at"):
            if field_name in updates:
                setattr(query, field_name, updates[field_name])

        self._commit_or_raise_name_conflict()
        self.session.refresh(query)
        return query

    def delete(self, query_id: int) -> None:
        query = self.get(query_id)
        self.session.delete(query)
        self.session.commit()

    def promote(self, query_id: int, payload: NamedQueryPromote) -> NamedQuery:
        query = self.get(query_id)
        if query.is_named:
            raise ConflictError(
                code="QUERY_ALREADY_NAMED",
                message="Only temporary queries can be promoted.",
                detail={"query_id": query.id},
            )
        if self._query_name_exists(
            connection_id=query.connection_id,
            name=payload.name,
            exclude_query_id=query.id,
        ):
            raise ConflictError(
                code="QUERY_NAME_CONFLICT",
                message="Named query name already exists for this connection.",
                detail={"connection_id": query.connection_id, "name": payload.name},
            )

        query.name = payload.name
        query.description = payload.description
        query.is_named = True
        query.expires_at = self._resolve_promoted_expiration(payload)
        self._commit_or_raise_name_conflict()
        self.session.refresh(query)
        return query

    def _get_connection_or_raise(self, connection_id: int) -> Connection:
        connection = self.session.get(Connection, connection_id)
        if connection is None:
            raise NotFoundError(
                code="NOT_FOUND",
                message="Connection not found.",
                detail={"connection_id": connection_id},
            )
        return connection

    def _get_or_create_view_config(self, query: NamedQuery) -> ViewConfig:
        view_config = query.view_config
        if view_config is not None:
            return view_config

        view_config = ViewConfig(query_id=query.id, field_renders="{}", table_config="{}")
        self.session.add(view_config)
        self.session.flush()
        return view_config

    def _record_query_history(
        self,
        *,
        query_id: int | None,
        connection_id: int,
        sql_text: str,
        status: str,
        row_count: int | None = None,
        duration_ms: int | None = None,
        error_message: str | None = None,
        executed_at: datetime | None = None,
    ) -> None:
        self.session.add(
            QueryHistory(
                connection_id=connection_id,
                query_id=query_id,
                sql_text=sql_text,
                row_count=row_count,
                duration_ms=duration_ms,
                status=status,
                error_message=error_message,
                executed_at=executed_at or _utcnow(),
            )
        )

    @staticmethod
    def _append_row_identity_config_warnings(
        view_config: ViewConfig,
        execution_result: ExecutorResult,
        warnings: list[WarningRead],
    ) -> None:
        identity_column = view_config.row_identity_column
        if not identity_column:
            return

        column_names = {column.name for column in execution_result.columns}
        if identity_column not in column_names:
            warnings.append(
                WarningRead(
                    code="ROW_IDENTITY_COLUMN_MISSING",
                    message=(
                        f"Configured row_identity_column '{identity_column}' was not returned; "
                        "row hashes were used instead."
                    ),
                    detail={"row_identity_column": identity_column},
                )
            )
            return

        if any(row.get(identity_column) is None for row in execution_result.rows):
            warnings.append(
                WarningRead(
                    code="ROW_IDENTITY_COLUMN_NULL",
                    message=(
                        f"Configured row_identity_column '{identity_column}' contains null "
                        "values; affected rows used row hashes instead."
                    ),
                    detail={"row_identity_column": identity_column},
                )
            )

    @staticmethod
    def _append_duplicate_row_identity_warning(
        row_identities: list[str],
        warnings: list[WarningRead],
    ) -> None:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for row_identity in row_identities:
            if row_identity in seen:
                duplicates.add(row_identity)
            seen.add(row_identity)
        if duplicates:
            warnings.append(
                WarningRead(
                    code="ROW_IDENTITY_DUPLICATE",
                    message=(
                        "Duplicate row_identity values detected; labels may apply to multiple rows."
                    ),
                    detail={"duplicate_count": len(duplicates)},
                )
            )

    def _query_name_exists(
        self,
        *,
        connection_id: int,
        name: str,
        exclude_query_id: int | None = None,
    ) -> bool:
        stmt: Select[tuple[NamedQuery]] = select(NamedQuery).where(
            NamedQuery.connection_id == connection_id,
            NamedQuery.name == name,
        )
        if exclude_query_id is not None:
            stmt = stmt.where(NamedQuery.id != exclude_query_id)
        return self.session.scalar(stmt) is not None

    def _commit_or_raise_name_conflict(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            if _is_named_query_name_conflict(exc):
                raise ConflictError(
                    code="QUERY_NAME_CONFLICT",
                    message="Named query name already exists for this connection.",
                ) from exc
            raise ConflictError(
                code="DB_INTEGRITY_CONFLICT",
                message="Database integrity constraint failed.",
            ) from exc

    @staticmethod
    def _resolve_named_expiration(payload: NamedQueryCreate) -> datetime | None:
        if "expires_at" in payload.model_fields_set:
            return _to_storage_datetime(payload.expires_at)
        return _utcnow() + timedelta(days=_NAMED_QUERY_TTL_DAYS)

    @staticmethod
    def _resolve_promoted_expiration(payload: NamedQueryPromote) -> datetime | None:
        if "expires_at" in payload.model_fields_set:
            return _to_storage_datetime(payload.expires_at)
        return _utcnow() + timedelta(days=_NAMED_QUERY_TTL_DAYS)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _to_storage_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return ensure_utc(value).replace(tzinfo=None)


def _error_message(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return exc.message
    return str(exc)


def _is_named_query_name_conflict(exc: IntegrityError) -> bool:
    message = str(exc.orig)
    return "named_queries.connection_id" in message and "named_queries.name" in message
