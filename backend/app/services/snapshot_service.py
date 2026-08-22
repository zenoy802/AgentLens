from __future__ import annotations

import base64
import hashlib
import heapq
import json
import shutil
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn, Protocol, cast
from uuid import uuid4

from loguru import logger
from sqlalchemy import Select, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.artifact_store import ArtifactInfo, ArtifactStore
from app.core.errors import (
    AppError,
    ArtifactCorruptedError,
    ArtifactPathError,
    ConflictError,
    IdempotencyConflictError,
    NotFoundError,
    SnapshotRowError,
    SnapshotStateError,
    ValidationError,
)
from app.core.executor_registry import get_executor_service
from app.core.logging import sanitize_exception_message
from app.models.connection import Connection
from app.models.named_query import NamedQuery
from app.models.trace_contract import RunSnapshot
from app.models.trace_contract import TraceContract as TraceContractModel
from app.schemas.common import CursorPagination
from app.schemas.datetime import ensure_utc
from app.schemas.run_snapshot import (
    RunSnapshotCreate,
    RunSnapshotListResponse,
    RunSnapshotManifest,
    RunSnapshotRead,
    RunSnapshotRowsResponse,
    RunSnapshotStatusRead,
    SnapshotBuildPolicy,
    SnapshotContractManifest,
    SnapshotErrorInfo,
    SnapshotQueryManifest,
    SnapshotStatus,
)
from app.schemas.trace_contract import CanonicalRunRow, RunRowsContract
from app.services.fingerprint_service import compute_sql_fingerprint
from app.services.query_executor import ExecutorService
from app.services.query_service import QueryService, ReadonlyQueryStream
from app.services.trace_contract import (
    CompiledTraceContract,
    aggregate_event_rows,
    canonical_json_bytes,
    compile_contract,
    extract_path,
    normalize_run_row,
    project_source_row,
)
from app.services.trace_contract_service import TraceContractService

_SNAPSHOT_SCHEMA_VERSION = "run-snapshot/v1"
_SNAPSHOT_PATH_PREFIX = "snapshots"
_RUN_CHUNK_MAX_BYTES = 16 * 1024 * 1024
_EVENT_CHUNK_MAX_BYTES = 16 * 1024 * 1024
_QUERY_BATCH_SIZE = 500
_MAX_IDEMPOTENCY_KEY_LENGTH = 200
_MAX_CURSOR_LENGTH = 4096


@dataclass(frozen=True, slots=True)
class SnapshotCreateResult:
    snapshot: RunSnapshot
    created: bool


class _HashWriter(Protocol):
    def update(self, data: bytes) -> None: ...


