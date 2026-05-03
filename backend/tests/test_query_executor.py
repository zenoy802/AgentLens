from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from cryptography.fernet import InvalidToken
from pymysql.constants import FIELD_TYPE  # type: ignore[import-untyped]
from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError

from app.core.errors import (
    ConnectionTestError,
    SqlExecutionError,
    SqlSyntaxError,
    SqlTimeoutError,
    ValidationError,
)
from app.db.session import get_session_factory, initialize_metadata_database
from app.models.connection import Connection
from app.schemas.connection import ConnectionUpdate
from app.services.connection_service import ConnectionService
from app.services.query_executor import ExecutorService

FETCHMANY_ROW_LIMIT_PLUS_ONE = 3
TIMEOUT_SECONDS = 3
MYSQL_POOL_SIZE = 5


class FakeCursor:
    def __init__(self, description: Sequence[Sequence[Any]]) -> None:
        self.description = description


class FakeResult:
    def __init__(self, rows: list[tuple[Any, ...]], description: Sequence[Sequence[Any]]) -> None:
        self.cursor = FakeCursor(description)
        self.rows = rows
        self.fetchmany_size: int | None = None
        self.closed = False

    def fetchmany(self, size: int) -> list[tuple[Any, ...]]:
        self.fetchmany_size = size
        return self.rows[:size]

    def close(self) -> None:
        self.closed = True


class FakeDbConnection:
    def __init__(
        self,
        *,
        result: FakeResult | None = None,
        query_error: DBAPIError | None = None,
    ) -> None:
        self.result = result
        self.query_error = query_error
        self.executed_sql: list[str] = []
        self.execution_options_kwargs: dict[str, object] = {}

    def execution_options(self, **kwargs: object) -> FakeDbConnection:
        self.execution_options_kwargs.update(kwargs)
        return self

    def exec_driver_sql(self, sql: str) -> FakeResult:
        self.executed_sql.append(sql)
        if sql.startswith("SET SESSION MAX_EXECUTION_TIME="):
            return FakeResult([], [])
        if self.query_error is not None:
            raise self.query_error
        assert self.result is not None
        return self.result

    def __enter__(self) -> FakeDbConnection:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(
        self,
        db_connection: FakeDbConnection,
        connect_error: BaseException | None = None,
    ) -> None:
        self.db_connection = db_connection
        self.connect_error = connect_error
        self.disposed = False

    def connect(self) -> FakeDbConnection:
        if self.connect_error is not None:
            raise self.connect_error
        return self.db_connection

    def dispose(self) -> None:
        self.disposed = True


class FakeExecutorForInvalidation:
    def __init__(self) -> None:
        self.invalidated_ids: list[int] = []

    def invalidate_engine(self, connection_id: int) -> None:
        self.invalidated_ids.append(connection_id)


class FakeOrigError(Exception):
    def __init__(self) -> None:
        super().__init__(3024, "Query execution exceeded max_execution_time")


class FakeSyntaxError(Exception):
    def __init__(self) -> None:
        super().__init__(1064, "You have an error in your SQL syntax")


class FakeConnectionError(Exception):
    def __init__(self) -> None:
        super().__init__(2003, "Can't connect to MySQL server")


class BrokenDecryptor:
    def decrypt_secret(self, value: bytes | None) -> str | None:
        assert value is None or isinstance(value, bytes)
        raise InvalidToken


def _connection(connection_id: int = 1) -> Connection:
    return Connection(
        id=connection_id,
        name="mysql",
        db_type="mysql",
        host="db.example.com",
        port=3306,
        database="agent_logs",
        username="reader",
        password_enc=None,
        extra_params=None,
        default_timeout=30,
        default_row_limit=10000,
    )


def test_execute_validates_sql_and_marks_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    description = [("id", FIELD_TYPE.LONGLONG, None, None, None, None, True)]
    result = FakeResult([(1,), (2,), (3,)], description)
    db_connection = FakeDbConnection(result=result)
    fake_engine = FakeEngine(db_connection)
    validated_sql: list[str] = []

    def fake_validate_sql(sql: str) -> None:
        validated_sql.append(sql)

    def fake_get_or_create_engine(
        self: ExecutorService,
        connection: Connection,
    ) -> Engine:
        assert self is service
        assert connection.id == 1
        return cast(Engine, fake_engine)

    service = ExecutorService()
    monkeypatch.setattr("app.services.query_executor.validate_sql", fake_validate_sql)
    monkeypatch.setattr(ExecutorService, "_get_or_create_engine", fake_get_or_create_engine)

    executor_result = service.execute(_connection(), "SELECT id FROM t", timeout=7, row_limit=2)

    assert validated_sql == ["SELECT id FROM t"]
    assert db_connection.execution_options_kwargs == {
        "isolation_level": "AUTOCOMMIT",
        "stream_results": True,
        "max_row_buffer": FETCHMANY_ROW_LIMIT_PLUS_ONE,
    }
    assert db_connection.executed_sql == [
        "SET SESSION MAX_EXECUTION_TIME=7000",
        "SELECT id FROM t",
    ]
    assert result.fetchmany_size == FETCHMANY_ROW_LIMIT_PLUS_ONE
    assert result.closed is True
    assert executor_result.truncated is True
    assert executor_result.rows == [{"id": 1}, {"id": 2}]
    assert executor_result.columns[0].inferred_type == "integer"


