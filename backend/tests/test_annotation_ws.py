from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette import status

from app.api import ws as ws_module
from app.db.session import get_session_factory, initialize_metadata_database
from app.main import app
from app.models.connection import Connection
from app.models.named_query import NamedQuery


def _create_query(session: Session) -> int:
    connection = Connection(
        name="annotation-ws-mysql",
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


def test_annotation_ws_receives_created_broadcast() -> None:
    query_id = _create_query_id()

    with (
        TestClient(app) as client,
        client.websocket_connect(f"/ws/queries/{query_id}/annotations") as websocket,
    ):
        assert websocket.receive_json() == {"type": "connected", "query_id": query_id}
        response = client.post(
            f"/api/v1/queries/{query_id}/annotations",
            json={
                "row_identity": "row-1",
                "author": "agent:codex",
                "color": "green",
                "text": "Looks stable",
            },
        )

        message = websocket.receive_json()

    assert response.status_code == status.HTTP_201_CREATED
    assert message["type"] == "annotation.created"
    assert message["query_id"] == query_id
    assert message["data"]["row_identity"] == "row-1"
    assert message["timestamp"].endswith("Z")


def test_annotation_ws_json_ping_pong(monkeypatch: pytest.MonkeyPatch) -> None:
    query_id = _create_query_id()
    monkeypatch.setattr(ws_module, "PING_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(ws_module, "PONG_TIMEOUT_SECONDS", 0.1)

    with (
        TestClient(app) as client,
        client.websocket_connect(f"/ws/queries/{query_id}/annotations") as websocket,
    ):
        assert websocket.receive_json() == {"type": "connected", "query_id": query_id}
        assert websocket.receive_json() == {"type": "ping"}
        websocket.send_json({"type": "pong"})
