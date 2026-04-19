from __future__ import annotations

import json
from typing import Any, cast

import httpx
import pytest
from pymysql import MySQLError  # type: ignore[import-untyped]
from starlette import status

from app.core.crypto import decrypt_secret
from app.db.session import get_session_factory, initialize_metadata_database
from app.main import app
from app.models.connection import Connection

HTTP_CREATED = status.HTTP_201_CREATED
HTTP_OK = status.HTTP_200_OK
HTTP_NO_CONTENT = status.HTTP_204_NO_CONTENT
HTTP_NOT_FOUND = status.HTTP_404_NOT_FOUND
HTTP_CONFLICT = status.HTTP_409_CONFLICT
HTTP_UNPROCESSABLE_ENTITY = status.HTTP_422_UNPROCESSABLE_CONTENT
MYSQL_TEST_PORT = 3307
PASSWORD_DECRYPT_ERROR = "Unable to decrypt connection password. Please update the saved password."


class FakeCursor:
    def execute(self, query: str) -> None:
        assert query == "SELECT VERSION()"

    def fetchone(self) -> tuple[str]:
        return ("8.0.32",)

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeMySQLConnection:
    def cursor(self) -> FakeCursor:
        return FakeCursor()

    def get_server_info(self) -> str:
        return "8.0.32"

    def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_create_list_get_update_and_delete_connection() -> None:
    initialize_metadata_database()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_response = await client.post(
            "/api/v1/connections",
            json={
                "name": "prod-mysql",
                "db_type": "mysql",
                "host": "db.example.com",
                "port": 3306,
                "database": "agent_logs",
                "username": "readonly_user",
                "password": "secret-value",
                "extra_params": {"charset": "utf8mb4"},
                "default_timeout": 30,
                "default_row_limit": 10000,
            },
        )
        assert create_response.status_code == HTTP_CREATED
        created = create_response.json()
        assert "password" not in created
        assert created["name"] == "prod-mysql"
        assert created["extra_params"] == {"charset": "utf8mb4"}

        list_response = await client.get("/api/v1/connections")
        assert list_response.status_code == HTTP_OK
        listed = list_response.json()
        assert listed["pagination"]["total"] == 1
        assert len(listed["items"]) == 1

        connection_id = created["id"]
        get_response = await client.get(f"/api/v1/connections/{connection_id}")
        assert get_response.status_code == HTTP_OK
        fetched = get_response.json()
        assert fetched["id"] == connection_id
        assert fetched["username"] == "readonly_user"

        patch_response = await client.patch(
            f"/api/v1/connections/{connection_id}",
            json={
                "name": "prod-mysql-updated",
                "password": "updated-secret",
                "extra_params": {"charset": "utf8mb4", "ssl_ca": "/tmp/ca.pem"},
            },
        )
        assert patch_response.status_code == HTTP_OK
        patched = patch_response.json()
        assert patched["name"] == "prod-mysql-updated"
        assert patched["extra_params"] == {"charset": "utf8mb4", "ssl_ca": "/tmp/ca.pem"}

        delete_response = await client.delete(f"/api/v1/connections/{connection_id}")
        assert delete_response.status_code == HTTP_NO_CONTENT

        missing_response = await client.get(f"/api/v1/connections/{connection_id}")
        assert missing_response.status_code == HTTP_NOT_FOUND

    session = get_session_factory()()
    try:
        connections = session.query(Connection).all()
        assert connections == []
    finally:
        session.close()


@pytest.mark.asyncio
async def test_create_connection_persists_encrypted_password() -> None:
    initialize_metadata_database()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/connections",
            json={
                "name": "encrypted-mysql",
                "db_type": "mysql",
                "host": "db.example.com",
                "database": "agent_logs",
                "username": "readonly_user",
                "password": "super-secret",
            },
        )
        assert response.status_code == HTTP_CREATED
        connection_id = response.json()["id"]

    session = get_session_factory()()
    try:
        connection = session.get(Connection, connection_id)
        assert connection is not None
        assert connection.password_enc is not None
        assert decrypt_secret(connection.password_enc) == "super-secret"
        assert json.loads(connection.extra_params or "null") is None
    finally:
        session.close()


@pytest.mark.asyncio
async def test_create_connection_rejects_duplicate_name() -> None:
    initialize_metadata_database()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post(
            "/api/v1/connections",
            json={"name": "dup", "db_type": "mysql", "database": "db"},
        )
        assert first.status_code == HTTP_CREATED

        duplicate = await client.post(
            "/api/v1/connections",
            json={"name": "dup", "db_type": "mysql", "database": "db2"},
        )
        assert duplicate.status_code == HTTP_CONFLICT
        payload = duplicate.json()
        assert payload["error"]["code"] == "CONN_NAME_CONFLICT"