def test_execute_preserves_duplicate_column_values(monkeypatch: pytest.MonkeyPatch) -> None:
    description = [
        ("id", FIELD_TYPE.LONGLONG, None, None, None, None, True),
        ("id", FIELD_TYPE.LONGLONG, None, None, None, None, True),
    ]
    result = FakeResult([(1, 2)], description)
    fake_engine = FakeEngine(FakeDbConnection(result=result))

    def fake_get_or_create_engine(
        self: ExecutorService,
        connection: Connection,
    ) -> Engine:
        assert isinstance(self, ExecutorService)
        assert connection.id == 1
        return cast(Engine, fake_engine)

    monkeypatch.setattr(ExecutorService, "_get_or_create_engine", fake_get_or_create_engine)

    executor_result = ExecutorService().execute(_connection(), "SELECT 1", timeout=1, row_limit=10)

    assert [column.name for column in executor_result.columns] == ["id", "id__2"]
    assert executor_result.rows == [{"id": 1, "id__2": 2}]


def test_execute_converts_datetime_and_json_string(monkeypatch: pytest.MonkeyPatch) -> None:
    created_at = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
    description = [
        ("created_at", FIELD_TYPE.DATETIME, None, None, None, None, True),
        ("payload", FIELD_TYPE.VAR_STRING, None, None, None, None, True),
    ]
    result = FakeResult([(created_at, '{"ok": true}')], description)
    fake_engine = FakeEngine(FakeDbConnection(result=result))

    def fake_get_or_create_engine(
        self: ExecutorService,
        connection: Connection,
    ) -> Engine:
        assert isinstance(self, ExecutorService)
        assert connection.id == 1
        return cast(Engine, fake_engine)

    monkeypatch.setattr(ExecutorService, "_get_or_create_engine", fake_get_or_create_engine)

    executor_result = ExecutorService().execute(_connection(), "SELECT 1", timeout=1, row_limit=10)

    assert executor_result.truncated is False
    assert executor_result.columns[0].inferred_type == "timestamp"
    assert executor_result.columns[1].inferred_type == "json"
    assert executor_result.rows == [
        {"created_at": "2024-01-02T03:04:05+00:00", "payload": {"ok": True}}
    ]


def test_execute_raises_timeout_for_mysql_3024(monkeypatch: pytest.MonkeyPatch) -> None:
    operational_error = OperationalError("SELECT SLOW", {}, FakeOrigError())
    fake_engine = FakeEngine(FakeDbConnection(query_error=operational_error))

    def fake_get_or_create_engine(
        self: ExecutorService,
        connection: Connection,
    ) -> Engine:
        assert isinstance(self, ExecutorService)
        assert connection.id == 1
        return cast(Engine, fake_engine)

    monkeypatch.setattr(ExecutorService, "_get_or_create_engine", fake_get_or_create_engine)

    with pytest.raises(SqlTimeoutError) as exc_info:
        ExecutorService().execute(
            _connection(),
            "SELECT SLOW",
            timeout=TIMEOUT_SECONDS,
            row_limit=10,
        )

    assert exc_info.value.code == "SQL_TIMEOUT"
    assert exc_info.value.detail is not None
    assert exc_info.value.detail["timeout"] == TIMEOUT_SECONDS


def test_execute_maps_programming_error_to_sql_syntax_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    programming_error = ProgrammingError("SELECT bad", {}, FakeSyntaxError())
    fake_engine = FakeEngine(FakeDbConnection(query_error=programming_error))

    def fake_get_or_create_engine(
        self: ExecutorService,
        connection: Connection,
    ) -> Engine:
        assert isinstance(self, ExecutorService)
        assert connection.id == 1
        return cast(Engine, fake_engine)

    monkeypatch.setattr(ExecutorService, "_get_or_create_engine", fake_get_or_create_engine)

    with pytest.raises(SqlSyntaxError) as exc_info:
        ExecutorService().execute(_connection(), "SELECT bad", timeout=1, row_limit=10)

    assert exc_info.value.code == "SQL_SYNTAX_ERROR"
    assert exc_info.value.detail is not None
    assert "SQL syntax" in str(exc_info.value.detail["orig"])


