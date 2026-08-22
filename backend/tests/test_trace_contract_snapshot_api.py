from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, cast

import httpx
import pytest
from starlette import status

from app.api.execute import get_query_service
from app.core.artifact_store import ArtifactStore
from app.core.snapshot_jobs import get_snapshot_job_runner
from app.db.session import get_session_factory, initialize_metadata_database
from app.main import app
from app.models.connection import Connection
from app.models.named_query import NamedQuery
from app.models.view_config import ViewConfig
from app.services.query_executor import (
    ExecutorBatch,
    ExecutorResult,
    ExecutorService,
    ExecutorStream,
)
from app.services.query_service import ExecutionOutcome
from app.services.snapshot_service import SnapshotService
from scripts.generate_regression_fixtures import QUICK_SPEC, generate_fixture

_QUERY_ID = 31
_EVENT_QUERY_ID = 32
_CONNECTION_ID = 7
_VALIDATION_SAMPLE_SIZE = 2


class FakeSnapshotRunner:
    def __init__(self) -> None:
        self.submitted: list[str] = []

    def submit(self, snapshot_id: str) -> bool:
        self.submitted.append(snapshot_id)
        return True


class InlineSnapshotRunner:
    def __init__(self, executor: ExecutorService, store: ArtifactStore) -> None:
        self.executor = executor
        self.store = store

    def submit(self, snapshot_id: str) -> bool:
        session = get_session_factory()()
        try:
            SnapshotService(
                session,
                executor_service=self.executor,
                artifact_store=self.store,
            ).build(snapshot_id)
        finally:
            session.close()
        return True


class ApiStreamingExecutor:
    def __init__(self, rows_by_query: dict[int, list[dict[str, object]]]) -> None:
        self.rows_by_query = rows_by_query

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
        assert sql.startswith("SELECT") and timeout > 0 and batch_size > 0
        assert query_id is not None and sql_fingerprint is not None
        source_rows = self.rows_by_query[query_id]
        selected_rows = source_rows[:row_limit]
        stream = ExecutorStream(columns=[], batches=iter(()))

        def batches() -> Iterator[ExecutorBatch]:
            for start in range(0, len(selected_rows), batch_size):
                rows = deepcopy(selected_rows[start : start + batch_size])
                stream.row_count += len(rows)
                yield ExecutorBatch(rows=cast(list[dict[str, Any]], rows), start_index=start)
            stream.truncated = len(source_rows) > row_limit

        stream.batches = batches()
        yield stream


class FakeValidationQueryService:
    def __init__(self, query: NamedQuery, outcome: ExecutionOutcome) -> None:
        self.query = query
        self.outcome = outcome

    def get(self, query_id: int) -> NamedQuery:
        assert query_id == self.query.id
        return self.query

    def execute_readonly(
        self,
        query: NamedQuery,
        *,
        timeout: int,
        row_limit: int,
    ) -> ExecutionOutcome:
        assert query.id == self.query.id
        assert timeout > 0 and row_limit > 0
        return self.outcome


def _seed_query() -> NamedQuery:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection = Connection(
            id=_CONNECTION_ID,
            name="contract-api-source",
            db_type="mysql",
            host="localhost",
            port=3306,
            database="fixtures",
            username="reader",
            default_timeout=30,
            default_row_limit=10_000,
        )
        query = NamedQuery(
            id=_QUERY_ID,
            connection_id=_CONNECTION_ID,
            name="contract-api-query",
            sql_text="SELECT * FROM fixture_runs",
            is_named=True,
        )
        query.view_config = ViewConfig(field_renders="{}", table_config="{}")
        event_query = NamedQuery(
            id=_EVENT_QUERY_ID,
            connection_id=_CONNECTION_ID,
            name="contract-api-event-query",
            sql_text="SELECT * FROM fixture_events",
            is_named=True,
        )
        event_query.view_config = ViewConfig(field_renders="{}", table_config="{}")
        session.add_all([connection, query, event_query])
        session.commit()
        _ = query.connection
        return query
    finally:
        session.close()