class SnapshotService:
    def __init__(
        self,
        session: Session,
        *,
        executor_service: ExecutorService | None = None,
        artifact_store: ArtifactStore | None = None,
    ) -> None:
        self.session = session
        self._executor_service = executor_service or get_executor_service()
        self._artifact_store = artifact_store or ArtifactStore()

    def create(
        self,
        payload: RunSnapshotCreate,
        *,
        idempotency_key: str | None = None,
    ) -> SnapshotCreateResult:
        query, contract = self._validate_create_references(payload)
        request_payload = payload.model_dump(mode="json")
        request_sha256 = _sha256(canonical_json_bytes(request_payload))
        normalized_key = _normalize_idempotency_key(idempotency_key)
        if normalized_key is not None:
            existing = self.session.scalar(
                select(RunSnapshot).where(RunSnapshot.idempotency_key == normalized_key)
            )
            if existing is not None:
                if existing.request_sha256 != request_sha256:
                    raise IdempotencyConflictError(detail={"resource": "run_snapshot"})
                return SnapshotCreateResult(snapshot=existing, created=False)

        input_fingerprint = self._input_fingerprint(
            connection_id=payload.connection_id,
            query=query,
            contract=contract,
            policy=payload.build_policy,
        )
        if normalized_key is None:
            reusable = self.session.scalar(
                select(RunSnapshot)
                .where(
                    RunSnapshot.input_fingerprint == input_fingerprint,
                    RunSnapshot.status == "building",
                )
                .order_by(RunSnapshot.created_at.desc(), RunSnapshot.id.desc())
            )
            if reusable is not None:
                return SnapshotCreateResult(snapshot=reusable, created=False)

        snapshot = RunSnapshot(
            id=str(uuid4()),
            name=payload.name,
            trace_contract_id=contract.id,
            connection_id=payload.connection_id,
            named_query_id=payload.named_query_id,
            status="building",
            input_fingerprint=input_fingerprint,
            idempotency_key=normalized_key,
            request_sha256=request_sha256,
            artifact_size_bytes=0,
            source_row_count=0,
            run_count=0,
            progress_source_rows=0,
            progress_runs=0,
            build_policy=payload.build_policy.model_dump(mode="json"),
            created_at=datetime.now(UTC),
        )
        self.session.add(snapshot)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            if normalized_key is not None:
                existing = self.session.scalar(
                    select(RunSnapshot).where(RunSnapshot.idempotency_key == normalized_key)
                )
                if existing is not None:
                    if existing.request_sha256 == request_sha256:
                        return SnapshotCreateResult(snapshot=existing, created=False)
                    raise IdempotencyConflictError(detail={"resource": "run_snapshot"}) from exc
            existing_build = self.session.scalar(
                select(RunSnapshot).where(
                    RunSnapshot.input_fingerprint == input_fingerprint,
                    RunSnapshot.status == "building",
                    RunSnapshot.idempotency_key.is_(None),
                )
            )
            if existing_build is not None:
                return SnapshotCreateResult(snapshot=existing_build, created=False)
            raise ConflictError(
                code="SNAPSHOT_CREATE_CONFLICT",
                message="Snapshot metadata conflicted with another request; retry the request.",
            ) from exc
        logger.info(
            "Snapshot metadata created: snapshot_id={} query_id={} contract_id={} input={}",
            snapshot.id,
            snapshot.named_query_id,
            snapshot.trace_contract_id,
            snapshot.input_fingerprint[:12],
        )
        return SnapshotCreateResult(snapshot=snapshot, created=True)

    def build(self, snapshot_id: str) -> RunSnapshot:
        snapshot = self.get(snapshot_id)
        if snapshot.status != "building":
            return snapshot
        relative_path = f"{_SNAPSHOT_PATH_PREFIX}/{snapshot.id}.jsonl.gz"
        build_directory = self._create_build_directory(snapshot.id)
        artifact_written = False
        try:
            query = self._get_query(snapshot.named_query_id)
            contract_model = TraceContractService(self.session).get(snapshot.trace_contract_id)
            policy = SnapshotBuildPolicy.model_validate(snapshot.build_policy)
            compiled = self._validate_build_input(snapshot, query, contract_model, policy)
            run_spool = _RunSpool(build_directory)
            tracker = _RunIdentityTracker()
            query_service = QueryService(self.session, self._executor_service)
            with query_service.iter_readonly(
                query,
                timeout=policy.timeout_seconds,
                row_limit=policy.max_source_rows,
                batch_size=_QUERY_BATCH_SIZE,
            ) as source:
                if isinstance(compiled.definition, RunRowsContract):
                    self._consume_run_rows(source, compiled, snapshot, run_spool, tracker, policy)
                else:
                    self._consume_event_rows(
                        source,
                        compiled,
                        snapshot,
                        run_spool,
                        tracker,
                        policy,
                        build_directory,
                    )
                if source.truncated:
                    raise ValidationError(
                        code="SNAPSHOT_SOURCE_LIMIT_EXCEEDED",
                        message="Snapshot source row limit was exceeded.",
                        detail={"max_source_rows": policy.max_source_rows},
                    )
            if tracker.run_count == 0:
                raise ValidationError(
                    code="SNAPSHOT_SOURCE_EMPTY",
                    message="Snapshot source query returned no valid runs.",
                )
            self.session.refresh(snapshot)
            if snapshot.status != "building":
                raise SnapshotStateError(detail={"snapshot_id": snapshot.id})
            manifest = self._build_manifest(snapshot, query, contract_model, policy, tracker)
            content_digest = hashlib.sha256()
            lines = self._artifact_lines(manifest, run_spool, content_digest)
            artifact_info = self._artifact_store.write_gzip_jsonl(relative_path, lines)
            artifact_written = True
            self._artifact_store.verify(
                artifact_info.relative_path,
                expected_sha256=artifact_info.sha256,
                expected_size_bytes=artifact_info.size_bytes,
                expected_schema_version=_SNAPSHOT_SCHEMA_VERSION,
            )
            self._mark_ready(snapshot, artifact_info, content_digest.hexdigest(), tracker)
            logger.info(
                "Snapshot ready: snapshot_id={} source_rows={} runs={} content={} artifact={}",
                snapshot.id,
                tracker.source_row_count,
                tracker.run_count,
                snapshot.content_sha256[:12] if snapshot.content_sha256 else None,
                snapshot.artifact_sha256[:12] if snapshot.artifact_sha256 else None,
            )
            return snapshot
        except Exception as exc:
            self.session.rollback()
            if artifact_written:
                try:
                    self._artifact_store.delete(relative_path)
                except Exception as cleanup_exc:
                    logger.warning(
                        "Snapshot artifact cleanup failed: snapshot_id={} error={}",
                        snapshot_id,
                        type(cleanup_exc).__name__,
                    )
            self._mark_failed(snapshot_id, exc)
            raise
        finally:
            shutil.rmtree(build_directory, ignore_errors=True)

    def get(self, snapshot_id: str) -> RunSnapshot:
        snapshot = self.session.get(RunSnapshot, snapshot_id)
        if snapshot is None:
            raise NotFoundError(
                code="SNAPSHOT_NOT_FOUND",
                message="Run snapshot not found.",
                detail={"snapshot_id": snapshot_id},
            )
        return snapshot

    def list(
        self,
        *,
        status: str | None,
        trace_contract_id: str | None,
        cursor: str | None,
        limit: int,
    ) -> RunSnapshotListResponse:
        filters: list[Any] = []
        if status is not None:
            filters.append(RunSnapshot.status == status)
        if trace_contract_id is not None:
            filters.append(RunSnapshot.trace_contract_id == trace_contract_id)
        cursor_value = _decode_list_cursor(cursor)
        if cursor_value is not None:
            created_at, resource_id = cursor_value
            filters.append(
                or_(
                    RunSnapshot.created_at < created_at,
                    (RunSnapshot.created_at == created_at) & (RunSnapshot.id < resource_id),
                )
            )
        statement: Select[tuple[RunSnapshot]] = (
            select(RunSnapshot)
            .where(*filters)
            .order_by(RunSnapshot.created_at.desc(), RunSnapshot.id.desc())
            .limit(limit + 1)
        )
        rows = list(self.session.scalars(statement))
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = _encode_list_cursor(items[-1].created_at, items[-1].id) if has_more else None
        return RunSnapshotListResponse(
            items=[self.to_read(item, include_manifest=False) for item in items],
            pagination=CursorPagination(limit=limit, next_cursor=next_cursor),
        )

    def to_read(self, snapshot: RunSnapshot, *, include_manifest: bool) -> RunSnapshotRead:
        contract = TraceContractService(self.session).get(snapshot.trace_contract_id)
        query = self._get_query(snapshot.named_query_id)
        policy = SnapshotBuildPolicy.model_validate(snapshot.build_policy)
        manifest = (
            self._load_manifest(snapshot)
            if include_manifest and snapshot.status == "ready"
            else None
        )
        return RunSnapshotRead(
            id=snapshot.id,
            name=snapshot.name,
            trace_contract_id=snapshot.trace_contract_id,
            trace_contract_version=contract.version,
            connection_id=snapshot.connection_id,
            named_query_id=snapshot.named_query_id,
            named_query_name=query.name,
            status=cast(SnapshotStatus, snapshot.status),
            input_fingerprint=snapshot.input_fingerprint,
            content_sha256=snapshot.content_sha256,
            artifact_sha256=snapshot.artifact_sha256,
            artifact_size_bytes=snapshot.artifact_size_bytes,
            source_row_count=snapshot.source_row_count,
            run_count=snapshot.run_count,
            progress_source_rows=snapshot.progress_source_rows,
            progress_runs=snapshot.progress_runs,
            pairing_key_field_coverage=snapshot.pairing_key_field_coverage,
            build_policy=policy,
            error=_error_info(snapshot.error),
            manifest=manifest,
            created_at=ensure_utc(snapshot.created_at),
            completed_at=(
                None if snapshot.completed_at is None else ensure_utc(snapshot.completed_at)
            ),
            deleted_at=None if snapshot.deleted_at is None else ensure_utc(snapshot.deleted_at),
        )

    def to_status_read(self, snapshot: RunSnapshot) -> RunSnapshotStatusRead:
        return RunSnapshotStatusRead(
            id=snapshot.id,
            status=cast(SnapshotStatus, snapshot.status),
            progress_source_rows=snapshot.progress_source_rows,
            progress_runs=snapshot.progress_runs,
            error=_error_info(snapshot.error),
            completed_at=(
                None if snapshot.completed_at is None else ensure_utc(snapshot.completed_at)
            ),
        )

    def read_rows(
        self,
        snapshot: RunSnapshot,
        *,
        cursor: str | None,
        limit: int,
    ) -> RunSnapshotRowsResponse:
        self._require_ready_artifact(snapshot)
        offset = _decode_rows_cursor(cursor, snapshot)
        rows: list[CanonicalRunRow] = []
        has_more = False
        try:
            assert snapshot.artifact_path is not None
            assert snapshot.artifact_sha256 is not None
            lines = self._artifact_store.iter_gzip_jsonl(
                snapshot.artifact_path,
                expected_sha256=snapshot.artifact_sha256,
                expected_size_bytes=snapshot.artifact_size_bytes,
                expected_schema_version=_SNAPSHOT_SCHEMA_VERSION,
            )
            next(lines, None)
            for index, line in enumerate(lines):
                if index < offset:
                    continue
                if len(rows) >= limit:
                    has_more = True
                    break
                rows.append(CanonicalRunRow.model_validate_json(line))
        except (ArtifactCorruptedError, ArtifactPathError, ValueError) as exc:
            self._mark_corrupted(snapshot, exc)
            raise ArtifactCorruptedError(
                detail={"reason": "snapshot_rows_invalid", "snapshot_id": snapshot.id}
            ) from exc
        next_cursor = _encode_rows_cursor(snapshot, offset + len(rows)) if has_more else None
        return RunSnapshotRowsResponse(
            items=rows,
            pagination=CursorPagination(limit=limit, next_cursor=next_cursor),
        )

    def recover_incomplete(self) -> int:
        snapshots = list(
            self.session.scalars(select(RunSnapshot).where(RunSnapshot.status == "building"))
        )
        now = datetime.now(UTC)
        for snapshot in snapshots:
            if snapshot.artifact_path is not None:
                self._artifact_store.delete(snapshot.artifact_path)
            else:
                self._artifact_store.delete(f"{_SNAPSHOT_PATH_PREFIX}/{snapshot.id}.jsonl.gz")
            snapshot.status = "failed"
            snapshot.error = {
                "code": "SNAPSHOT_BUILD_INTERRUPTED",
                "message": "Snapshot build was interrupted by process restart.",
            }
            snapshot.completed_at = now
        self._artifact_store.cleanup_temporary_files()
        self._cleanup_build_directories()
        if snapshots:
            self.session.commit()
        return len(snapshots)

    def _consume_run_rows(
        self,
        source: ReadonlyQueryStream,
        compiled: CompiledTraceContract,
        snapshot: RunSnapshot,
        spool: _RunSpool,
        tracker: _RunIdentityTracker,
        policy: SnapshotBuildPolicy,
    ) -> None:
        for batch in source:
            for local_index, (row, row_identity) in enumerate(
                zip(batch.rows, batch.row_identities, strict=True)
            ):
                source_index = batch.start_index + local_index
                normalized = normalize_run_row(
                    row,
                    compiled,
                    query_id=snapshot.named_query_id,
                    row_identity=row_identity,
                    source_row_index=source_index,
                )
                tracker.add(normalized.run, source_index=source_index)
                if tracker.run_count > policy.max_runs:
                    raise ValidationError(
                        code="SNAPSHOT_RUN_LIMIT_EXCEEDED",
                        message="Snapshot run limit was exceeded.",
                        detail={"max_runs": policy.max_runs},
                    )
                spool.add(normalized.run)
            tracker.source_row_count += len(batch.rows)
            self._update_progress(snapshot, tracker)

    def _consume_event_rows(
        self,
        source: ReadonlyQueryStream,
        compiled: CompiledTraceContract,
        snapshot: RunSnapshot,
        spool: _RunSpool,
        tracker: _RunIdentityTracker,
        policy: SnapshotBuildPolicy,
        build_directory: Path,
    ) -> None:
        event_spool = _EventSpool(build_directory, compiled)
        for batch in source:
            for local_index, (row, row_identity) in enumerate(
                zip(batch.rows, batch.row_identities, strict=True)
            ):
                source_index = batch.start_index + local_index
                event_spool.add(row, row_identity=row_identity, source_row_index=source_index)
            tracker.source_row_count += len(batch.rows)
            self._update_progress(snapshot, tracker)
        for group in event_spool.iter_groups():
            normalized = aggregate_event_rows(
                group.rows,
                compiled,
                query_id=snapshot.named_query_id,
                row_identities=group.row_identities,
                source_row_indexes=group.source_row_indexes,
            )[0]
            tracker.add(normalized.run, source_index=group.source_row_indexes[0])
            if tracker.run_count > policy.max_runs:
                raise ValidationError(
                    code="SNAPSHOT_RUN_LIMIT_EXCEEDED",
                    message="Snapshot run limit was exceeded.",
                    detail={"max_runs": policy.max_runs},
                )
            spool.add(normalized.run)
            if tracker.run_count % _QUERY_BATCH_SIZE == 0:
                self._update_progress(snapshot, tracker)
        self._update_progress(snapshot, tracker)

    def _artifact_lines(
        self,
        manifest: RunSnapshotManifest,
        spool: _RunSpool,
        content_digest: _HashWriter,
    ) -> Iterator[bytes]:
        yield canonical_json_bytes(manifest)
        for run in spool.iter_sorted():
            semantic_line = _semantic_run_bytes(run)
            content_digest.update(semantic_line)
            content_digest.update(b"\n")
            yield canonical_json_bytes(run)

    def _build_manifest(
        self,
        snapshot: RunSnapshot,
        query: NamedQuery,
        contract: TraceContractModel,
        policy: SnapshotBuildPolicy,
        tracker: _RunIdentityTracker,
    ) -> RunSnapshotManifest:
        return RunSnapshotManifest(
            snapshot_id=snapshot.id,
            created_at=ensure_utc(snapshot.created_at),
            query=SnapshotQueryManifest(
                named_query_id=query.id,
                sql_sha256=compute_sql_fingerprint(query.sql_text),
            ),
            contract=SnapshotContractManifest(
                id=contract.id,
                version=contract.version,
                definition_sha256=contract.definition_sha256,
            ),
            policy=policy,
            source_row_count=tracker.source_row_count,
            run_count=tracker.run_count,
        )

    def _mark_ready(
        self,
        snapshot: RunSnapshot,
        artifact: ArtifactInfo,
        content_sha256: str,
        tracker: _RunIdentityTracker,
    ) -> None:
        snapshot.status = "ready"
        snapshot.content_sha256 = content_sha256
        snapshot.artifact_sha256 = artifact.sha256
        snapshot.artifact_path = artifact.relative_path
        snapshot.artifact_size_bytes = artifact.size_bytes
        snapshot.source_row_count = tracker.source_row_count
        snapshot.run_count = tracker.run_count
        snapshot.progress_source_rows = tracker.source_row_count
        snapshot.progress_runs = tracker.run_count
        snapshot.pairing_key_field_coverage = tracker.pairing_key_coverage
        snapshot.error = None
        snapshot.completed_at = datetime.now(UTC)
        self.session.commit()

    def _mark_failed(self, snapshot_id: str, exc: Exception) -> None:
        self.session.rollback()
        snapshot = self.session.get(RunSnapshot, snapshot_id)
        if snapshot is None or snapshot.status != "building":
            return
        code = exc.code if isinstance(exc, AppError) else "SNAPSHOT_BUILD_FAILED"
        message = exc.message if isinstance(exc, AppError) else sanitize_exception_message(exc)
        snapshot.status = "failed"
        snapshot.error = {"code": code, "message": message}
        snapshot.completed_at = datetime.now(UTC)
        self.session.commit()
        logger.warning("Snapshot build failed: snapshot_id={} code={}", snapshot_id, code)

    def _mark_corrupted(self, snapshot: RunSnapshot, exc: Exception) -> None:
        snapshot.status = "corrupted"
        snapshot.error = {
            "code": "ARTIFACT_CORRUPTED",
            "message": "Snapshot artifact failed integrity validation.",
        }
        snapshot.completed_at = datetime.now(UTC)
        self.session.commit()
        logger.warning(
            "Snapshot artifact corrupted: snapshot_id={} error={}",
            snapshot.id,
            type(exc).__name__,
        )

    def _load_manifest(self, snapshot: RunSnapshot) -> RunSnapshotManifest:
        self._require_ready_artifact(snapshot)
        try:
            assert snapshot.artifact_path is not None
            assert snapshot.artifact_sha256 is not None
            payload = self._artifact_store.verify(
                snapshot.artifact_path,
                expected_sha256=snapshot.artifact_sha256,
                expected_size_bytes=snapshot.artifact_size_bytes,
                expected_schema_version=_SNAPSHOT_SCHEMA_VERSION,
            )
            return RunSnapshotManifest.model_validate(payload)
        except (ArtifactCorruptedError, ArtifactPathError, ValueError) as exc:
            self._mark_corrupted(snapshot, exc)
            raise ArtifactCorruptedError(
                detail={"reason": "snapshot_manifest_invalid", "snapshot_id": snapshot.id}
            ) from exc

    @staticmethod
    def _require_ready_artifact(snapshot: RunSnapshot) -> None:
        if (
            snapshot.status != "ready"
            or snapshot.artifact_path is None
            or snapshot.artifact_sha256 is None
        ):
            raise SnapshotStateError(
                code="SNAPSHOT_NOT_READY",
                message="Snapshot artifact is not ready.",
                detail={"snapshot_id": snapshot.id, "status": snapshot.status},
            )

    def _update_progress(self, snapshot: RunSnapshot, tracker: _RunIdentityTracker) -> None:
        snapshot.progress_source_rows = tracker.source_row_count
        snapshot.progress_runs = tracker.run_count
        self.session.commit()

    def _validate_create_references(
        self, payload: RunSnapshotCreate
    ) -> tuple[NamedQuery, TraceContractModel]:
        connection = self.session.get(Connection, payload.connection_id)
        if connection is None:
            raise NotFoundError(
                code="CONNECTION_NOT_FOUND",
                message="Connection not found.",
                detail={"connection_id": payload.connection_id},
            )
        query = self._get_query(payload.named_query_id)
        if query.connection_id != payload.connection_id:
            raise ValidationError(
                code="SNAPSHOT_CONNECTION_QUERY_MISMATCH",
                detail={
                    "connection_id": payload.connection_id,
                    "named_query_id": payload.named_query_id,
                },
            )
        contract = TraceContractService(self.session).get(payload.trace_contract_id)
        if contract.named_query_id != payload.named_query_id or contract.archived_at is not None:
            raise ValidationError(
                code="SNAPSHOT_CONTRACT_QUERY_MISMATCH",
                detail={
                    "trace_contract_id": payload.trace_contract_id,
                    "named_query_id": payload.named_query_id,
                },
            )
        return query, contract

    def _validate_build_input(
        self,
        snapshot: RunSnapshot,
        query: NamedQuery,
        contract: TraceContractModel,
        policy: SnapshotBuildPolicy,
    ) -> CompiledTraceContract:
        compiled = compile_contract(contract.definition)
        actual_definition_sha256 = _sha256(
            canonical_json_bytes(compiled.definition.model_dump(mode="json"))
        )
        if actual_definition_sha256 != contract.definition_sha256:
            raise ValidationError(
                code="SNAPSHOT_CONTRACT_HASH_MISMATCH",
                message="Trace contract metadata failed its definition hash check.",
            )
        current_input_fingerprint = self._input_fingerprint(
            connection_id=snapshot.connection_id,
            query=query,
            contract=contract,
            policy=policy,
        )
        if current_input_fingerprint != snapshot.input_fingerprint:
            raise ValidationError(
                code="SNAPSHOT_INPUT_CHANGED",
                message="Snapshot query or contract changed before the build started.",
            )
        return compiled

    def _input_fingerprint(
        self,
        *,
        connection_id: int,
        query: NamedQuery,
        contract: TraceContractModel,
        policy: SnapshotBuildPolicy,
    ) -> str:
        fingerprint_payload = {
            "schema_version": "snapshot-input/v1",
            "connection_id": connection_id,
            "named_query_id": query.id,
            "sql_sha256": compute_sql_fingerprint(query.sql_text),
            "trace_contract_id": contract.id,
            "trace_contract_version": contract.version,
            "trace_contract_definition_sha256": contract.definition_sha256,
            "build_policy": policy.model_dump(mode="json"),
        }
        return _sha256(canonical_json_bytes(fingerprint_payload))

    def _get_query(self, query_id: int) -> NamedQuery:
        query = self.session.get(NamedQuery, query_id)
        if query is None:
            raise NotFoundError(
                code="QUERY_NOT_FOUND",
                message="Named query not found.",
                detail={"query_id": query_id},
            )
        return query

    def _create_build_directory(self, snapshot_id: str) -> Path:
        snapshots_dir = self._artifact_store.resolve(_SNAPSHOT_PATH_PREFIX)
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix=f".{snapshot_id}.build-", dir=snapshots_dir))

    def _cleanup_build_directories(self) -> None:
        snapshots_dir = self._artifact_store.resolve(_SNAPSHOT_PATH_PREFIX)
        if not snapshots_dir.exists():
            return
        for path in snapshots_dir.glob(".*.build-*"):
            resolved = path.resolve(strict=False)
            if resolved.is_relative_to(snapshots_dir.resolve()) and path.is_dir():
                shutil.rmtree(path, ignore_errors=True)


