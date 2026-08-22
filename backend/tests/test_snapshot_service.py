from __future__ import annotations

import tracemalloc
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn, cast

import pytest

from app.core.artifact_store import ArtifactStore
from app.core.errors import (
    AppError,
    ArtifactCorruptedError,
    ArtifactWriteError,
    IdempotencyConflictError,
    NotFoundError,
    SqlTimeoutError,
    ValidationError,
)
from app.db.session import get_session_factory, initialize_metadata_database
from app.models.connection import Connection
from app.models.named_query import NamedQuery
from app.models.trace_contract import RunSnapshot
from app.models.view_config import ViewConfig
from app.schemas.run_snapshot import RunSnapshotCreate, SnapshotBuildPolicy
from app.schemas.trace_contract import TraceContractCreate
from app.services.query_executor import ExecutorBatch, ExecutorService, ExecutorStream
from app.services.snapshot_service import SnapshotService
from app.services.trace_contract_service import TraceContractService
from scripts.generate_regression_fixtures import QUICK_SPEC, generate_fixture

_CONNECTION_ID = 1
_RUN_QUERY_ID = 11
_EVENT_QUERY_ID = 12
_TRUNCATED_QUERY_ID = 13
_FAKE_BATCH_SIZE = 17
_PAGE_SIZE = 2
_TEN_THOUSAND_RUNS = 10_000
_MAX_BUILD_MEMORY_BYTES = 128 * 1024 * 1024


class FakeStreamingExecutor:
    def __init__(
        self,
        rows_by_query: dict[int, list[dict[str, object]]],
        *,
        failure_after_first_batch: AppError | None = None,
    ) -> None:
        self.rows_by_query = rows_by_query
        self.batch_counts: dict[int, int] = {}
        self.failure_after_first_batch = failure_after_first_batch

    @contextmanager
    def iter_execute(
        self,
        connection: Connection,
        sql: str,
        *,
        timeout: int,
        row_limit: int,
        batch_size: int,
        query_id: int | None,
        sql_fingerprint: str | None,
    ) -> Iterator[ExecutorStream]:
        assert connection.id == _CONNECTION_ID
        assert sql.startswith("SELECT")
        assert timeout > 0 and batch_size > 0 and sql_fingerprint is not None
        assert query_id is not None
        source_rows = self.rows_by_query[query_id]
        rows = source_rows[:row_limit]
        stream = ExecutorStream(columns=[], batches=iter(()))

        def batches() -> Iterator[ExecutorBatch]:
            count = 0
            for start in range(0, len(rows), _FAKE_BATCH_SIZE):
                batch_rows = deepcopy(rows[start : start + _FAKE_BATCH_SIZE])
                stream.row_count += len(batch_rows)
                count += 1
                yield ExecutorBatch(rows=cast(list[dict[str, Any]], batch_rows), start_index=start)
                if count == 1 and self.failure_after_first_batch is not None:
                    raise self.failure_after_first_batch
            self.batch_counts[query_id] = count
            stream.truncated = len(source_rows) > row_limit

        stream.batches = batches()
        yield stream


def _seed_metadata() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection = Connection(
            id=_CONNECTION_ID,
            name="fixture-source",
            db_type="mysql",
            host="localhost",
            port=3306,
            database="fixtures",
            username="reader",
            default_timeout=30,
            default_row_limit=100_000,
        )
        session.add(connection)
        for query_id, name in (
            (_RUN_QUERY_ID, "run-layout"),
            (_EVENT_QUERY_ID, "event-layout"),
            (_TRUNCATED_QUERY_ID, "truncated-layout"),
        ):
            query = NamedQuery(
                id=query_id,
                connection_id=_CONNECTION_ID,
                name=name,
                sql_text=f"SELECT * FROM {name.replace('-', '_')}",
                is_named=True,
            )
            query.view_config = ViewConfig(field_renders="{}", table_config="{}")
            session.add(query)
        session.commit()
    finally:
        session.close()


def _create_contract(query_id: int, name: str, definition: dict[str, object]) -> str:
    session = get_session_factory()()
    try:
        contract = TraceContractService(session).create(
            TraceContractCreate(
                name=name,
                named_query_id=query_id,
                definition=definition,
            )
        )
        return contract.id
    finally:
        session.close()


