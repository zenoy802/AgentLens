from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette import status

from app.db.session import get_session_factory, initialize_metadata_database
from app.main import app
from app.models.annotation import Annotation
from app.models.connection import Connection
from app.models.named_query import NamedQuery

BATCH_SIZE = 200


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _create_query(session: Session) -> int:
    connection = Connection(
        name="annotation-api-mysql",
        db_type="mysql",
        host="db.example.com",
        port=3306,
        database="agent_logs",
        username="reader",
        default_timeout=30,
        default_row_limit=10000,
    )
    session.add(connection)
    session.flush()
    query = NamedQuery(
        connection_id=connection.id,
        name=None,
        sql_text="SELECT * FROM traces",
        is_named=False,
        expires_at=_now() + timedelta(days=7),
    )
    session.add(query)
    session.commit()
    return query.id


def _create_query_id() -> int:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        return _create_query(session)
    finally:
        session.close()


@pytest.mark.asyncio
async def test_create_and_filter_annotations() -> None:
    query_id = _create_query_id()
    transport = httpx.ASGITransport(app=cast(Any, app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_response = await client.post(
            f"/api/v1/queries/{query_id}/annotations",
            json={
                "row_identity": "row-1",
                "column_key": "content",
                "author": "agent:codex",
                "color": "red",
                "title": "Bad answer",
                "text": "The answer contradicts the tool output.",
                "severity": "error",
                "annotation_set": "failure-pattern-analysis-20260518",
                "sql_fingerprint": "sha256:sql",
            },
        )
        await client.post(
            f"/api/v1/queries/{query_id}/annotations",
            json={
                "row_identity": "row-2",
                "author": "human",
                "color": "blue",
                "text": "Manual note",
            },
        )
        filter_response = await client.get(
            f"/api/v1/queries/{query_id}/annotations",
            params={
                "author_prefix": "agent:",
                "color": "red",
                "row_identity": "row-1",
                "column_key": "content",
                "annotation_set": "failure-pattern-analysis-20260518",
            },
        )

    assert create_response.status_code == status.HTTP_201_CREATED
    created = create_response.json()
    assert created["id"] > 0
    assert created["query_id"] == query_id
    assert created["expires_at"].endswith(("+00:00", "Z"))
    assert filter_response.status_code == status.HTTP_200_OK
    assert [item["row_identity"] for item in filter_response.json()] == ["row-1"]


@pytest.mark.asyncio
async def test_batch_create_200_annotations_and_clear_agents() -> None:
    query_id = _create_query_id()
    transport = httpx.ASGITransport(app=cast(Any, app))
    payload = {
        "annotations": [
            {
                "row_identity": f"row-{index}",
                "author": "agent:claude-code",
                "color": "yellow",
            }
            for index in range(BATCH_SIZE)
        ]
    }

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        batch_response = await client.post(
            f"/api/v1/queries/{query_id}/annotations/batch",
            json=payload,
        )
        delete_response = await client.delete(
            f"/api/v1/queries/{query_id}/annotations",
            params={"author_prefix": "agent:"},
        )

    assert batch_response.status_code == status.HTTP_201_CREATED
    assert len(batch_response.json()) == BATCH_SIZE
    assert delete_response.status_code == status.HTTP_200_OK
    assert delete_response.json() == {"deleted_count": BATCH_SIZE}

    session = get_session_factory()()
    try:
        remaining = session.scalar(
            select(func.count()).select_from(Annotation).where(Annotation.query_id == query_id)
        )
        assert remaining == 0
    finally:
        session.close()


@pytest.mark.asyncio
async def test_delete_annotations_rejects_unfiltered_delete() -> None:
    query_id = _create_query_id()
    transport = httpx.ASGITransport(app=cast(Any, app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.delete(f"/api/v1/queries/{query_id}/annotations")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "ANNOTATION_DELETE_FILTER_REQUIRED"


@pytest.mark.asyncio
async def test_delete_annotation_by_id() -> None:
    query_id = _create_query_id()
    transport = httpx.ASGITransport(app=cast(Any, app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_response = await client.post(
            f"/api/v1/queries/{query_id}/annotations",
            json={
                "row_identity": "row-1",
                "author": "human",
                "color": "gray",
                "text": "Manual note",
            },
        )
        annotation_id = create_response.json()["id"]
        delete_response = await client.delete(
            f"/api/v1/queries/{query_id}/annotations/{annotation_id}",
        )
        missing_response = await client.delete(
            f"/api/v1/queries/{query_id}/annotations/{annotation_id}",
        )

    assert create_response.status_code == status.HTTP_201_CREATED
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT
    assert missing_response.status_code == status.HTTP_404_NOT_FOUND
    assert missing_response.json()["error"]["code"] == "ANNOTATION_NOT_FOUND"
