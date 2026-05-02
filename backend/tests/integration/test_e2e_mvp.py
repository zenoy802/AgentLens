from __future__ import annotations

import os
from typing import Any, cast

import httpx
import pytest
from sqlalchemy.engine import make_url
from starlette import status

from app.db.session import initialize_metadata_database
from app.main import app


@pytest.mark.asyncio
async def test_e2e_mvp_create_execute_promote_delete() -> None:
    initialize_metadata_database()
    mysql_url = make_url(os.environ["AGENT_LENS_TEST_MYSQL_URL"])
    extra_params = {
        key: value if isinstance(value, str) else value[-1]
        for key, value in mysql_url.query.items()
    } or None

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_connection = await client.post(
            "/api/v1/connections",
            json={
                "name": "e2e-mysql",
                "db_type": "mysql",
                "host": mysql_url.host,
                "port": mysql_url.port or 3306,
                "database": mysql_url.database or "",
                "username": mysql_url.username,
                "password": mysql_url.password,
                "extra_params": extra_params,
                "default_timeout": 10,
                "default_row_limit": 100,
            },
        )
        assert create_connection.status_code == status.HTTP_201_CREATED
        connection_id = create_connection.json()["id"]

        execute = await client.post(
            "/api/v1/execute",
            json={
                "connection_id": connection_id,
                "sql": "SELECT 1 AS agentlens_value",
                "save_as_temporary": True,
                "row_limit": 10,
            },
        )
        assert execute.status_code == status.HTTP_200_OK
        execution_payload = execute.json()
        assert execution_payload["rows"][0]["agentlens_value"] == 1
        query_id = execution_payload["query_id"]

        promote = await client.post(
            f"/api/v1/queries/{query_id}/promote",
            json={
                "name": "e2e-mvp-query",
                "description": "Created by the real MySQL MVP integration test.",
            },
        )
        assert promote.status_code == status.HTTP_200_OK
        assert promote.json()["is_named"] is True

        delete_connection = await client.delete(f"/api/v1/connections/{connection_id}")
        assert delete_connection.status_code == status.HTTP_204_NO_CONTENT

        deleted_query = await client.get(f"/api/v1/queries/{query_id}")
        assert deleted_query.status_code == status.HTTP_404_NOT_FOUND
