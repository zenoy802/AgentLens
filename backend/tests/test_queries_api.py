from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx
import pytest
from sqlalchemy.orm import Session
from starlette import status

from app.db.session import get_session_factory, initialize_metadata_database
from app.main import app
from app.models.connection import Connection
from app.models.label import LabelRecord, LabelSchema
from app.models.llm import LLMAnalysis
from app.models.misc import QueryHistory
from app.models.named_query import NamedQuery
from app.models.view_config import ViewConfig

HTTP_OK = status.HTTP_200_OK
HTTP_NO_CONTENT = status.HTTP_204_NO_CONTENT
HTTP_CONFLICT = status.HTTP_409_CONFLICT
HTTP_UNPROCESSABLE_ENTITY = status.HTTP_422_UNPROCESSABLE_CONTENT
LEGACY_LIMIT = 2
EXPECTED_LABEL_RECORD_COUNT = 2
EXPECTED_LLM_ANALYSIS_COUNT = 1
EXPECTED_LAST_EXECUTED_ORDER_TOTAL = 3


def _is_utc_iso(value: str) -> bool:
    return value.endswith(("Z", "+00:00"))


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _naive_utc(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC).replace(tzinfo=None)


def _parse_response_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _create_connection(session: Session) -> int:
    connection = Connection(
        name="queries-mysql",
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
    name: str | None,
    is_named: bool,
    expires_at: datetime | None = None,
) -> int:
    query = NamedQuery(
        connection_id=connection_id,
        name=name,
        sql_text="SELECT 1",
        is_named=is_named,
        expires_at=expires_at,
    )
    query.view_config = ViewConfig(field_renders="{}", table_config="{}")
    query.label_schema = LabelSchema(fields="[]")
    session.add(query)
    session.commit()
    return query.id


@pytest.mark.asyncio
async def test_list_filter_is_named() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        named_id = _create_query(
            session,
            connection_id=connection_id,
            name="named",
            is_named=True,
        )
        _create_query(session, connection_id=connection_id, name=None, is_named=False)
    finally:
        session.close()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/queries", params={"is_named": "true"})

    assert response.status_code == HTTP_OK
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert [item["id"] for item in payload["items"]] == [named_id]
    assert payload["items"][0]["is_named"] is True


