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
from app.models.misc import GlobalRenderRule, QueryHistory
from app.models.named_query import NamedQuery
from app.models.view_config import ViewConfig
from app.services.query_executor import Column, ExecutorResult, ExecutorService
from app.services.row_identity_service import compute

HTTP_OK = status.HTTP_200_OK
HTTP_BAD_REQUEST = status.HTTP_400_BAD_REQUEST


def _is_utc_iso(value: str) -> bool:
    return value.endswith(("Z", "+00:00"))


def _create_connection(session: Session) -> int:
    connection = Connection(
        name="test-mysql",
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
        assert timeout > 0
        assert row_limit > 0
        validate_sql(sql)
        return result

    monkeypatch.setattr(ExecutorService, "execute", fake_execute)


@pytest.mark.asyncio
async def test_execute_creates_temporary_query(monkeypatch: pytest.MonkeyPatch) -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
    finally:
        session.close()

    _patch_executor(
        monkeypatch,
        ExecutorResult(
            columns=[Column(name="a", sql_type="LONGLONG", inferred_type="integer")],
            rows=[{"a": 1}],
            duration_ms=5,
            truncated=False,
        ),
    )

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/execute",
            json={"connection_id": connection_id, "sql": "SELECT 1 AS a"},
        )

    assert response.status_code == HTTP_OK
    payload = response.json()
    assert payload["is_temporary"] is True
    assert payload["query_id"] > 0
    assert _is_utc_iso(payload["execution"]["executed_at"])
    assert payload["rows"][0]["a"] == 1
    assert "_row_identity" in payload["rows"][0]

    session = get_session_factory()()
    try:
        query = session.get(NamedQuery, payload["query_id"])
        assert query is not None
        assert query.connection_id == connection_id
        assert query.is_named is False
        assert query.name is None
        assert query.expires_at is not None
        assert query.view_config is not None
        assert query.label_schema is not None
    finally:
        session.close()


@pytest.mark.asyncio
async def test_execute_returns_row_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    initialize_metadata_database()
    hash_row = {"message_id": "m-1", "content": "hello"}
    _patch_executor(
        monkeypatch,
        ExecutorResult(
            columns=[
                Column(name="message_id", sql_type="VAR_STRING", inferred_type="text"),
                Column(name="content", sql_type="VAR_STRING", inferred_type="text"),
            ],
            rows=[hash_row],
            duration_ms=5,
            truncated=False,
        ),
    )

    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
    finally:
        session.close()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        hash_response = await client.post(
            "/api/v1/execute",
            json={"connection_id": connection_id, "sql": "SELECT message_id, content FROM t"},
        )

    assert hash_response.status_code == HTTP_OK
    assert hash_response.json()["rows"][0]["_row_identity"] == compute(hash_row, None)

    session = get_session_factory()()
    try:
        query = NamedQuery(
            connection_id=connection_id,
            name=None,
            sql_text="SELECT message_id, content FROM t",
            is_named=False,
        )
        query.view_config = ViewConfig(
            field_renders="{}",
            table_config="{}",
            row_identity_column="message_id",
        )
        query.label_schema = LabelSchema(fields="[]")
        session.add(query)
        session.commit()
        query_id = query.id
    finally:
        session.close()

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        column_response = await client.post(f"/api/v1/queries/{query_id}/execute")

    assert column_response.status_code == HTTP_OK
    assert column_response.json()["is_temporary"] is True
    assert column_response.json()["rows"][0]["_row_identity"] == "m-1"


@pytest.mark.asyncio
async def test_execute_warns_for_row_identity_missing_and_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialize_metadata_database()
    _patch_executor(
        monkeypatch,
        ExecutorResult(
            columns=[
                Column(name="message_id", sql_type="VAR_STRING", inferred_type="text"),
                Column(name="content", sql_type="VAR_STRING", inferred_type="text"),
            ],
            rows=[
                {"message_id": "duplicate", "content": "one"},
                {"message_id": "duplicate", "content": "two"},
            ],
            duration_ms=5,
            truncated=False,
        ),
    )

    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        query = NamedQuery(
            connection_id=connection_id,
            name=None,
            sql_text="SELECT message_id, content FROM t",
            is_named=False,
        )
        query.view_config = ViewConfig(
            field_renders="{}",
            table_config="{}",
            row_identity_column="missing_id",
        )
        query.label_schema = LabelSchema(fields="[]")
        session.add(query)
        session.commit()
        query_id = query.id
    finally:
        session.close()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        missing_response = await client.post(f"/api/v1/queries/{query_id}/execute")

    assert missing_response.status_code == HTTP_OK
    missing_warnings = missing_response.json()["warnings"]
    assert any(
        warning["code"] == "ROW_IDENTITY_COLUMN_MISSING"
        and warning["detail"] == {"row_identity_column": "missing_id"}
        for warning in missing_warnings
    )

    session = get_session_factory()()
    try:
        view_config = session.query(ViewConfig).filter_by(query_id=query_id).one()
        view_config.row_identity_column = "message_id"
        session.commit()
    finally:
        session.close()

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        duplicate_response = await client.post(f"/api/v1/queries/{query_id}/execute")

    assert duplicate_response.status_code == HTTP_OK
    duplicate_warnings = duplicate_response.json()["warnings"]
    assert any(warning["code"] == "ROW_IDENTITY_DUPLICATE" for warning in duplicate_warnings)


