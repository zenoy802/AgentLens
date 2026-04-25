from __future__ import annotations

import logging
from typing import Any, cast

import httpx
import pytest
from loguru import logger
from sqlalchemy.orm import Session
from starlette import status

from app.db.session import get_session_factory, initialize_metadata_database
from app.main import app
from app.models.connection import Connection
from app.models.label import LabelSchema
from app.models.named_query import NamedQuery
from app.models.view_config import ViewConfig

HTTP_OK = status.HTTP_200_OK
HTTP_NOT_FOUND = status.HTTP_404_NOT_FOUND
HTTP_UNPROCESSABLE_ENTITY = status.HTTP_422_UNPROCESSABLE_CONTENT


def _create_connection(session: Session) -> int:
    connection = Connection(
        name="view-config-mysql",
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


def _create_query(
    session: Session,
    *,
    connection_id: int,
    with_view_config: bool = True,
    row_identity_column: str | None = None,
) -> int:
    query = NamedQuery(
        connection_id=connection_id,
        name=None,
        sql_text="SELECT 1",
        is_named=False,
    )
    if with_view_config:
        query.view_config = ViewConfig(
            field_renders="{}",
            table_config="{}",
            row_identity_column=row_identity_column,
        )
    query.label_schema = LabelSchema(fields="[]")
    session.add(query)
    session.commit()
    return query.id


def _roundtrip_payload(row_identity_column: str = "id") -> dict[str, object]:
    return {
        "field_renders": {
            "content": {"type": "markdown"},
            "tool_calls": {"type": "json", "collapsed": True},
            "sql_query": {"type": "code", "language": "sql"},
            "created_at": {
                "type": "timestamp",
                "format": "YYYY-MM-DD HH:mm:ss",
            },
        },
        "table_config": {
            "column_widths": {"content": 600},
            "hidden_columns": ["internal_id"],
            "frozen_columns": ["session_id"],
            "sort": [{"column": "created_at", "direction": "asc"}],
        },
        "trajectory_config": {
            "group_by": "session_id",
            "role_column": "role",
            "content_column": "content",
            "tool_calls_column": "tool_calls",
            "order_by": "created_at",
            "order_direction": "asc",
        },
        "row_identity_column": row_identity_column,
    }


def _assert_view_config_matches_payload(
    response_payload: dict[str, object],
    expected_payload: dict[str, object],
) -> None:
    assert response_payload["field_renders"] == expected_payload["field_renders"]
    assert response_payload["table_config"] == expected_payload["table_config"]
    assert response_payload["trajectory_config"] == expected_payload["trajectory_config"]
    assert response_payload["row_identity_column"] == expected_payload["row_identity_column"]


def _prepare_query(*, with_view_config: bool = True) -> int:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        return _create_query(
            session,
            connection_id=connection_id,
            with_view_config=with_view_config,
        )
    finally:
        session.close()


@pytest.mark.asyncio
async def test_get_default_empty_view_config() -> None:
    query_id = _prepare_query()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/v1/queries/{query_id}/view-config")

    assert response.status_code == HTTP_OK
    payload = response.json()
    assert payload["query_id"] == query_id
    assert payload["field_renders"] == {}
    assert payload["table_config"] == {
        "column_widths": {},
        "hidden_columns": [],
        "frozen_columns": [],
        "sort": [],
    }
    assert payload["trajectory_config"] is None
    assert payload["row_identity_column"] is None
    assert isinstance(payload["updated_at"], str)


@pytest.mark.asyncio
async def test_get_creates_missing_view_config_for_legacy_query() -> None:
    query_id = _prepare_query(with_view_config=False)

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/v1/queries/{query_id}/view-config")

    assert response.status_code == HTTP_OK
    assert response.json()["field_renders"] == {}

    session = get_session_factory()()
    try:
        view_config = session.query(ViewConfig).filter_by(query_id=query_id).one_or_none()
        assert view_config is not None
    finally:
        session.close()


@pytest.mark.asyncio
async def test_get_query_not_found() -> None:
    initialize_metadata_database()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/queries/99999/view-config")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_put_then_get_roundtrip() -> None:
    query_id = _prepare_query()
    payload = _roundtrip_payload()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        put_response = await client.put(
            f"/api/v1/queries/{query_id}/view-config",
            json=payload,
        )
        get_response = await client.get(f"/api/v1/queries/{query_id}/view-config")

    assert put_response.status_code == HTTP_OK
    assert get_response.status_code == HTTP_OK
    _assert_view_config_matches_payload(put_response.json(), payload)
    _assert_view_config_matches_payload(get_response.json(), payload)


@pytest.mark.asyncio
async def test_put_discriminator_validation() -> None:
    query_id = _prepare_query()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            f"/api/v1/queries/{query_id}/view-config",
            json={
                "field_renders": {"content": {"type": "invalid"}},
                "table_config": {},
                "trajectory_config": None,
                "row_identity_column": None,
            },
        )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert "field_renders" in str(payload["error"]["detail"])