def test_execute_maps_non_syntax_dbapi_error_to_sql_execution_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection_error = OperationalError("SELECT 1", {}, FakeConnectionError())
    fake_engine = FakeEngine(FakeDbConnection(query_error=connection_error))

    def fake_get_or_create_engine(
        self: ExecutorService,
        connection: Connection,
    ) -> Engine:
        assert isinstance(self, ExecutorService)
        assert connection.id == 1
        return cast(Engine, fake_engine)

    monkeypatch.setattr(ExecutorService, "_get_or_create_engine", fake_get_or_create_engine)

    with pytest.raises(SqlExecutionError) as exc_info:
        ExecutorService().execute(_connection(), "SELECT 1", timeout=1, row_limit=10)

    assert exc_info.value.code == "SQL_EXECUTION_ERROR"
    assert exc_info.value.detail is not None
    assert "Can't connect" in str(exc_info.value.detail["orig"])


def test_execute_maps_raw_connect_os_error_to_sql_execution_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_engine = FakeEngine(
        FakeDbConnection(result=FakeResult([], [])),
        connect_error=FileNotFoundError("/definitely/not/found/ca.pem"),
    )

    def fake_get_or_create_engine(
        self: ExecutorService,
        connection: Connection,
    ) -> Engine:
        assert isinstance(self, ExecutorService)
        assert connection.id == 1
        return cast(Engine, fake_engine)

    monkeypatch.setattr(ExecutorService, "_get_or_create_engine", fake_get_or_create_engine)

    with pytest.raises(SqlExecutionError) as exc_info:
        ExecutorService().execute(_connection(), "SELECT 1", timeout=1, row_limit=10)

    assert exc_info.value.code == "SQL_EXECUTION_ERROR"
    assert exc_info.value.detail is not None
    assert "/definitely/not/found/ca.pem" in str(exc_info.value.detail["orig"])


def test_get_or_create_engine_maps_broken_secret_to_app_error() -> None:
    service = ExecutorService(cast(Any, BrokenDecryptor()))

    with pytest.raises(ConnectionTestError) as exc_info:
        service._get_or_create_engine(_connection())

    assert exc_info.value.code == "CONN_SECRET_DECRYPT_FAILED"
    assert exc_info.value.detail == {"connection_id": 1}


def test_get_or_create_engine_rejects_persisted_unsafe_extra_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_create_engine(*_: object, **__: object) -> Engine:
        raise AssertionError("unsafe extra_params must not reach create_engine")

    monkeypatch.setattr("app.services.query_executor.create_engine", fake_create_engine)
    connection = _connection()
    connection.extra_params = '{"init_command": "DROP TABLE t"}'

    with pytest.raises(ValidationError) as exc_info:
        ExecutorService()._get_or_create_engine(connection)

    assert exc_info.value.code == "CONN_EXTRA_PARAMS_FORBIDDEN"
    assert exc_info.value.detail == {"keys": ["init_command"]}


def test_get_or_create_engine_rejects_persisted_invalid_extra_params_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_create_engine(*_: object, **__: object) -> Engine:
        raise AssertionError("invalid extra_params must not reach create_engine")

    monkeypatch.setattr("app.services.query_executor.create_engine", fake_create_engine)
    connection = _connection()
    connection.extra_params = "{not-json"

    with pytest.raises(ValidationError) as exc_info:
        ExecutorService()._get_or_create_engine(connection)

    assert exc_info.value.code == "CONN_EXTRA_PARAMS_INVALID"


def test_invalidate_engine_disposes_cached_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_engine = FakeEngine(FakeDbConnection(result=FakeResult([], [])))

    def fake_create_engine(*args: object, **kwargs: object) -> Engine:
        assert len(args) == 1
        assert kwargs["pool_size"] == MYSQL_POOL_SIZE
        assert kwargs["connect_args"] == {
            "read_timeout": 5,
            "ssl_verify_cert": True,
            "connect_timeout": 5,
        }
        return cast(Engine, fake_engine)

    monkeypatch.setattr("app.services.query_executor.create_engine", fake_create_engine)
    service = ExecutorService()
    connection = _connection()
    connection.extra_params = '{"read_timeout": 5, "ssl_verify_cert": true}'
    engine = service._get_or_create_engine(connection)

    assert cast(object, engine) is fake_engine
    service.invalidate_engine(1)

    assert fake_engine.disposed is True


def test_connection_service_invalidates_executor_on_update_and_delete() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    fake_executor = FakeExecutorForInvalidation()
    try:
        connection = _connection()
        session.add(connection)
        session.commit()

        service = ConnectionService(session, cast(ExecutorService, fake_executor))
        service.update_connection(connection.id, ConnectionUpdate(name="renamed"))
        service.delete_connection(connection.id)
    finally:
        session.close()

    assert fake_executor.invalidated_ids == [1, 1]
