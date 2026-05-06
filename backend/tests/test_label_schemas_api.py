from __future__ import annotations

from typing import Any, cast

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette import status

from app.db.session import get_session_factory, initialize_metadata_database
from app.main import app
from app.models.connection import Connection
from app.models.label import LabelRecord
from app.services.query_executor import ExecutorService
from app.services.query_service import QueryService

HTTP_OK = status.HTTP_200_OK
HTTP_UNPROCESSABLE_ENTITY = status.HTTP_422_UNPROCESSABLE_CONTENT
EXPECTED_CASCADE_DELETED_RECORDS = 2


def _create_connection(session: Session) -> int:
    connection = Connection(
        name="label-schema-mysql",
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


def _create_temporary_query() -> int:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        query_service = QueryService(session, cast(ExecutorService, object()))
        query = query_service.create_temporary_query(connection_id, "SELECT 1")
        return query.id
    finally:
        session.close()


def _single_select_schema() -> dict[str, object]:
    return {
        "fields": [
            {
                "key": "quality",
                "label": "质量",
                "type": "single_select",
                "options": [
                    {"value": "good", "label": "好", "color": "#10b981"},
                    {"value": "bad", "label": "差", "color": "#ef4444"},
                ],
            }
        ]
    }


@pytest.mark.asyncio
async def test_new_query_has_empty_label_schema() -> None:
    query_id = _create_temporary_query()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/v1/queries/{query_id}/label-schema")

    assert response.status_code == HTTP_OK
    payload = response.json()
    assert payload["query_id"] == query_id
    assert payload["fields"] == []
    assert payload["cascade_deleted_records"] == 0
    assert isinstance(payload["updated_at"], str)


@pytest.mark.asyncio
async def test_put_adds_field_and_get_roundtrip() -> None:
    query_id = _create_temporary_query()
    payload = _single_select_schema()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        put_response = await client.put(
            f"/api/v1/queries/{query_id}/label-schema",
            json=payload,
        )
        get_response = await client.get(f"/api/v1/queries/{query_id}/label-schema")

    assert put_response.status_code == HTTP_OK
    assert get_response.status_code == HTTP_OK
    assert put_response.json()["fields"] == payload["fields"]
    assert put_response.json()["cascade_deleted_records"] == 0
    assert get_response.json()["fields"] == payload["fields"]


@pytest.mark.asyncio
async def test_put_removes_field_and_cascades_records() -> None:
    query_id = _create_temporary_query()
    initial_payload: dict[str, object] = {
        "fields": [
            {
                "key": "quality",
                "label": "质量",
                "type": "single_select",
                "options": [{"value": "good", "label": "好"}],
            },
            {
                "key": "note",
                "label": "备注",
                "type": "text",
            },
        ]
    }
    initial_fields = cast(list[dict[str, object]], initial_payload["fields"])

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_schema_response = await client.put(
            f"/api/v1/queries/{query_id}/label-schema",
            json=initial_payload,
        )

    assert create_schema_response.status_code == HTTP_OK

    session = get_session_factory()()
    try:
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
                    row_identity="row-1",
                    field_key="note",
                    value='"keep"',
                ),
                LabelRecord(
                    query_id=query_id,
                    row_identity="row-2",
                    field_key="quality",
                    value='"good"',
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            f"/api/v1/queries/{query_id}/label-schema",
            json={"fields": [initial_fields[1]]},
        )

    assert response.status_code == HTTP_OK
    assert response.json()["fields"] == [initial_fields[1]]
    assert response.json()["cascade_deleted_records"] == EXPECTED_CASCADE_DELETED_RECORDS

    session = get_session_factory()()
    try:
        assert (
            session.scalar(
                select(func.count())
                .select_from(LabelRecord)
                .where(LabelRecord.query_id == query_id)
            )
            == 1
        )
        remaining = session.scalars(
            select(LabelRecord).where(LabelRecord.query_id == query_id)
        ).one()
        assert remaining.field_key == "note"
    finally:
        session.close()


@pytest.mark.asyncio
async def test_put_rejects_duplicate_field_key() -> None:
    query_id = _create_temporary_query()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            f"/api/v1/queries/{query_id}/label-schema",
            json={
                "fields": [
                    {"key": "quality", "label": "质量", "type": "text"},
                    {"key": "quality", "label": "质量 2", "type": "text"},
                ]
            },
        )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert response.json()["error"]["code"] == "LABEL_SCHEMA_DUPLICATE_FIELD_KEY"


@pytest.mark.asyncio
async def test_put_rejects_empty_options() -> None:
    query_id = _create_temporary_query()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            f"/api/v1/queries/{query_id}/label-schema",
            json={
                "fields": [
                    {
                        "key": "quality",
                        "label": "质量",
                        "type": "single_select",
                        "options": [],
                    }
                ]
            },
        )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert response.json()["error"]["code"] == "LABEL_SCHEMA_OPTIONS_REQUIRED"


@pytest.mark.asyncio
async def test_put_rejects_duplicate_option_value() -> None:
    query_id = _create_temporary_query()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            f"/api/v1/queries/{query_id}/label-schema",
            json={
                "fields": [
                    {
                        "key": "quality",
                        "label": "质量",
                        "type": "multi_select",
                        "options": [
                            {"value": "bad", "label": "差"},
                            {"value": "bad", "label": "不好"},
                        ],
                    }
                ]
            },
        )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert response.json()["error"]["code"] == "LABEL_SCHEMA_DUPLICATE_OPTION_VALUE"