def _create_snapshot(
    service: SnapshotService,
    *,
    query_id: int,
    contract_id: str,
    policy: SnapshotBuildPolicy | None = None,
) -> str:
    result = service.create(
        RunSnapshotCreate(
            name=f"snapshot-{query_id}",
            connection_id=_CONNECTION_ID,
            named_query_id=query_id,
            trace_contract_id=contract_id,
            build_policy=policy or SnapshotBuildPolicy(),
        )
    )
    assert result.created is True
    return result.snapshot.id


def _semantic_row(row: object) -> dict[str, object]:
    payload = cast(Any, row).model_dump(mode="json")
    for message in payload["messages"]:
        message.pop("source_ref", None)
    return cast(dict[str, object], payload)


def test_run_and_event_layouts_build_equivalent_paginated_snapshots(tmp_path: Path) -> None:
    fixture = generate_fixture(QUICK_SPEC)
    _seed_metadata()
    run_contract_id = _create_contract(_RUN_QUERY_ID, "fixture-run", fixture.contracts["run_rows"])
    event_contract_id = _create_contract(
        _EVENT_QUERY_ID, "fixture-event", fixture.contracts["event_rows"]
    )
    executor = FakeStreamingExecutor(
        {
            _RUN_QUERY_ID: fixture.baseline_run_rows,
            _EVENT_QUERY_ID: list(reversed(fixture.baseline_event_rows)),
        }
    )
    session = get_session_factory()()
    try:
        service = SnapshotService(
            session,
            executor_service=cast(ExecutorService, executor),
            artifact_store=ArtifactStore(tmp_path),
        )
        run_id = _create_snapshot(service, query_id=_RUN_QUERY_ID, contract_id=run_contract_id)
        event_id = _create_snapshot(
            service, query_id=_EVENT_QUERY_ID, contract_id=event_contract_id
        )

        run_snapshot = service.build(run_id)
        event_snapshot = service.build(event_id)

        assert run_snapshot.status == event_snapshot.status == "ready"
        assert run_snapshot.content_sha256 == event_snapshot.content_sha256
        assert run_snapshot.run_count == event_snapshot.run_count
        assert executor.batch_counts[_RUN_QUERY_ID] > 1
        assert executor.batch_counts[_EVENT_QUERY_ID] > 1

        first_page = service.read_rows(run_snapshot, cursor=None, limit=_PAGE_SIZE)
        assert len(first_page.items) == _PAGE_SIZE
        assert first_page.pagination.next_cursor is not None
        second_page = service.read_rows(
            run_snapshot,
            cursor=first_page.pagination.next_cursor,
            limit=_PAGE_SIZE,
        )
        assert len(second_page.items) == _PAGE_SIZE

        run_rows = service.read_rows(run_snapshot, cursor=None, limit=200).items
        event_rows = service.read_rows(event_snapshot, cursor=None, limit=200).items
        assert [_semantic_row(row) for row in run_rows] == [
            _semantic_row(row) for row in event_rows
        ]
        detail = service.to_read(run_snapshot, include_manifest=True)
        assert detail.manifest is not None
        assert detail.manifest.run_count == run_snapshot.run_count
    finally:
        session.close()


def test_source_limit_failure_never_exposes_ready_artifact(tmp_path: Path) -> None:
    fixture = generate_fixture(QUICK_SPEC)
    _seed_metadata()
    contract_id = _create_contract(
        _TRUNCATED_QUERY_ID,
        "fixture-truncated",
        fixture.contracts["run_rows"],
    )
    executor = FakeStreamingExecutor({_TRUNCATED_QUERY_ID: fixture.baseline_run_rows})
    session = get_session_factory()()
    try:
        store = ArtifactStore(tmp_path)
        service = SnapshotService(
            session,
            executor_service=cast(ExecutorService, executor),
            artifact_store=store,
        )
        snapshot_id = _create_snapshot(
            service,
            query_id=_TRUNCATED_QUERY_ID,
            contract_id=contract_id,
            policy=SnapshotBuildPolicy(max_source_rows=10),
        )

        with pytest.raises(ValidationError) as exc_info:
            service.build(snapshot_id)

        failed = service.get(snapshot_id)
        assert exc_info.value.code == "SNAPSHOT_SOURCE_LIMIT_EXCEEDED"
        assert failed.status == "failed"
        assert failed.error is not None
        assert failed.error["code"] == "SNAPSHOT_SOURCE_LIMIT_EXCEEDED"
        assert not store.resolve(f"snapshots/{snapshot_id}.jsonl.gz").exists()
    finally:
        session.close()