@pytest.mark.asyncio
async def test_list_includes_connection_name_and_stats() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        query_id = _create_query(
            session,
            connection_id=connection_id,
            name="with-stats",
            is_named=True,
        )
        session.add_all(
            [
                LabelRecord(
                    query_id=query_id,
                    row_identity="row-1",
                    field_key="quality",
                    value='"good"',
                ),
                LabelRecord(
                    query_id=query_id,
                    row_identity="row-2",
                    field_key="quality",
                    value='"bad"',
                ),
                LLMAnalysis(
                    query_id=query_id,
                    provider_id=None,
                    selection="{}",
                    structure_format="json",
                    prompt="Analyze rows",
                    structured_input="[]",
                    response="{}",
                    model_name="test-model",
                    token_usage=None,
                    status="completed",
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/queries", params={"is_named": "true"})

    assert response.status_code == HTTP_OK
    payload = response.json()
    assert payload["items"][0]["id"] == query_id
    assert payload["items"][0]["connection_name"] == "queries-mysql"
    assert payload["items"][0]["label_record_count"] == EXPECTED_LABEL_RECORD_COUNT
    assert payload["items"][0]["llm_analysis_count"] == EXPECTED_LLM_ANALYSIS_COUNT


@pytest.mark.asyncio
async def test_list_can_order_by_last_executed_at() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        old_id = _create_query(
            session,
            connection_id=connection_id,
            name="old",
            is_named=True,
        )
        new_id = _create_query(
            session,
            connection_id=connection_id,
            name="new",
            is_named=True,
        )
        never_run_id = _create_query(
            session,
            connection_id=connection_id,
            name="never-run",
            is_named=True,
        )
        old_query = session.get(NamedQuery, old_id)
        new_query = session.get(NamedQuery, new_id)
        assert old_query is not None
        assert new_query is not None
        old_query.last_executed_at = _now() - timedelta(days=1)
        new_query.last_executed_at = _now()
        session.commit()
    finally:
        session.close()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/v1/queries",
            params={
                "is_named": "true",
                "order_by": "last_executed_at",
                "page_size": LEGACY_LIMIT,
            },
        )

    assert response.status_code == HTTP_OK
    payload = response.json()
    assert payload["pagination"]["total"] == EXPECTED_LAST_EXECUTED_ORDER_TOTAL
    assert [item["id"] for item in payload["items"]] == [new_id, old_id]
    assert never_run_id not in {item["id"] for item in payload["items"]}


@pytest.mark.asyncio
async def test_promote_temp_to_named() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        query_id = _create_query(session, connection_id=connection_id, name=None, is_named=False)
    finally:
        session.close()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            f"/api/v1/queries/{query_id}/promote",
            json={
                "name": "saved-query",
                "description": "Useful query",
                "expires_at": "2026-04-21T00:00:00-07:00",
            },
        )

    assert response.status_code == HTTP_OK
    payload = response.json()
    assert payload["is_named"] is True
    assert payload["name"] == "saved-query"
    assert payload["description"] == "Useful query"
    assert _is_utc_iso(payload["created_at"])
    assert _is_utc_iso(payload["updated_at"])
    assert _is_utc_iso(payload["expires_at"])
    assert _parse_response_datetime(payload["expires_at"]) == datetime(
        2026,
        4,
        21,
        7,
        0,
        tzinfo=UTC,
    )


@pytest.mark.asyncio
async def test_query_expiration_inputs_are_normalized_to_utc_storage() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
    finally:
        session.close()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_response = await client.post(
            "/api/v1/queries",
            json={
                "connection_id": connection_id,
                "name": "tz-query",
                "sql_text": "SELECT 1",
                "expires_at": "2026-04-21T00:00:00-07:00",
            },
        )
        patch_response = await client.patch(
            f"/api/v1/queries/{create_response.json()['id']}",
            json={"expires_at": "2026-04-21T10:30:00+02:00"},
        )

    assert create_response.status_code == status.HTTP_201_CREATED
    create_payload = create_response.json()
    query_id = create_payload["id"]
    assert _parse_response_datetime(create_payload["expires_at"]) == datetime(
        2026,
        4,
        21,
        7,
        0,
        tzinfo=UTC,
    )
    assert patch_response.status_code == HTTP_OK
    patch_payload = patch_response.json()
    assert _parse_response_datetime(patch_payload["expires_at"]) == datetime(
        2026,
        4,
        21,
        8,
        30,
        tzinfo=UTC,
    )

    session = get_session_factory()()
    try:
        query = session.get(NamedQuery, query_id)
        assert query is not None
        assert query.expires_at == _naive_utc(2026, 4, 21, 8, 30)
    finally:
        session.close()


@pytest.mark.asyncio
async def test_promote_name_conflict() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        _create_query(session, connection_id=connection_id, name="existing", is_named=True)
        query_id = _create_query(session, connection_id=connection_id, name=None, is_named=False)
    finally:
        session.close()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            f"/api/v1/queries/{query_id}/promote",
            json={"name": "existing"},
        )

    assert response.status_code == HTTP_CONFLICT
    assert response.json()["error"]["code"] == "QUERY_NAME_CONFLICT"


@pytest.mark.asyncio
async def test_promote_rejects_already_named_query() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        query_id = _create_query(
            session,
            connection_id=connection_id,
            name="already-named",
            is_named=True,
        )
    finally:
        session.close()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            f"/api/v1/queries/{query_id}/promote",
            json={"name": "renamed"},
        )

    assert response.status_code == HTTP_CONFLICT
    assert response.json()["error"]["code"] == "QUERY_ALREADY_NAMED"