@pytest.mark.asyncio
async def test_put_label_field_type_enum_validation() -> None:
    query_id = _prepare_query()
    payload = _roundtrip_payload()
    trajectory_config = cast(dict[str, object], payload["trajectory_config"])
    trajectory_config["order_direction"] = "random"

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            f"/api/v1/queries/{query_id}/view-config",
            json=payload,
        )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_put_overwrites_not_merges() -> None:
    query_id = _prepare_query()
    payload_a: dict[str, object] = {
        "field_renders": {
            "a": {"type": "markdown"},
            "b": {"type": "json", "collapsed": True},
        },
        "table_config": {},
        "trajectory_config": None,
        "row_identity_column": None,
    }
    payload_b: dict[str, object] = {
        "field_renders": {"c": {"type": "text"}},
        "table_config": {},
        "trajectory_config": None,
        "row_identity_column": None,
    }

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        first_response = await client.put(
            f"/api/v1/queries/{query_id}/view-config",
            json=payload_a,
        )
        second_response = await client.put(
            f"/api/v1/queries/{query_id}/view-config",
            json=payload_b,
        )
        get_response = await client.get(f"/api/v1/queries/{query_id}/view-config")

    assert first_response.status_code == HTTP_OK
    assert second_response.status_code == HTTP_OK
    assert get_response.status_code == HTTP_OK
    assert get_response.json()["field_renders"] == {"c": {"type": "text"}}


@pytest.mark.asyncio
async def test_put_trajectory_config_null() -> None:
    query_id = _prepare_query()
    payload = _roundtrip_payload()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        first_response = await client.put(
            f"/api/v1/queries/{query_id}/view-config",
            json=payload,
        )
        payload["trajectory_config"] = None
        second_response = await client.put(
            f"/api/v1/queries/{query_id}/view-config",
            json=payload,
        )
        get_response = await client.get(f"/api/v1/queries/{query_id}/view-config")

    assert first_response.status_code == HTTP_OK
    assert second_response.status_code == HTTP_OK
    assert get_response.status_code == HTTP_OK
    assert get_response.json()["trajectory_config"] is None


@pytest.mark.asyncio
async def test_put_emits_row_identity_change_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        query_id = _create_query(
            session,
            connection_id=connection_id,
            row_identity_column="id",
        )
    finally:
        session.close()

    payload = _roundtrip_payload(row_identity_column="message_id")
    handler_id = logger.add(caplog.handler, level="WARNING", format="{message}")
    caplog.set_level(logging.WARNING)
    try:
        transport = httpx.ASGITransport(app=cast(Any, app))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.put(
                f"/api/v1/queries/{query_id}/view-config",
                json=payload,
            )
    finally:
        logger.remove(handler_id)

    assert response.status_code == HTTP_OK
    assert "row_identity_column changed for query" in caplog.text
    assert "'id'" in caplog.text
    assert "'message_id'" in caplog.text
