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
from app.models.connection import Connection
from app.models.label import LabelRecord
from app.models.llm import LLMAnalysis
from app.models.misc import QueryHistory
from app.models.named_query import NamedQuery
from app.services.cleanup_service import CleanupService


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _create_connection(session: Session) -> int:
    connection = Connection(
        name="cleanup-mysql",
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


def _count(session: Session, model: type[object]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_cleanup_dry_run_reports_without_deleting() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        expired_query = NamedQuery(
            connection_id=connection_id,
            name=None,
            sql_text="SELECT 1",
            is_named=False,
            expires_at=_now() - timedelta(days=1),
        )
        session.add(expired_query)
        session.flush()
        session.add(
            LabelRecord(
                query_id=expired_query.id,
                row_identity="row-1",
                field_key="quality",
                value='"good"',
            )
        )
        session.add(
            LLMAnalysis(
                query_id=expired_query.id,
                provider_id=None,
                selection="{}",
                structure_format="rows",
                prompt="Analyze",
                structured_input="{}",
                status="completed",
            )
        )
        session.add(
            QueryHistory(
                connection_id=connection_id,
                query_id=expired_query.id,
                sql_text="SELECT 1",
                row_count=1,
                duration_ms=5,
                status="success",
                executed_at=_now() - timedelta(days=60),
            )
        )
        session.commit()

        report = CleanupService().run(session, dry_run=True)

        assert report.expired_queries_deleted == 1
        assert report.cascade_label_records_deleted == 1
        assert report.cascade_analyses_deleted == 1
        assert report.history_records_deleted == 1
        assert report.dry_run is True
        assert _count(session, NamedQuery) == 1
        assert _count(session, LabelRecord) == 1
        assert _count(session, LLMAnalysis) == 1
        assert _count(session, QueryHistory) == 1
    finally:
        session.close()


def test_cleanup_deletes_expired_queries_and_old_history() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection_id = _create_connection(session)
        expired_query = NamedQuery(
            connection_id=connection_id,
            name=None,
            sql_text="SELECT expired",
            is_named=False,
            expires_at=_now() - timedelta(days=1),
        )
        active_query = NamedQuery(
            connection_id=connection_id,
            name="active",
            sql_text="SELECT active",
            is_named=True,
            expires_at=_now() + timedelta(days=1),
        )
        session.add_all([expired_query, active_query])
        session.flush()
        session.add(
            LabelRecord(
                query_id=expired_query.id,
                row_identity="row-1",
                field_key="quality",
                value='"good"',
            )
        )
        session.add(
            LLMAnalysis(
                query_id=expired_query.id,
                provider_id=None,
                selection="{}",
                structure_format="rows",
                prompt="Analyze",
                structured_input="{}",
                status="completed",
            )
        )
        session.add_all(
            [
                QueryHistory(
                    connection_id=connection_id,
                    query_id=expired_query.id,
                    sql_text="SELECT old",
                    row_count=1,
                    duration_ms=5,
                    status="success",
                    executed_at=_now() - timedelta(days=60),
                ),
                QueryHistory(
                    connection_id=connection_id,
                    query_id=active_query.id,
                    sql_text="SELECT recent",
                    row_count=1,
                    duration_ms=5,
                    status="success",
                    executed_at=_now() - timedelta(days=1),
                ),
            ]
        )
        session.commit()
        active_query_id = active_query.id

        report = CleanupService().run(session)

        assert report.expired_queries_deleted == 1
        assert report.cascade_label_records_deleted == 1
        assert report.cascade_analyses_deleted == 1
        assert report.history_records_deleted == 1
        assert report.dry_run is False
        assert session.get(NamedQuery, expired_query.id) is None
        assert session.get(NamedQuery, active_query_id) is not None
        assert _count(session, LabelRecord) == 0
        assert _count(session, LLMAnalysis) == 0
        assert _count(session, QueryHistory) == 1
    finally:
        session.close()


@pytest.mark.asyncio
async def test_admin_cleanup_endpoint_returns_report() -> None:
    initialize_metadata_database()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/v1/admin/cleanup", json={"dry_run": True})

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "expired_queries_deleted": 0,
        "history_records_deleted": 0,
        "cascade_label_records_deleted": 0,
        "cascade_analyses_deleted": 0,
        "dry_run": True,
    }
