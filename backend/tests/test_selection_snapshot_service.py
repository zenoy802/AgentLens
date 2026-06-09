from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.session import get_session_factory, initialize_metadata_database
from app.models.connection import Connection
from app.models.named_query import NamedQuery
from app.models.selection_snapshot import SelectionSnapshot
from app.schemas.selection_snapshot import SelectionSnapshotCreate
from app.services.selection_snapshot_service import SelectionSnapshotService

EXPECTED_SELECTION_COUNT = 2


def _now() -> datetime:
    return datetime.now(UTC)


def _create_query(session: Session) -> int:
    connection = Connection(
        name="selection-service-mysql",
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
    )
    session.add(query)
    session.commit()
    return query.id


@pytest.mark.asyncio
async def test_create_and_get_selection_snapshot() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        query_id = _create_query(session)
        service = SelectionSnapshotService(session)
        snapshot = await service.create(
            query_id,
            SelectionSnapshotCreate(
                row_identities=["row-1", "row-2"],
                source="copy_agent_prompt",
            ),
        )
        output = service.to_read_model(await service.get(snapshot.id))

        assert re.fullmatch(r"sel_\d{8}_\d{6}_[0-9a-f]{8}", snapshot.id)
        assert output.row_identities == ["row-1", "row-2"]
        assert output.count == EXPECTED_SELECTION_COUNT
        assert output.source == "copy_agent_prompt"
    finally:
        session.close()


@pytest.mark.asyncio
async def test_get_expired_selection_snapshot_returns_not_found() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        query_id = _create_query(session)
        snapshot = SelectionSnapshot(
            id="sel_20260518_103000_deadbeef",
            query_id=query_id,
            row_identities_json='["row-1"]',
            source="manual",
            created_at=_now() - timedelta(days=8),
            expires_at=_now() - timedelta(seconds=1),
        )
        session.add(snapshot)
        session.commit()

        with pytest.raises(NotFoundError):
            await SelectionSnapshotService(session).get(snapshot.id)
    finally:
        session.close()