@pytest.mark.asyncio
async def test_execute_uses_fallback_identity_key_on_column_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
    finally:
        session.close()

    _patch_executor(
        monkeypatch,
        ExecutorResult(
            columns=[
                Column(name="_row_identity", sql_type="VAR_STRING", inferred_type="text"),
                Column(
                    name="_agent_lens_row_identity",
                    sql_type="VAR_STRING",
                    inferred_type="text",
                ),
                Column(name="a", sql_type="LONGLONG", inferred_type="integer"),
            ],
            rows=[
                {
                    "_row_identity": "user-value",
                    "_agent_lens_row_identity": "also-user-value",
                    "a": 1,
                }
            ],
            duration_ms=5,
            truncated=False,
        ),
    )

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/execute",
            json={"connection_id": connection_id, "sql": "SELECT _row_identity, a FROM t"},
        )

    assert response.status_code == HTTP_OK
    row = response.json()["rows"][0]
    assert row["_row_identity"] == "user-value"
    assert row["_agent_lens_row_identity"] == "also-user-value"
    assert "_agent_lens_row_identity_2" in row
    assert any(
        warning["code"] == "ROW_IDENTITY_KEY_COLLISION"
        and warning["detail"]["fallback_key"] == "_agent_lens_row_identity_2"
        for warning in response.json()["warnings"]
    )


@pytest.mark.asyncio
async def test_execute_applies_suggested_renders(monkeypatch: pytest.MonkeyPatch) -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        session.add(
            GlobalRenderRule(
                match_pattern="content",
                match_type="exact",
                render_config=json.dumps({"type": "markdown"}),
                priority=100,
                enabled=True,
            )
        )
        session.commit()
    finally:
        session.close()

    _patch_executor(
        monkeypatch,
        ExecutorResult(
            columns=[Column(name="content", sql_type="VAR_STRING", inferred_type="text")],
            rows=[{"content": "**hello**"}],
            duration_ms=5,
            truncated=False,
        ),
    )

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/execute",
            json={"connection_id": connection_id, "sql": "SELECT content FROM t"},
        )

    assert response.status_code == HTTP_OK
    assert response.json()["suggested_field_renders"]["content"]["type"] == "markdown"


@pytest.mark.asyncio
async def test_execute_applies_suggested_trajectory_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        session.add_all(
            [
                GlobalRenderRule(
                    match_pattern="session_id",
                    match_type="exact",
                    render_config=json.dumps({"type": "trajectory_config", "field": "group_by"}),
                    priority=100,
                    enabled=True,
                ),
                GlobalRenderRule(
                    match_pattern="role",
                    match_type="exact",
                    render_config=json.dumps({"type": "trajectory_config", "field": "role_column"}),
                    priority=100,
                    enabled=True,
                ),
                GlobalRenderRule(
                    match_pattern="content",
                    match_type="exact",
                    render_config=json.dumps(
                        {"type": "trajectory_config", "field": "content_column"}
                    ),
                    priority=100,
                    enabled=True,
                ),
                GlobalRenderRule(
                    match_pattern="created_at",
                    match_type="exact",
                    render_config=json.dumps(
                        {
                            "type": "trajectory_config",
                            "field": "order_by",
                            "order_direction": "desc",
                        }
                    ),
                    priority=90,
                    enabled=True,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    _patch_executor(
        monkeypatch,
        ExecutorResult(
            columns=[
                Column(name="session_id", sql_type="VAR_STRING", inferred_type="text"),
                Column(name="role", sql_type="VAR_STRING", inferred_type="text"),
                Column(name="content", sql_type="TEXT", inferred_type="text"),
                Column(name="created_at", sql_type="DATETIME", inferred_type="timestamp"),
            ],
            rows=[
                {
                    "session_id": "s1",
                    "role": "user",
                    "content": "hello",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ],
            duration_ms=5,
            truncated=False,
        ),
    )

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/execute",
            json={"connection_id": connection_id, "sql": "SELECT session_id, role, content FROM t"},
        )

    assert response.status_code == HTTP_OK
    assert response.json()["suggested_trajectory_config"] == {
        "group_by": "session_id",
        "role_column": "role",
        "content_column": "content",
        "tool_calls_column": None,
        "order_by": "created_at",
        "order_direction": "desc",
    }


@pytest.mark.asyncio
async def test_execute_truncation_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
    finally:
        session.close()

    _patch_executor(
        monkeypatch,
        ExecutorResult(
            columns=[Column(name="a", sql_type="LONGLONG", inferred_type="integer")],
            rows=[{"a": 1}],
            duration_ms=5,
            truncated=True,
        ),
    )

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/execute",
            json={"connection_id": connection_id, "sql": "SELECT a FROM t"},
        )

    assert response.status_code == HTTP_OK
    assert any(warning["code"] == "RESULT_TRUNCATED" for warning in response.json()["warnings"])


@pytest.mark.asyncio
async def test_execute_forbidden_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
    finally:
        session.close()

    _patch_executor(
        monkeypatch,
        ExecutorResult(
            columns=[],
            rows=[],
            duration_ms=0,
            truncated=False,
        ),
    )

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/execute",
            json={"connection_id": connection_id, "sql": "DELETE FROM t"},
        )

    assert response.status_code == HTTP_BAD_REQUEST
    assert response.json()["error"]["code"] == "SQL_FORBIDDEN_STATEMENT"

    session = get_session_factory()()
    try:
        assert session.query(NamedQuery).count() == 0
        history = session.query(QueryHistory).one()
        assert history.status == "failed"
        assert history.query_id is None
    finally:
        session.close()