@pytest.mark.parametrize(
    "failure",
    [
        ValidationError(code="SNAPSHOT_ITERATOR_TEST_FAILURE"),
        SqlTimeoutError(detail={"timeout": 1}),
    ],
    ids=["iterator", "timeout"],
)
def test_stream_failure_never_exposes_ready_artifact(
    tmp_path: Path,
    failure: AppError,
) -> None:
    fixture = generate_fixture(QUICK_SPEC)
    _seed_metadata()
    contract_id = _create_contract(
        _RUN_QUERY_ID, f"stream-failure-{failure.code}", fixture.contracts["run_rows"]
    )
    session = get_session_factory()()
    try:
        store = ArtifactStore(tmp_path)
        executor = FakeStreamingExecutor(
            {_RUN_QUERY_ID: fixture.baseline_run_rows},
            failure_after_first_batch=failure,
        )
        service = SnapshotService(
            session,
            executor_service=cast(ExecutorService, executor),
            artifact_store=store,
        )
        snapshot_id = _create_snapshot(service, query_id=_RUN_QUERY_ID, contract_id=contract_id)

        with pytest.raises(type(failure)):
            service.build(snapshot_id)

        failed = service.get(snapshot_id)
        assert failed.status == "failed"
        assert failed.error is not None and failed.error["code"] == failure.code
        assert not store.resolve(f"snapshots/{snapshot_id}.jsonl.gz").exists()
    finally:
        session.close()


def test_query_change_before_build_fails_fingerprint_check(tmp_path: Path) -> None:
    fixture = generate_fixture(QUICK_SPEC)
    _seed_metadata()
    contract_id = _create_contract(_RUN_QUERY_ID, "input-change", fixture.contracts["run_rows"])
    session = get_session_factory()()
    try:
        store = ArtifactStore(tmp_path)
        executor = FakeStreamingExecutor({_RUN_QUERY_ID: fixture.baseline_run_rows})
        service = SnapshotService(
            session,
            executor_service=cast(ExecutorService, executor),
            artifact_store=store,
        )
        snapshot_id = _create_snapshot(service, query_id=_RUN_QUERY_ID, contract_id=contract_id)
        query = session.get(NamedQuery, _RUN_QUERY_ID)
        assert query is not None
        query.sql_text = "SELECT * FROM changed_source"
        session.commit()

        with pytest.raises(ValidationError) as exc_info:
            service.build(snapshot_id)

        assert exc_info.value.code == "SNAPSHOT_INPUT_CHANGED"
        assert service.get(snapshot_id).status == "failed"
        assert executor.batch_counts == {}
        assert not store.resolve(f"snapshots/{snapshot_id}.jsonl.gz").exists()
    finally:
        session.close()


def test_artifact_write_failure_marks_snapshot_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_fixture(QUICK_SPEC)
    _seed_metadata()
    contract_id = _create_contract(
        _RUN_QUERY_ID, "artifact-write-failure", fixture.contracts["run_rows"]
    )
    session = get_session_factory()()
    try:
        store = ArtifactStore(tmp_path)
        service = SnapshotService(
            session,
            executor_service=cast(
                ExecutorService,
                FakeStreamingExecutor({_RUN_QUERY_ID: fixture.baseline_run_rows}),
            ),
            artifact_store=store,
        )
        snapshot_id = _create_snapshot(service, query_id=_RUN_QUERY_ID, contract_id=contract_id)

        def fail_write(*_: object, **__: object) -> NoReturn:
            raise ArtifactWriteError(detail={"reason": "injected_write_failure"})

        monkeypatch.setattr(store, "write_gzip_jsonl", fail_write)

        with pytest.raises(ArtifactWriteError):
            service.build(snapshot_id)

        failed = service.get(snapshot_id)
        assert failed.status == "failed"
        assert failed.error is not None and failed.error["code"] == "ARTIFACT_WRITE_FAILED"
        assert not store.resolve(f"snapshots/{snapshot_id}.jsonl.gz").exists()
    finally:
        session.close()