class _RunIdentityTracker:
    def __init__(self) -> None:
        self.source_row_count = 0
        self.run_count = 0
        self._pairing_count = 0
        self._trace_ids: set[str] = set()
        self._task_trials: set[tuple[str, str | None]] = set()
        self._pairing_keys: set[tuple[str, str]] = set()

    @property
    def pairing_key_coverage(self) -> float:
        return self._pairing_count / self.run_count if self.run_count else 0.0

    def add(self, run: CanonicalRunRow, *, source_index: int) -> None:
        if run.trace_id in self._trace_ids:
            _snapshot_row_error(source_index, "duplicate_trace_id", "trace_id")
        task_trial = (run.task_id, run.trial_id)
        if task_trial in self._task_trials:
            _snapshot_row_error(source_index, "duplicate_task_trial", "trial_id")
        if run.pairing_key is not None:
            pairing_key = (run.task_id, run.pairing_key)
            if pairing_key in self._pairing_keys:
                _snapshot_row_error(source_index, "duplicate_pairing_key", "pairing_key")
            self._pairing_keys.add(pairing_key)
            self._pairing_count += 1
        self._trace_ids.add(run.trace_id)
        self._task_trials.add(task_trial)
        self.run_count += 1


class _RunSpool:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._buffer: list[tuple[tuple[str, int, str, str], bytes]] = []
        self._buffer_bytes = 0
        self._chunks: list[Path] = []

    def add(self, run: CanonicalRunRow) -> None:
        line = canonical_json_bytes(run)
        if self._buffer and self._buffer_bytes + len(line) > _RUN_CHUNK_MAX_BYTES:
            self._flush()
        self._buffer.append((_run_sort_key(run), line))
        self._buffer_bytes += len(line)

    def iter_sorted(self) -> Iterator[CanonicalRunRow]:
        self._flush()
        iterators = [self._iter_chunk(path) for path in self._chunks]
        for _, _, run in heapq.merge(*iterators):
            yield run

    def _flush(self) -> None:
        if not self._buffer:
            return
        self._buffer.sort(key=lambda item: item[0])
        path = self._directory / f"run-{len(self._chunks):06d}.jsonl"
        with path.open("wb") as chunk:
            for _, line in self._buffer:
                chunk.write(line)
                chunk.write(b"\n")
        self._chunks.append(path)
        self._buffer.clear()
        self._buffer_bytes = 0

    @staticmethod
    def _iter_chunk(path: Path) -> Iterator[tuple[tuple[str, int, str, str], str, CanonicalRunRow]]:
        with path.open("rb") as chunk:
            for line in chunk:
                run = CanonicalRunRow.model_validate_json(line)
                yield _run_sort_key(run), run.trace_id, run


