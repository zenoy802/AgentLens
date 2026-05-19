from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import httpx
import pytest
from sqlalchemy.orm import Session
from starlette import status

from app.db.session import get_session_factory, initialize_metadata_database
from app.main import app
from app.models.connection import Connection
from app.models.named_query import NamedQuery

EXPECTED_SELECTION_COUNT = 2


def _create_query(session: Session) -> int:
    connection = Connection(
        name="selection-api-mysql",
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
        expires_at=datetime.now(UTC).replace(tzinfo=None),
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
async def test_selection_snapshot_api_create_get_delete() -> None:
    query_id = _create_query_id()
    transport = httpx.ASGITransport(app=cast(Any, app))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_response = await client.post(
            f"/api/v1/queries/{query_id}/selection-snapshots",
            json={"row_identities": ["row-1", "row-2"], "source": "context_export"},
        )
        selection_id = create_response.json()["id"]
        get_response = await client.get(f"/api/v1/selections/{selection_id}")
        delete_response = await client.delete(f"/api/v1/selections/{selection_id}")
        missing_response = await client.get(f"/api/v1/selections/{selection_id}")

    assert create_response.status_code == status.HTTP_201_CREATED
    assert create_response.json()["count"] == EXPECTED_SELECTION_COUNT
    assert get_response.status_code == status.HTTP_200_OK
    assert get_response.json()["row_identities"] == ["row-1", "row-2"]
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT
    assert missing_response.status_code == status.HTTP_404_NOT_FOUND
