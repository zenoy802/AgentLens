from __future__ import annotations

import json
import os

import pytest
from sqlalchemy.engine import make_url

from app.core.crypto import encrypt_secret
from app.models.connection import Connection
from app.services.query_executor import ExecutorService


@pytest.mark.skipif(
    not os.environ.get("AGENT_LENS_TEST_MYSQL_URL"),
    reason="Set AGENT_LENS_TEST_MYSQL_URL to run real MySQL executor integration tests.",
)
def test_executor_real_mysql_select_only() -> None:
    raw_url = os.environ["AGENT_LENS_TEST_MYSQL_URL"]
    url = make_url(raw_url)
    connection = Connection(
        id=9001,
        name="integration-mysql",
        db_type="mysql",
        host=url.host,
        port=url.port or 3306,
        database=url.database or "",
        username=url.username,
        password_enc=encrypt_secret(url.password) if url.password is not None else None,
        extra_params=json.dumps(dict(url.query)) if url.query else None,
        default_timeout=5,
        default_row_limit=10,
    )

    result = ExecutorService().execute(
        connection,
        "SELECT 1 AS n, JSON_OBJECT('ok', true) AS payload",
        timeout=5,
        row_limit=10,
    )

    assert result.truncated is False
    assert result.rows[0]["n"] == 1
    assert result.rows[0]["payload"] == {"ok": True}