@dataclass(slots=True)
class _EventGroup:
    rows: list[Mapping[str, object]]
    row_identities: list[str]
    source_row_indexes: list[int]


class _EventSpool:
    def __init__(self, directory: Path, contract: CompiledTraceContract) -> None:
        self._directory = directory
        self._contract = contract
        self._buffer: list[tuple[tuple[str, int, int | str], bytes]] = []
        self._buffer_bytes = 0
        self._chunks: list[Path] = []

    def add(
        self,
        row: Mapping[str, object],
        *,
        row_identity: str,
        source_row_index: int,
    ) -> None:
        trace_value = extract_path(row, self._contract.paths["trace_id"])
        trace_id = _source_identifier(trace_value, source_row_index, "trace_id")
        event_index = extract_path(row, self._contract.paths["event_index"])
        if isinstance(event_index, bool) or not isinstance(event_index, (int, str)):
            _snapshot_row_error(source_row_index, "event_index_type_invalid", "event_index")
        if isinstance(event_index, str) and not event_index.strip():
            _snapshot_row_error(source_row_index, "event_index_empty", "event_index")
        key = (trace_id, 0 if isinstance(event_index, int) else 1, event_index)
        record = canonical_json_bytes(
            {
                "trace_id": trace_id,
                "event_index": event_index,
                "row_identity": row_identity,
                "source_row_index": source_row_index,
                "row": project_source_row(row, self._contract),
            }
        )
        if self._buffer and self._buffer_bytes + len(record) > _EVENT_CHUNK_MAX_BYTES:
            self._flush()
        self._buffer.append((key, record))
        self._buffer_bytes += len(record)

    def iter_groups(self) -> Iterator[_EventGroup]:
        self._flush()
        iterators = [self._iter_chunk(path) for path in self._chunks]
        active_trace_id: str | None = None
        rows: list[Mapping[str, object]] = []
        identities: list[str] = []
        indexes: list[int] = []
        for _, _, record in heapq.merge(*iterators):
            trace_id = cast(str, record["trace_id"])
            if active_trace_id is not None and trace_id != active_trace_id:
                yield _EventGroup(rows=rows, row_identities=identities, source_row_indexes=indexes)
                rows, identities, indexes = [], [], []
            active_trace_id = trace_id
            raw_row = record["row"]
            if not isinstance(raw_row, Mapping):
                raise SnapshotRowError(detail={"reason": "event_spool_row_invalid"})
            rows.append(cast(Mapping[str, object], raw_row))
            identities.append(str(record["row_identity"]))
            raw_source_index = record["source_row_index"]
            if isinstance(raw_source_index, bool) or not isinstance(raw_source_index, int):
                raise SnapshotRowError(detail={"reason": "event_spool_source_index_invalid"})
            indexes.append(raw_source_index)
        if active_trace_id is not None:
            yield _EventGroup(rows=rows, row_identities=identities, source_row_indexes=indexes)

    def _flush(self) -> None:
        if not self._buffer:
            return
        self._buffer.sort(key=lambda item: item[0])
        path = self._directory / f"event-{len(self._chunks):06d}.jsonl"
        with path.open("wb") as chunk:
            for _, record in self._buffer:
                chunk.write(record)
                chunk.write(b"\n")
        self._chunks.append(path)
        self._buffer.clear()
        self._buffer_bytes = 0

    @staticmethod
    def _iter_chunk(
        path: Path,
    ) -> Iterator[tuple[tuple[str, int, int | str], str, dict[str, object]]]:
        with path.open("rb") as chunk:
            for sequence, line in enumerate(chunk):
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise SnapshotRowError(detail={"reason": "event_spool_record_invalid"})
                trace_id = str(payload["trace_id"])
                event_index = payload["event_index"]
                if isinstance(event_index, bool) or not isinstance(event_index, (int, str)):
                    raise SnapshotRowError(detail={"reason": "event_spool_index_invalid"})
                key = (trace_id, 0 if isinstance(event_index, int) else 1, event_index)
                yield key, f"{path.name}:{sequence}", cast(dict[str, object], payload)