def test_snapshot_reader_marks_same_size_tamper_corrupted(tmp_path: Path) -> None:
    fixture = generate_fixture(QUICK_SPEC)
    _seed_metadata()
    contract_id = _create_contract(_RUN_QUERY_ID, "tamper-run", fixture.contracts["run_rows"])
    executor = FakeStreamingExecutor({_RUN_QUERY_ID: fixture.baseline_run_rows})
    session = get_session_factory()()
    try:
        store = ArtifactStore(tmp_path)
        service = SnapshotService(
            session,
            executor_service=cast(ExecutorService, executor),
            artifact_store=store,
        )
        snapshot_id = _create_snapshot(service, query_id=_RUN_QUERY_ID, contract_id=contract_id)
        snapshot = service.build(snapshot_id)
        assert snapshot.artifact_path is not None
        path = store.resolve(snapshot.artifact_path, must_exist=True)
        payload = bytearray(path.read_bytes())
        payload[len(payload) // 2] ^= 1
        path.write_bytes(payload)

        with pytest.raises(ArtifactCorruptedError):
            service.read_rows(snapshot, cursor=None, limit=10)

        assert service.get(snapshot_id).status == "corrupted"
    finally:
        session.close()


def test_contract_and_snapshot_idempotency_conflicts_are_explicit(tmp_path: Path) -> None:
    fixture = generate_fixture(QUICK_SPEC)
    _seed_metadata()
    session = get_session_factory()()
    try:
        contract_service = TraceContractService(session)
        payload = TraceContractCreate(
            name="idempotent",
            named_query_id=_RUN_QUERY_ID,
            definition=fixture.contracts["run_rows"],
        )
        first = contract_service.create(payload, idempotency_key="contract-key")
        second = contract_service.create(payload, idempotency_key="contract-key")
        assert second.id == first.id

        next_version = contract_service.create(payload)
        assert next_version.id != first.id
        assert next_version.version == first.version + 1

        changed = payload.model_copy(update={"name": "changed"})
        with pytest.raises(IdempotencyConflictError):
            contract_service.create(changed, idempotency_key="contract-key")

        service = SnapshotService(
            session,
            executor_service=cast(
                ExecutorService,
                FakeStreamingExecutor({_RUN_QUERY_ID: fixture.baseline_run_rows}),
            ),
            artifact_store=ArtifactStore(tmp_path),
        )
        snapshot_payload = RunSnapshotCreate(
            name="idempotent-snapshot",
            connection_id=_CONNECTION_ID,
            named_query_id=_RUN_QUERY_ID,
            trace_contract_id=first.id,
        )
        first_snapshot = service.create(snapshot_payload, idempotency_key="snapshot-key")
        second_snapshot = service.create(snapshot_payload, idempotency_key="snapshot-key")
        assert second_snapshot.snapshot.id == first_snapshot.snapshot.id
        assert second_snapshot.created is False

        distinct_key_snapshot = service.create(
            snapshot_payload,
            idempotency_key="another-snapshot-key",
        )
        assert distinct_key_snapshot.created is True
        assert distinct_key_snapshot.snapshot.id != first_snapshot.snapshot.id

        first_page = service.list(
            status="building",
            trace_contract_id=first.id,
            cursor=None,
            limit=1,
        )
        assert len(first_page.items) == 1
        assert first_page.pagination.next_cursor is not None
        second_page = service.list(
            status="building",
            trace_contract_id=first.id,
            cursor=first_page.pagination.next_cursor,
            limit=1,
        )
        assert len(second_page.items) == 1
        assert first_page.items[0].id != second_page.items[0].id

        with pytest.raises(IdempotencyConflictError):
            service.create(
                snapshot_payload.model_copy(update={"name": "changed"}),
                idempotency_key="snapshot-key",
            )
    finally:
        session.close()


def test_input_fingerprint_reuses_only_an_active_build(tmp_path: Path) -> None:
    fixture = generate_fixture(QUICK_SPEC)
    _seed_metadata()
    contract_id = _create_contract(
        _RUN_QUERY_ID, "fingerprint-reuse", fixture.contracts["run_rows"]
    )
    session = get_session_factory()()
    try:
        service = SnapshotService(
            session,
            executor_service=cast(
                ExecutorService,
                FakeStreamingExecutor({_RUN_QUERY_ID: fixture.baseline_run_rows}),
            ),
            artifact_store=ArtifactStore(tmp_path),
        )
        payload = RunSnapshotCreate(
            name="fingerprint-snapshot",
            connection_id=_CONNECTION_ID,
            named_query_id=_RUN_QUERY_ID,
            trace_contract_id=contract_id,
        )

        first = service.create(payload)
        active_retry = service.create(payload)

        assert active_retry.created is False
        assert active_retry.snapshot.id == first.snapshot.id

        service.build(first.snapshot.id)
        fresh_capture = service.create(payload)

        assert fresh_capture.created is True
        assert fresh_capture.snapshot.id != first.snapshot.id
        assert fresh_capture.snapshot.input_fingerprint == first.snapshot.input_fingerprint
    finally:
        session.close()


def test_trace_contract_service_validation_lookup_and_cursor_edges() -> None:
    fixture = generate_fixture(QUICK_SPEC)
    _seed_metadata()
    session = get_session_factory()()
    try:
        service = TraceContractService(session)
        payload = TraceContractCreate(
            name="service-edges",
            named_query_id=_RUN_QUERY_ID,
            definition=fixture.contracts["run_rows"],
        )
        first = service.create(payload)
        second = service.create(payload)

        first_page = service.list(
            named_query_id=_RUN_QUERY_ID,
            include_archived=False,
            cursor=None,
            limit=1,
        )
        assert len(first_page.items) == 1
        assert first_page.pagination.next_cursor is not None
        second_page = service.list(
            named_query_id=_RUN_QUERY_ID,
            include_archived=True,
            cursor=first_page.pagination.next_cursor,
            limit=1,
        )
        assert [item.id for item in first_page.items + second_page.items] == [
            second.id,
            first.id,
        ]

        empty = service.validate_rows(
            payload.definition,
            [],
            query_id=_RUN_QUERY_ID,
            row_identities=[],
        )
        invalid = service.validate_rows(
            payload.definition,
            [{}],
            query_id=_RUN_QUERY_ID,
            row_identities=["invalid-row"],
        )
        assert empty.valid is False and empty.errors[0].reason == "sample_empty"
        assert invalid.valid is False and invalid.errors[0].path == "case_id"

        with pytest.raises(ValidationError, match="Pagination cursor is invalid"):
            service.list(
                named_query_id=None,
                include_archived=False,
                cursor="not-a-cursor",
                limit=10,
            )
        with pytest.raises(NotFoundError):
            service.get("missing-contract")
        with pytest.raises(NotFoundError):
            service.create(payload.model_copy(update={"named_query_id": 999_999}))
        with pytest.raises(ValidationError) as idempotency_error:
            service.create(payload, idempotency_key=" ")
        assert idempotency_error.value.code == "IDEMPOTENCY_KEY_INVALID"
    finally:
        session.close()


def test_snapshot_reader_rejects_traversal_metadata_and_marks_corrupted(
    tmp_path: Path,
) -> None:
    fixture = generate_fixture(QUICK_SPEC)
    _seed_metadata()
    contract_id = _create_contract(
        _RUN_QUERY_ID, "traversal-metadata", fixture.contracts["run_rows"]
    )
    session = get_session_factory()()
    try:
        service = SnapshotService(
            session,
            executor_service=cast(
                ExecutorService,
                FakeStreamingExecutor({_RUN_QUERY_ID: fixture.baseline_run_rows}),
            ),
            artifact_store=ArtifactStore(tmp_path),
        )
        snapshot_id = _create_snapshot(service, query_id=_RUN_QUERY_ID, contract_id=contract_id)
        snapshot = service.build(snapshot_id)
        snapshot.artifact_path = "../outside.jsonl.gz"
        session.commit()

        with pytest.raises(ArtifactCorruptedError):
            service.to_read(snapshot, include_manifest=True)

        assert service.get(snapshot_id).status == "corrupted"
    finally:
        session.close()


def test_ready_db_commit_failure_removes_final_artifact_and_marks_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = generate_fixture(QUICK_SPEC)
    _seed_metadata()
    contract_id = _create_contract(_RUN_QUERY_ID, "commit-failure", fixture.contracts["run_rows"])
    session = get_session_factory()()
    store = ArtifactStore(tmp_path)
    try:
        service = SnapshotService(
            session,
            executor_service=cast(
                ExecutorService,
                FakeStreamingExecutor({_RUN_QUERY_ID: fixture.baseline_run_rows}),
            ),
            artifact_store=store,
        )
        snapshot_id = _create_snapshot(service, query_id=_RUN_QUERY_ID, contract_id=contract_id)
        original_commit = session.commit
        injected = False

        def commit_with_ready_failure() -> None:
            nonlocal injected
            snapshot = session.get(RunSnapshot, snapshot_id)
            if snapshot is not None and snapshot.status == "ready" and not injected:
                injected = True
                raise OSError("injected metadata commit failure")
            original_commit()

        monkeypatch.setattr(session, "commit", commit_with_ready_failure)

        with pytest.raises(OSError, match="injected metadata commit failure"):
            service.build(snapshot_id)

        failed = service.get(snapshot_id)
        assert failed.status == "failed"
        assert not store.resolve(f"snapshots/{snapshot_id}.jsonl.gz").exists()
    finally:
        session.close()


def test_restart_recovery_marks_building_failed_and_cleans_orphans(tmp_path: Path) -> None:
    fixture = generate_fixture(QUICK_SPEC)
    _seed_metadata()
    contract_id = _create_contract(_RUN_QUERY_ID, "restart-recovery", fixture.contracts["run_rows"])
    session = get_session_factory()()
    store = ArtifactStore(tmp_path)
    try:
        service = SnapshotService(
            session,
            executor_service=cast(
                ExecutorService,
                FakeStreamingExecutor({_RUN_QUERY_ID: fixture.baseline_run_rows}),
            ),
            artifact_store=store,
        )
        snapshot_id = _create_snapshot(service, query_id=_RUN_QUERY_ID, contract_id=contract_id)
        final_path = store.resolve(f"snapshots/{snapshot_id}.jsonl.gz")
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(b"orphan")
        build_directory = final_path.parent / f".{snapshot_id}.build-orphan"
        build_directory.mkdir()
        (build_directory / "chunk").write_bytes(b"partial")

        assert service.recover_incomplete() == 1

        recovered = service.get(snapshot_id)
        assert recovered.status == "failed"
        assert recovered.error is not None
        assert recovered.error["code"] == "SNAPSHOT_BUILD_INTERRUPTED"
        assert not final_path.exists()
        assert not build_directory.exists()
    finally:
        session.close()


def test_ten_thousand_run_snapshot_uses_bounded_extra_memory(tmp_path: Path) -> None:
    fixture = generate_fixture(QUICK_SPEC)
    rows = [_performance_run_row(index) for index in range(_TEN_THOUSAND_RUNS)]
    _seed_metadata()
    contract_id = _create_contract(
        _RUN_QUERY_ID, "ten-thousand-runs", fixture.contracts["run_rows"]
    )
    session = get_session_factory()()
    try:
        service = SnapshotService(
            session,
            executor_service=cast(
                ExecutorService,
                FakeStreamingExecutor({_RUN_QUERY_ID: rows}),
            ),
            artifact_store=ArtifactStore(tmp_path),
        )
        snapshot_id = _create_snapshot(
            service,
            query_id=_RUN_QUERY_ID,
            contract_id=contract_id,
            policy=SnapshotBuildPolicy(
                max_source_rows=_TEN_THOUSAND_RUNS,
                max_runs=_TEN_THOUSAND_RUNS,
            ),
        )
        tracemalloc.start()
        baseline_bytes, _ = tracemalloc.get_traced_memory()
        try:
            snapshot = service.build(snapshot_id)
            _, peak_bytes = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        assert snapshot.status == "ready"
        assert snapshot.run_count == _TEN_THOUSAND_RUNS
        assert peak_bytes - baseline_bytes < _MAX_BUILD_MEMORY_BYTES
    finally:
        session.close()


def _performance_run_row(index: int) -> dict[str, object]:
    return {
        "case_id": f"task-{index:05d}",
        "attempt": "0",
        "run_uuid": f"run-{index:05d}",
        "shared_seed": f"seed-{index:05d}",
        "result": {"outcome": "success", "score": 1.0, "error": None},
        "metrics": {"latency_ms": 10.0, "token_usage": 20, "cost_usd": 0.001},
        "dataset_split": "test",
        "model": "fixture-model",
        "payload": {
            "messages": [
                {"role": "user", "content": f"task {index}", "status": "ok"},
                {"role": "assistant", "content": "done", "status": "ok"},
            ]
        },
    }