@pytest.mark.asyncio
async def test_patch_rejects_invalid_name_transitions() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        named_id = _create_query(
            session,
            connection_id=connection_id,
            name="saved",
            is_named=True,
        )
        temp_id = _create_query(session, connection_id=connection_id, name=None, is_named=False)
    finally:
        session.close()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        null_name_response = await client.patch(
            f"/api/v1/queries/{named_id}",
            json={"name": None},
        )
        temp_name_response = await client.patch(
            f"/api/v1/queries/{temp_id}",
            json={"name": "should-use-promote"},
        )
        sql_text_response = await client.patch(
            f"/api/v1/queries/{named_id}",
            json={"sql_text": "SELECT 2"},
        )

    assert null_name_response.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert temp_name_response.status_code == HTTP_CONFLICT
    assert temp_name_response.json()["error"]["code"] == "QUERY_TEMPORARY_NAME_UPDATE_FORBIDDEN"
    assert sql_text_response.status_code == HTTP_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_delete_cascade_to_history() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        query_id = _create_query(session, connection_id=connection_id, name="saved", is_named=True)
        history = QueryHistory(
            connection_id=connection_id,
            query_id=query_id,
            sql_text="SELECT 1",
            row_count=1,
            duration_ms=2,
            status="success",
            executed_at=_now(),
        )
        session.add(history)
        session.commit()
        history_id = history.id
    finally:
        session.close()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.delete(f"/api/v1/queries/{query_id}")

    assert response.status_code == HTTP_NO_CONTENT

    session = get_session_factory()()
    try:
        persisted_history = session.get(QueryHistory, history_id)
        assert persisted_history is not None
        assert persisted_history.query_id is None
    finally:
        session.close()


@pytest.mark.asyncio
async def test_list_excludes_expired_by_default() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        expired_id = _create_query(
            session,
            connection_id=connection_id,
            name="expired",
            is_named=True,
            expires_at=_now() - timedelta(days=1),
        )
        active_id = _create_query(
            session,
            connection_id=connection_id,
            name="active",
            is_named=True,
            expires_at=_now() + timedelta(days=1),
        )
    finally:
        session.close()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        default_response = await client.get("/api/v1/queries")
        include_response = await client.get(
            "/api/v1/queries",
            params={"include_expired": "true"},
        )

    assert default_response.status_code == HTTP_OK
    default_ids = {item["id"] for item in default_response.json()["items"]}
    assert active_id in default_ids
    assert expired_id not in default_ids

    assert include_response.status_code == HTTP_OK
    include_ids = {item["id"] for item in include_response.json()["items"]}
    assert {active_id, expired_id}.issubset(include_ids)


@pytest.mark.asyncio
async def test_query_history_paginates_filters_and_sorts() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        first_connection_id = _create_connection(session)
        second_connection = Connection(
            name="other-mysql",
            db_type="mysql",
            database="agent_logs",
            default_timeout=30,
            default_row_limit=10000,
        )
        session.add(second_connection)
        session.commit()
        second_connection_id = second_connection.id

        session.add_all(
            [
                QueryHistory(
                    connection_id=first_connection_id,
                    query_id=None,
                    sql_text="SELECT old",
                    row_count=1,
                    duration_ms=10,
                    status="success",
                    executed_at=_now() - timedelta(minutes=2),
                ),
                QueryHistory(
                    connection_id=first_connection_id,
                    query_id=None,
                    sql_text="SELECT newest",
                    row_count=1,
                    duration_ms=8,
                    status="success",
                    executed_at=_now(),
                ),
                QueryHistory(
                    connection_id=second_connection_id,
                    query_id=None,
                    sql_text="SELECT other",
                    row_count=1,
                    duration_ms=5,
                    status="success",
                    executed_at=_now() + timedelta(minutes=1),
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/v1/query-history",
            params={"connection_id": first_connection_id, "page_size": 1},
        )
        legacy_limit_response = await client.get(
            "/api/v1/query-history",
            params={"connection_id": first_connection_id, "limit": LEGACY_LIMIT},
        )

    assert response.status_code == HTTP_OK
    payload = response.json()
    assert payload["pagination"] == {
        "page": 1,
        "page_size": 1,
        "total": 2,
        "total_pages": 2,
    }
    assert [item["sql_text"] for item in payload["items"]] == ["SELECT newest"]
    assert payload["items"][0]["connection_id"] == first_connection_id

    assert legacy_limit_response.status_code == HTTP_OK
    assert legacy_limit_response.json()["pagination"]["page_size"] == LEGACY_LIMIT
    assert [item["sql_text"] for item in legacy_limit_response.json()["items"]] == [
        "SELECT newest",
        "SELECT old",
    ]