def _run_sort_key(run: CanonicalRunRow) -> tuple[str, int, str, str]:
    return (run.task_id, 0 if run.trial_id is None else 1, run.trial_id or "", run.trace_id)


def _semantic_run_bytes(run: CanonicalRunRow) -> bytes:
    payload = run.model_dump(mode="json")
    raw_messages = payload.get("messages")
    if isinstance(raw_messages, list):
        for message in raw_messages:
            if isinstance(message, dict):
                message.pop("source_ref", None)
    return canonical_json_bytes(payload)


def _snapshot_row_error(source_index: int, reason: str, path: str) -> NoReturn:
    raise SnapshotRowError(
        detail={"reason": reason, "path": path, "source_row_index": source_index}
    )


def _source_identifier(value: object, source_index: int, path: str) -> str:
    if value is None or isinstance(value, bool) or not isinstance(value, (str, int, float)):
        _snapshot_row_error(source_index, "id_type_invalid", path)
    normalized = str(value).strip()
    if not normalized:
        _snapshot_row_error(source_index, "id_empty", path)
    return normalized


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


def _error_info(value: Mapping[str, object] | None) -> SnapshotErrorInfo | None:
    if value is None:
        return None
    return SnapshotErrorInfo(
        code=str(value.get("code", "SNAPSHOT_BUILD_FAILED")),
        message=str(value.get("message", "Snapshot build failed.")),
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _encode_list_cursor(created_at: datetime, resource_id: str) -> str:
    return _encode_cursor(
        {
            "kind": "snapshot-list/v1",
            "created_at": ensure_utc(created_at).isoformat(),
            "id": resource_id,
        }
    )


def _decode_list_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if cursor is None:
        return None
    payload = _decode_cursor(cursor, expected_kind="snapshot-list/v1")
    try:
        return ensure_utc(datetime.fromisoformat(str(payload["created_at"]))), str(payload["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(
            code="CURSOR_INVALID", message="Pagination cursor is invalid."
        ) from exc


def _encode_rows_cursor(snapshot: RunSnapshot, offset: int) -> str:
    return _encode_cursor(
        {
            "kind": "snapshot-rows/v1",
            "snapshot_id": snapshot.id,
            "content_sha256": snapshot.content_sha256,
            "offset": offset,
        }
    )


def _decode_rows_cursor(cursor: str | None, snapshot: RunSnapshot) -> int:
    if cursor is None:
        return 0
    payload = _decode_cursor(cursor, expected_kind="snapshot-rows/v1")
    try:
        raw_offset = payload["offset"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(
            code="CURSOR_INVALID", message="Pagination cursor is invalid."
        ) from exc
    if isinstance(raw_offset, bool) or not isinstance(raw_offset, int):
        raise ValidationError(code="CURSOR_INVALID", message="Pagination cursor is invalid.")
    offset = raw_offset
    if (
        offset < 0
        or payload.get("snapshot_id") != snapshot.id
        or payload.get("content_sha256") != snapshot.content_sha256
    ):
        raise ValidationError(code="CURSOR_INVALID", message="Pagination cursor is invalid.")
    return offset


def _encode_cursor(payload: Mapping[str, object]) -> str:
    return base64.urlsafe_b64encode(canonical_json_bytes(payload)).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, *, expected_kind: str) -> Mapping[str, object]:
    if len(cursor) > _MAX_CURSOR_LENGTH:
        raise ValidationError(code="CURSOR_INVALID", message="Pagination cursor is invalid.")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(
            code="CURSOR_INVALID", message="Pagination cursor is invalid."
        ) from exc
    if not isinstance(payload, Mapping) or payload.get("kind") != expected_kind:
        raise ValidationError(code="CURSOR_INVALID", message="Pagination cursor is invalid.")
    return cast(Mapping[str, object], payload)
