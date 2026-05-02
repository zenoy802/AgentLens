from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast

import httpx
import pytest
from starlette import status

from app.api.admin import _scheduler_jobs
from app.db.session import get_session_factory, initialize_metadata_database
from app.main import app
from app.models.connection import Connection
from app.models.label import LabelSchema
from app.models.named_query import NamedQuery
from app.models.view_config import ViewConfig

PACIFIC = timezone(timedelta(hours=-7))


@pytest.mark.asyncio
async def test_admin_info_returns_runtime_counts() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection = Connection(
            name="admin-info-mysql",
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
        named_query = NamedQuery(
            connection_id=connection.id,
            name="recent trajectory",
            sql_text="SELECT 1",
            is_named=True,
        )
        named_query.view_config = ViewConfig(field_renders="{}", table_config="{}")
        named_query.label_schema = LabelSchema(fields="[]")
        temporary_query = NamedQuery(
            connection_id=connection.id,
            name=None,
            sql_text="SELECT 2",
            is_named=False,
        )
        temporary_query.view_config = ViewConfig(field_renders="{}", table_config="{}")
        temporary_query.label_schema = LabelSchema(fields="[]")
        session.add_all([named_query, temporary_query])
        session.commit()
    finally:
        session.close()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/admin/info")

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["version"] == "0.1.0"
    assert payload["data_dir"]
    assert payload["db_path"].endswith("metadata.db")
    assert isinstance(payload["uptime_seconds"], int)
    assert isinstance(payload["scheduler_jobs"], list)
    assert payload["connections_count"] == 1
    assert payload["named_queries_count"] == 1


def test_scheduler_job_next_run_serializes_as_utc_z() -> None:
    job = _Job(next_run_time=datetime(2026, 5, 2, 20, 30, tzinfo=PACIFIC))
    payload = _Scheduler([job]).get_jobs()[0]
    assert payload.next_run_time.tzinfo is PACIFIC

    serialized = _scheduler_jobs(_Scheduler([job]))[0].model_dump(mode="json")

    assert serialized["next_run"] == "2026-05-03T03:30:00Z"


class _Job:
    id = "cleanup"
    name = "Cleanup expired queries and query history"
    trigger = "cron[hour='3', minute='0']"

    def __init__(self, next_run_time: datetime) -> None:
        self.next_run_time = next_run_time


class _Scheduler:
    def __init__(self, jobs: list[_Job]) -> None:
        self._jobs = jobs

    def get_jobs(self) -> list[_Job]:
        return self._jobs