@pytest.mark.asyncio
async def test_contract_and_snapshot_rest_vertical_contract() -> None:
    fixture = generate_fixture(QUICK_SPEC)
    _seed_query()
    runner = FakeSnapshotRunner()
    app.dependency_overrides[get_snapshot_job_runner] = lambda: runner
    transport = httpx.ASGITransport(app=cast(Any, app))
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            contract_response = await client.post(
                "/api/v1/trace-contracts",
                headers={"Idempotency-Key": "contract-api-key"},
                json={
                    "name": "fixture-contract",
                    "named_query_id": _QUERY_ID,
                    "definition": fixture.contracts["run_rows"],
                },
            )
            contract_payload = contract_response.json()
            contract_id = contract_payload["id"]
            list_contracts = await client.get("/api/v1/trace-contracts")
            contract_detail = await client.get(f"/api/v1/trace-contracts/{contract_id}")
            snapshot_response = await client.post(
                "/api/v1/run-snapshots",
                headers={"Idempotency-Key": "snapshot-api-key"},
                json={
                    "name": "fixture-snapshot",
                    "connection_id": _CONNECTION_ID,
                    "named_query_id": _QUERY_ID,
                    "trace_contract_id": contract_id,
                    "build_policy": {
                        "max_source_rows": 1000,
                        "max_runs": 1000,
                        "timeout_seconds": 30,
                    },
                },
            )
            snapshot_payload = snapshot_response.json()
            snapshot_id = snapshot_payload["id"]
            snapshot_retry = await client.post(
                "/api/v1/run-snapshots",
                headers={"Idempotency-Key": "snapshot-api-key"},
                json={
                    "name": "fixture-snapshot",
                    "connection_id": _CONNECTION_ID,
                    "named_query_id": _QUERY_ID,
                    "trace_contract_id": contract_id,
                    "build_policy": {
                        "max_source_rows": 1000,
                        "max_runs": 1000,
                        "timeout_seconds": 30,
                    },
                },
            )
            list_snapshots = await client.get("/api/v1/run-snapshots")
            snapshot_status = await client.get(f"/api/v1/run-snapshots/{snapshot_id}/status")
            snapshot_rows = await client.get(f"/api/v1/run-snapshots/{snapshot_id}/rows")
    finally:
        app.dependency_overrides.clear()

    assert contract_response.status_code == status.HTTP_201_CREATED
    assert contract_payload["named_query_id"] == _QUERY_ID
    assert isinstance(contract_id, str)
    assert list_contracts.status_code == status.HTTP_200_OK
    assert list_contracts.json()["items"][0]["id"] == contract_id
    assert contract_detail.status_code == status.HTTP_200_OK
    assert snapshot_response.status_code == status.HTTP_202_ACCEPTED
    assert snapshot_payload["connection_id"] == _CONNECTION_ID
    assert snapshot_payload["named_query_id"] == _QUERY_ID
    assert snapshot_payload["trace_contract_id"] == contract_id
    assert snapshot_payload["status"] == "building"
    assert snapshot_retry.status_code == status.HTTP_202_ACCEPTED
    assert snapshot_retry.json()["id"] == snapshot_id
    assert runner.submitted == [snapshot_id, snapshot_id]
    assert list_snapshots.status_code == status.HTTP_200_OK
    assert list_snapshots.json()["items"][0]["id"] == snapshot_id
    assert snapshot_status.status_code == status.HTTP_200_OK
    assert snapshot_status.json()["status"] == "building"
    assert snapshot_rows.status_code == status.HTTP_409_CONFLICT
    assert snapshot_rows.json()["error"]["code"] == "SNAPSHOT_NOT_READY"


@pytest.mark.asyncio
async def test_trace_contract_validate_returns_canonical_preview() -> None:
    fixture = generate_fixture(QUICK_SPEC)
    query = _seed_query()
    rows = fixture.baseline_run_rows[:_VALIDATION_SAMPLE_SIZE]
    outcome = ExecutionOutcome(
        execution_result=ExecutorResult(
            columns=[],
            rows=cast(list[dict[str, Any]], rows),
            duration_ms=1,
            truncated=True,
        ),
        suggested_field_renders={},
        suggested_trajectory_config=None,
        row_identities=[str(row["row_identity"]) for row in rows],
        executed_at=query.created_at,
        warnings=[],
    )
    fake_service = FakeValidationQueryService(query, outcome)
    app.dependency_overrides[get_query_service] = lambda: fake_service
    transport = httpx.ASGITransport(app=cast(Any, app))
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/trace-contracts/validate",
                json={
                    "named_query_id": _QUERY_ID,
                    "definition": fixture.contracts["run_rows"],
                    "sample_limit": 100,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["valid"] is True
    assert payload["valid_run_count"] == _VALIDATION_SAMPLE_SIZE
    assert payload["canonical_preview"][0]["schema_version"] == "run-row/v1"


@pytest.mark.asyncio
async def test_both_layouts_build_equivalent_snapshots_through_rest() -> None:
    fixture = generate_fixture(QUICK_SPEC)
    _seed_query()
    executor = cast(
        ExecutorService,
        ApiStreamingExecutor(
            {
                _QUERY_ID: fixture.baseline_run_rows,
                _EVENT_QUERY_ID: list(reversed(fixture.baseline_event_rows)),
            }
        ),
    )
    runner = InlineSnapshotRunner(executor, ArtifactStore())
    app.dependency_overrides[get_snapshot_job_runner] = lambda: runner
    transport = httpx.ASGITransport(app=cast(Any, app))
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            run_contract = await client.post(
                "/api/v1/trace-contracts",
                json={
                    "name": "rest-run-layout",
                    "named_query_id": _QUERY_ID,
                    "definition": fixture.contracts["run_rows"],
                },
            )
            event_contract = await client.post(
                "/api/v1/trace-contracts",
                json={
                    "name": "rest-event-layout",
                    "named_query_id": _EVENT_QUERY_ID,
                    "definition": fixture.contracts["event_rows"],
                },
            )
            run_snapshot = await client.post(
                "/api/v1/run-snapshots",
                json={
                    "name": "rest-run-snapshot",
                    "connection_id": _CONNECTION_ID,
                    "named_query_id": _QUERY_ID,
                    "trace_contract_id": run_contract.json()["id"],
                },
            )
            event_snapshot = await client.post(
                "/api/v1/run-snapshots",
                json={
                    "name": "rest-event-snapshot",
                    "connection_id": _CONNECTION_ID,
                    "named_query_id": _EVENT_QUERY_ID,
                    "trace_contract_id": event_contract.json()["id"],
                },
            )
            run_detail = await client.get(f"/api/v1/run-snapshots/{run_snapshot.json()['id']}")
            event_detail = await client.get(f"/api/v1/run-snapshots/{event_snapshot.json()['id']}")
    finally:
        app.dependency_overrides.clear()

    assert run_contract.status_code == event_contract.status_code == status.HTTP_201_CREATED
    assert run_snapshot.status_code == event_snapshot.status_code == status.HTTP_202_ACCEPTED
    assert run_detail.status_code == event_detail.status_code == status.HTTP_200_OK
    assert run_detail.json()["status"] == event_detail.json()["status"] == "ready"
    assert run_detail.json()["content_sha256"] == event_detail.json()["content_sha256"]