@pytest.mark.asyncio
async def test_create_connection_rejects_extra_params_core_override() -> None:
    initialize_metadata_database()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/connections",
            json={
                "name": "override-mysql",
                "db_type": "mysql",
                "host": "db.example.com",
                "database": "agent_logs",
                "extra_params": {"host": "other.example.com", "charset": "utf8mb4"},
            },
        )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    payload = response.json()
    assert payload["error"]["code"] == "CONN_EXTRA_PARAMS_FORBIDDEN"
    assert payload["error"]["detail"] == {"keys": ["host"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra_params",
    [
        {"init_command": "DROP TABLE t"},
        {"local_infile": True},
        {"client_flag": 1},
        {"read_default_file": "/tmp/my.cnf"},
        {"cursorclass": "DictCursor"},
        {"ssl": True},
        {"bad_kwarg": True},
        {"Read_Timeout": 5},
        {"SSL_CA": "/tmp/ca.pem"},
    ],
)
async def test_create_connection_rejects_unsupported_or_unsafe_extra_params(
    extra_params: dict[str, object],
) -> None:
    initialize_metadata_database()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/connections",
            json={
                "name": "unsafe-param-mysql",
                "db_type": "mysql",
                "host": "db.example.com",
                "database": "agent_logs",
                "extra_params": extra_params,
            },
        )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    payload = response.json()
    assert payload["error"]["code"] == "CONN_EXTRA_PARAMS_FORBIDDEN"
    assert payload["error"]["detail"] == {"keys": sorted(extra_params)}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra_params",
    [
        {"charset": 123},
        {"read_timeout": "5"},
        {"write_timeout": True},
        {"ssl_ca": True},
        {"ssl_verify_cert": "true"},
    ],
)
async def test_create_connection_rejects_invalid_extra_param_value_types(
    extra_params: dict[str, object],
) -> None:
    initialize_metadata_database()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/connections",
            json={
                "name": "invalid-param-type-mysql",
                "db_type": "mysql",
                "host": "db.example.com",
                "database": "agent_logs",
                "extra_params": extra_params,
            },
        )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    payload = response.json()
    assert payload["error"]["code"] == "CONN_EXTRA_PARAMS_INVALID"
    assert payload["error"]["detail"] == {"keys": sorted(extra_params)}


@pytest.mark.asyncio
async def test_get_connection_rejects_persisted_unsafe_extra_params() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection = Connection(
            name="legacy-unsafe",
            db_type="mysql",
            database="agent_logs",
            extra_params=json.dumps({"init_command": "DROP TABLE t"}),
            default_timeout=30,
            default_row_limit=10000,
        )
        session.add(connection)
        session.commit()
        connection_id = connection.id
    finally:
        session.close()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/v1/connections/{connection_id}")

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    payload = response.json()
    assert payload["error"]["code"] == "CONN_EXTRA_PARAMS_FORBIDDEN"
    assert payload["error"]["detail"] == {"keys": ["init_command"]}


@pytest.mark.asyncio
async def test_get_connection_rejects_persisted_invalid_extra_params_json() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection = Connection(
            name="legacy-invalid-json",
            db_type="mysql",
            database="agent_logs",
            extra_params="{not-json",
            default_timeout=30,
            default_row_limit=10000,
        )
        session.add(connection)
        session.commit()
        connection_id = connection.id
    finally:
        session.close()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/v1/connections/{connection_id}")

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    payload = response.json()
    assert payload["error"]["code"] == "CONN_EXTRA_PARAMS_INVALID"


@pytest.mark.asyncio
async def test_test_connection_success(monkeypatch: pytest.MonkeyPatch) -> None:
    initialize_metadata_database()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_response = await client.post(
            "/api/v1/connections",
            json={
                "name": "test-mysql",
                "db_type": "mysql",
                "host": "db.example.com",
                "port": MYSQL_TEST_PORT,
                "database": "agent_logs",
                "username": "readonly_user",
                "password": "pw",
                "extra_params": {"charset": "utf8mb4"},
            },
        )
        connection_id = create_response.json()["id"]

        captured_kwargs: dict[str, object] = {}

        def fake_connect(**kwargs: object) -> FakeMySQLConnection:
            captured_kwargs.update(kwargs)
            return FakeMySQLConnection()

        monkeypatch.setattr("app.services.connection_service.pymysql.connect", fake_connect)

        test_response = await client.post(f"/api/v1/connections/{connection_id}/test")
        assert test_response.status_code == HTTP_OK
        payload = test_response.json()
        assert payload["ok"] is True
        assert payload["server_version"] == "8.0.32"
        assert payload["error"] is None
        assert isinstance(payload["latency_ms"], int)
        assert captured_kwargs["host"] == "db.example.com"
        assert captured_kwargs["port"] == MYSQL_TEST_PORT
        assert captured_kwargs["user"] == "readonly_user"
        assert captured_kwargs["password"] == "pw"
        assert captured_kwargs["charset"] == "utf8mb4"

    session = get_session_factory()()
    try:
        connection = session.get(Connection, connection_id)
        assert connection is not None
        assert connection.last_test_ok is True
        assert connection.last_tested_at is not None
    finally:
        session.close()


