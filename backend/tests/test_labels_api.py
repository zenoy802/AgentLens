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
HTTP_BAD_REQUEST = status.HTTP_400_BAD_REQUEST
HTTP_NO_CONTENT = status.HTTP_204_NO_CONTENT
HTTP_NOT_FOUND = status.HTTP_404_NOT_FOUND
EXPECTED_BATCH_AFFECTED = 2


def _create_connection(session: Session) -> int:
    connection = Connection(
        name="labels-mysql",
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


def _label_schema() -> dict[str, object]:
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
            },
            {
                "key": "issues",
                "label": "问题",
                "type": "multi_select",
                "options": [
                    {"value": "hallucination", "label": "幻觉"},
                    {"value": "format_error", "label": "格式错误"},
                ],
            },
            {
                "key": "note",
                "label": "备注",
                "type": "text",
            },
        ]
    }


async def _put_schema(client: httpx.AsyncClient, query_id: int) -> None:
    response = await client.put(
        f"/api/v1/queries/{query_id}/label-schema",
        json=_label_schema(),
    )
    assert response.status_code == HTTP_OK


@pytest.mark.asyncio
async def test_upsert_inserts_updates_and_deletes_label_record() -> None:
    query_id = _create_temporary_query()
    transport = httpx.ASGITransport(app=cast(Any, app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        await _put_schema(client, query_id)
        insert_response = await client.post(
            f"/api/v1/queries/{query_id}/labels",
            json={
                "row_identity": "row-1",
                "field_key": "quality",
                "value": "good",
            },
        )
        update_response = await client.post(
            f"/api/v1/queries/{query_id}/labels",
            json={
                "row_identity": "row-1",
                "field_key": "quality",
                "value": "bad",
            },
        )
        delete_response = await client.post(
            f"/api/v1/queries/{query_id}/labels",
            json={
                "row_identity": "row-1",
                "field_key": "quality",
                "value": None,
            },
        )

    assert insert_response.status_code == HTTP_OK
    inserted = insert_response.json()
    assert inserted["value"] == "good"
    assert inserted["record_id"] > 0

    assert update_response.status_code == HTTP_OK
    updated = update_response.json()
    assert updated["record_id"] == inserted["record_id"]
    assert updated["value"] == "bad"

    assert delete_response.status_code == HTTP_OK
    assert delete_response.json() is None

    session = get_session_factory()()
    try:
        record_count = session.scalar(
            select(func.count()).select_from(LabelRecord).where(LabelRecord.query_id == query_id)
        )
        assert record_count == 0
    finally:
        session.close()


@pytest.mark.asyncio
async def test_get_labels_by_rows_returns_nested_row_field_map() -> None:
    query_id = _create_temporary_query()
    transport = httpx.ASGITransport(app=cast(Any, app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        await _put_schema(client, query_id)
        for payload in [
            {"row_identity": "row-1", "field_key": "quality", "value": "good"},
            {
                "row_identity": "row-1",
                "field_key": "issues",
                "value": ["hallucination"],
            },
            {"row_identity": "row-2", "field_key": "note", "value": "needs review"},
        ]:
            response = await client.post(f"/api/v1/queries/{query_id}/labels", json=payload)
            assert response.status_code == HTTP_OK

        query_response = await client.post(
            f"/api/v1/queries/{query_id}/labels/query",
            json={"row_identities": ["row-1", "row-2", "row-3"]},
        )

    assert query_response.status_code == HTTP_OK
    assert query_response.json() == {
        "labels_by_row": {
            "row-1": {
                "quality": "good",
                "issues": ["hallucination"],
            },
            "row-2": {
                "note": "needs review",
            },
        }
    }


@pytest.mark.asyncio
async def test_get_labels_accepts_csv_row_identities_and_strips_whitespace() -> None:
    query_id = _create_temporary_query()
    transport = httpx.ASGITransport(app=cast(Any, app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        await _put_schema(client, query_id)
        response = await client.post(
            f"/api/v1/queries/{query_id}/labels",
            json={
                "row_identity": "row-1",
                "field_key": "quality",
                "value": "good",
            },
        )
        assert response.status_code == HTTP_OK

        get_response = await client.get(
            f"/api/v1/queries/{query_id}/labels",
            params={"row_identities": "row-1, row-2,,"},
        )

    assert get_response.status_code == HTTP_OK
    assert get_response.json() == {"labels_by_row": {"row-1": {"quality": "good"}}}


@pytest.mark.asyncio
async def test_get_labels_exact_row_identity_supports_commas_and_surrounding_whitespace() -> None:
    query_id = _create_temporary_query()
    transport = httpx.ASGITransport(app=cast(Any, app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        await _put_schema(client, query_id)
        for row_identity, value in [("a,b", "comma"), (" 42 ", "space")]:
            response = await client.post(
                f"/api/v1/queries/{query_id}/labels",
                json={
                    "row_identity": row_identity,
                    "field_key": "note",
                    "value": value,
                },
            )
            assert response.status_code == HTTP_OK

        get_response = await client.get(
            f"/api/v1/queries/{query_id}/labels",
            params=[("row_identity", "a,b"), ("row_identity", " 42 ")],
        )

    assert get_response.status_code == HTTP_OK
    assert get_response.json() == {
        "labels_by_row": {
            "a,b": {"note": "comma"},
            " 42 ": {"note": "space"},
        }
    }


@pytest.mark.asyncio
async def test_delete_label_record_by_id() -> None:
    query_id = _create_temporary_query()
    transport = httpx.ASGITransport(app=cast(Any, app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        await _put_schema(client, query_id)
        create_response = await client.post(
            f"/api/v1/queries/{query_id}/labels",
            json={
                "row_identity": "row-1",
                "field_key": "quality",
                "value": "good",
            },
        )
        assert create_response.status_code == HTTP_OK
        record_id = create_response.json()["record_id"]

        delete_response = await client.delete(f"/api/v1/queries/{query_id}/labels/{record_id}")
        missing_response = await client.delete(f"/api/v1/queries/{query_id}/labels/{record_id}")

    assert delete_response.status_code == HTTP_NO_CONTENT
    assert missing_response.status_code == HTTP_NOT_FOUND
    assert missing_response.json()["error"]["code"] == "LABEL_RECORD_NOT_FOUND"


@pytest.mark.asyncio
async def test_upsert_rejects_invalid_value_with_400() -> None:
    query_id = _create_temporary_query()
    transport = httpx.ASGITransport(app=cast(Any, app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        await _put_schema(client, query_id)
        enum_response = await client.post(
            f"/api/v1/queries/{query_id}/labels",
            json={
                "row_identity": "row-1",
                "field_key": "quality",
                "value": "unknown",
            },
        )
        type_response = await client.post(
            f"/api/v1/queries/{query_id}/labels",
            json={
                "row_identity": "row-1",
                "field_key": "issues",
                "value": "hallucination",
            },
        )

    assert enum_response.status_code == HTTP_BAD_REQUEST
    assert enum_response.json()["error"]["code"] == "LABEL_VALUE_INVALID"
    assert type_response.status_code == HTTP_BAD_REQUEST
    assert type_response.json()["error"]["code"] == "LABEL_VALUE_INVALID"


@pytest.mark.asyncio
async def test_batch_upsert_records_row_errors_without_rolling_back_successes() -> None:
    query_id = _create_temporary_query()
    too_long_row_identity = "x" * 513
    transport = httpx.ASGITransport(app=cast(Any, app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        await _put_schema(client, query_id)
        response = await client.post(
            f"/api/v1/queries/{query_id}/labels/batch",
            json={
                "row_identities": ["row-1", too_long_row_identity, "row-2"],
                "field_key": "quality",
                "value": "bad",
            },
        )
        labels_response = await client.post(
            f"/api/v1/queries/{query_id}/labels/query",
            json={"row_identities": ["row-1", "row-2"]},
        )

    assert response.status_code == HTTP_OK
    assert response.json()["affected"] == EXPECTED_BATCH_AFFECTED
    assert response.json()["skipped"] == 1
    assert response.json()["errors"][0]["row_identity"] == too_long_row_identity
    assert response.json()["errors"][0]["code"] == "LABEL_ROW_IDENTITY_INVALID"
    assert labels_response.json() == {
        "labels_by_row": {
            "row-1": {"quality": "bad"},
            "row-2": {"quality": "bad"},
        }
    }


@pytest.mark.asyncio
async def test_query_labels_rejects_more_than_1000_row_identities() -> None:
    query_id = _create_temporary_query()
    transport = httpx.ASGITransport(app=cast(Any, app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        await _put_schema(client, query_id)
        response = await client.post(
            f"/api/v1/queries/{query_id}/labels/query",
            json={"row_identities": [f"row-{index}" for index in range(1001)]},
        )

    assert response.status_code == HTTP_BAD_REQUEST
    assert response.json()["error"]["code"] == "LABEL_ROW_IDENTITIES_TOO_MANY"
