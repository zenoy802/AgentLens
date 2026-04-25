from __future__ import annotations

import json
from typing import Any, cast

import httpx
import pytest
from sqlalchemy.orm import Session
from starlette import status

from app.core.sql_guard import validate_sql
from app.db.session import get_session_factory, initialize_metadata_database
from app.main import app
from app.models.connection import Connection
from app.models.label import LabelSchema
from app.models.misc import QueryHistory
from app.models.named_query import NamedQuery
from app.models.view_config import ViewConfig
from app.services.query_executor import Column, ExecutorResult, ExecutorService

HTTP_OK = status.HTTP_200_OK
HTTP_BAD_REQUEST = status.HTTP_400_BAD_REQUEST
DEFAULT_TIMEOUT = 30
DEFAULT_ROW_LIMIT = 10000
EXPECTED_TWO = 2


def _create_connection(session: Session) -> int:
    connection = Connection(
        name="trajectory-mysql",
        db_type="mysql",
        host="db.example.com",
        port=3306,
        database="agent_logs",
        username="reader",
        default_timeout=30,
        default_row_limit=10000,
    )
    session.add(connection)
    session.commit()
    return connection.id


def _trajectory_config(**overrides: object) -> dict[str, object]:
    config: dict[str, object] = {
        "group_by": "session_id",
        "role_column": "role",
        "content_column": "content",
        "tool_calls_column": "tool_calls",
        "order_by": "created_at",
        "order_direction": "asc",
    }
    config.update(overrides)
    return config


def _create_query(
    session: Session,
    *,
    connection_id: int,
    trajectory_config: dict[str, object] | None = None,
    row_identity_column: str | None = None,
) -> int:
    query = NamedQuery(
        connection_id=connection_id,
        name=None,
        sql_text="SELECT session_id, role, content FROM messages",
        is_named=False,
    )
    query.view_config = ViewConfig(
        field_renders="{}",
        table_config="{}",
        trajectory_config=(None if trajectory_config is None else json.dumps(trajectory_config)),
        row_identity_column=row_identity_column,
    )
    query.label_schema = LabelSchema(fields="[]")
    session.add(query)
    session.commit()
    return query.id


def _patch_executor(
    monkeypatch: pytest.MonkeyPatch,
    result: ExecutorResult,
) -> None:
    def fake_execute(
        self: ExecutorService,
        connection: Connection,
        sql: str,
        *,
        timeout: int,
        row_limit: int,
    ) -> ExecutorResult:
        assert isinstance(self, ExecutorService)
        assert connection.id > 0
        assert timeout == DEFAULT_TIMEOUT
        assert row_limit == DEFAULT_ROW_LIMIT
        validate_sql(sql)
        return result

    monkeypatch.setattr(ExecutorService, "execute", fake_execute)


@pytest.mark.asyncio
async def test_aggregate_trajectories_with_saved_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        query_id = _create_query(
            session,
            connection_id=connection_id,
            trajectory_config=_trajectory_config(),
        )
    finally:
        session.close()

    _patch_executor(
        monkeypatch,
        ExecutorResult(
            columns=[
                Column(name="session_id", sql_type="VAR_STRING", inferred_type="text"),
                Column(name="role", sql_type="VAR_STRING", inferred_type="text"),
                Column(name="content", sql_type="VAR_STRING", inferred_type="text"),
                Column(name="tool_calls", sql_type="JSON", inferred_type="json"),
                Column(name="created_at", sql_type="LONGLONG", inferred_type="integer"),
            ],
            rows=[
                {
                    "session_id": "s1",
                    "role": "assistant",
                    "content": "second",
                    "tool_calls": '[{"name": "search"}]',
                    "created_at": 2,
                },
                {
                    "session_id": "s1",
                    "role": "user",
                    "content": "first",
                    "tool_calls": None,
                    "created_at": 1,
                },
            ],
            duration_ms=5,
            truncated=False,
        ),
    )

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(f"/api/v1/queries/{query_id}/trajectories")

    assert response.status_code == HTTP_OK
    payload = response.json()
    assert payload["warnings"] == []
    assert len(payload["trajectories"]) == 1
    trajectory = payload["trajectories"][0]
    assert trajectory["group_key"] == "s1"
    assert [message["role"] for message in trajectory["messages"]] == ["user", "assistant"]
    assert trajectory["messages"][1]["tool_calls"] == [{"name": "search"}]

    session = get_session_factory()()
    try:
        query = session.get(NamedQuery, query_id)
        assert query is not None
        assert query.last_executed_at is None
        assert session.query(QueryHistory).count() == 0
    finally:
        session.close()