@pytest.mark.asyncio
async def test_update_connection_rejects_unsupported_extra_params() -> None:
    initialize_metadata_database()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_response = await client.post(
            "/api/v1/connections",
            json={
                "name": "safe-param-mysql",
                "db_type": "mysql",
                "database": "agent_logs",
                "extra_params": {"charset": "utf8mb4"},
            },
        )
        connection_id = create_response.json()["id"]

        response = await client.patch(
            f"/api/v1/connections/{connection_id}",
            json={"extra_params": {"init_command": "DROP TABLE t"}},
        )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    payload = response.json()
    assert payload["error"]["code"] == "CONN_EXTRA_PARAMS_FORBIDDEN"
    assert payload["error"]["detail"] == {"keys": ["init_command"]}


@pytest.mark.asyncio
async def test_test_connection_rejects_persisted_unsafe_extra_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    try:
        connection = Connection(
            name="legacy-unsafe-test",
            db_type="mysql",
            database="agent_logs",
            extra_params=json.dumps({"init_command": "DROP TABLE t"}),
            default_timeout=30,
            default_row_limit=10000,
        )
        session.add(connection)
        session.commit()
        connection_id = connection.id
    finally:
        session.close()

    def fake_connect(**_: object) -> FakeMySQLConnection:
        raise AssertionError("unsafe extra_params must not reach pymysql.connect")

    monkeypatch.setattr("app.services.connection_service.pymysql.connect", fake_connect)

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(f"/api/v1/connections/{connection_id}/test")

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    payload = response.json()
    assert payload["error"]["code"] == "CONN_EXTRA_PARAMS_FORBIDDEN"
    assert payload["error"]["detail"] == {"keys": ["init_command"]}


@pytest.mark.asyncio
async def test_test_connection_file_error_returns_ok_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialize_metadata_database()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_response = await client.post(
            "/api/v1/connections",
            json={
                "name": "missing-ssl-ca",
                "db_type": "mysql",
                "database": "agent_logs",
                "extra_params": {"ssl_ca": "/definitely/not/found/ca.pem"},
            },
        )
        connection_id = create_response.json()["id"]

        def fake_connect(**_: object) -> FakeMySQLConnection:
            raise FileNotFoundError("/definitely/not/found/ca.pem")

        monkeypatch.setattr("app.services.connection_service.pymysql.connect", fake_connect)

        response = await client.post(f"/api/v1/connections/{connection_id}/test")

    assert response.status_code == HTTP_OK
    payload = response.json()
    assert payload["ok"] is False
    assert payload["server_version"] is None
    assert payload["latency_ms"] is None
    assert payload["error"].startswith("Invalid MySQL connection parameters:")


@pytest.mark.asyncio
async def test_test_connection_decrypt_failure_returns_ok_false() -> None:
    initialize_metadata_database()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_response = await client.post(
            "/api/v1/connections",
            json={
                "name": "broken-secret-mysql",
                "db_type": "mysql",
                "database": "agent_logs",
                "password": "pw",
            },
        )
        connection_id = create_response.json()["id"]

    session = get_session_factory()()
    try:
        connection = session.get(Connection, connection_id)
        assert connection is not None
        connection.password_enc = b"not-a-fernet-token"
        session.commit()
    finally:
        session.close()

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        test_response = await client.post(f"/api/v1/connections/{connection_id}/test")

    assert test_response.status_code == HTTP_OK
    payload = test_response.json()
    assert payload["ok"] is False
    assert payload["error"] == PASSWORD_DECRYPT_ERROR


@pytest.mark.asyncio
async def test_test_connection_failure_returns_ok_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialize_metadata_database()

    transport = httpx.ASGITransport(app=cast(Any, app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_response = await client.post(
            "/api/v1/connections",
            json={"name": "bad-mysql", "db_type": "mysql", "database": "agent_logs"},
        )
        connection_id = create_response.json()["id"]

        def fake_connect(**_: object) -> FakeMySQLConnection:
            raise MySQLError("Access denied")

        monkeypatch.setattr("app.services.connection_service.pymysql.connect", fake_connect)

        test_response = await client.post(f"/api/v1/connections/{connection_id}/test")
        assert test_response.status_code == HTTP_OK
        payload = test_response.json()
        assert payload["ok"] is False
        assert payload["error"] == "Access denied"
        assert payload["server_version"] is None
        assert payload["latency_ms"] is None

    session = get_session_factory()()
    try:
        connection = session.get(Connection, connection_id)
        assert connection is not None
        assert connection.last_test_ok is False
        assert connection.last_tested_at is not None
    finally:
        session.close()