@pytest.mark.asyncio
async def test_aggregate_trajectories_missing_saved_config_returns_400() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        query_id = _create_query(session, connection_id=connection_id)
    finally:
        session.close()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(f"/api/v1/queries/{query_id}/trajectories")

    assert response.status_code == HTTP_BAD_REQUEST
    assert response.json()["error"]["code"] == "TRAJECTORY_CONFIG_MISSING"


@pytest.mark.asyncio
async def test_aggregate_trajectories_with_inline_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        query_id = _create_query(session, connection_id=connection_id)
    finally:
        session.close()

    _patch_executor(
        monkeypatch,
        ExecutorResult(
            columns=[
                Column(name="session_id", sql_type="VAR_STRING", inferred_type="text"),
                Column(name="role", sql_type="VAR_STRING", inferred_type="text"),
                Column(name="content", sql_type="VAR_STRING", inferred_type="text"),
            ],
            rows=[
                {"session_id": "s1", "role": None, "content": "system"},
                {"session_id": "s2", "role": "user", "content": "hello"},
            ],
            duration_ms=5,
            truncated=False,
        ),
    )

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            f"/api/v1/queries/{query_id}/trajectories",
            json={"use_saved_config": False, "trajectory_config": _trajectory_config()},
        )

    assert response.status_code == HTTP_OK
    payload = response.json()
    assert len(payload["trajectories"]) == EXPECTED_TWO
    assert payload["trajectories"][0]["messages"][0]["role"] == "unknown"
    assert payload["warnings"][0]["code"] == "MISSING_ROLE_COLUMN"


@pytest.mark.asyncio
async def test_aggregate_trajectories_preserves_user_row_identity_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        query_id = _create_query(
            session,
            connection_id=connection_id,
            trajectory_config=_trajectory_config(
                role_column="_row_identity",
                tool_calls_column=None,
                order_by=None,
            ),
        )
    finally:
        session.close()

    _patch_executor(
        monkeypatch,
        ExecutorResult(
            columns=[
                Column(name="session_id", sql_type="VAR_STRING", inferred_type="text"),
                Column(name="_row_identity", sql_type="VAR_STRING", inferred_type="text"),
                Column(name="content", sql_type="VAR_STRING", inferred_type="text"),
            ],
            rows=[
                {
                    "session_id": "s1",
                    "_row_identity": "user-owned-value",
                    "content": "hello",
                }
            ],
            duration_ms=5,
            truncated=False,
        ),
    )

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(f"/api/v1/queries/{query_id}/trajectories")

    assert response.status_code == HTTP_OK
    payload = response.json()
    message = payload["trajectories"][0]["messages"][0]
    assert message["role"] == "user-owned-value"
    assert message["raw"]["_row_identity"] == "user-owned-value"
    assert "_agent_lens_row_identity" not in message["raw"]
    assert any(
        warning["code"] == "ROW_IDENTITY_KEY_COLLISION"
        and warning["detail"]["fallback_key"] == "_agent_lens_row_identity"
        for warning in payload["warnings"]
    )


@pytest.mark.asyncio
async def test_aggregate_trajectories_propagates_readonly_execution_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        query_id = _create_query(
            session,
            connection_id=connection_id,
            trajectory_config=_trajectory_config(tool_calls_column=None, order_by=None),
            row_identity_column="missing_id",
        )
    finally:
        session.close()

    _patch_executor(
        monkeypatch,
        ExecutorResult(
            columns=[
                Column(name="session_id", sql_type="VAR_STRING", inferred_type="text"),
                Column(name="role", sql_type="VAR_STRING", inferred_type="text"),
                Column(name="content", sql_type="VAR_STRING", inferred_type="text"),
            ],
            rows=[{"session_id": "s1", "role": "user", "content": "hello"}],
            duration_ms=5,
            truncated=True,
        ),
    )

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(f"/api/v1/queries/{query_id}/trajectories")

    assert response.status_code == HTTP_OK
    warning_codes = {warning["code"] for warning in response.json()["warnings"]}
    assert "ROW_IDENTITY_COLUMN_MISSING" in warning_codes
    assert "RESULT_TRUNCATED" in warning_codes
