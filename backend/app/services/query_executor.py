from __future__ import annotations

import base64
import json
import threading
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, NoReturn

from cryptography.fernet import InvalidToken
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import DBAPIError

from app.core.crypto import CryptoService
from app.core.errors import ConnectionTestError, SqlExecutionError, SqlSyntaxError, SqlTimeoutError
from app.core.sql_guard import validate_sql
from app.models.connection import Connection
from app.services.connection_service import (
    SecretDecryptor,
    _build_sqlalchemy_connect_args,
    _build_sqlalchemy_url,
)
from app.services.inferred_type import InferredType, from_cursor_description, infer_from_value

_MYSQL_TIMEOUT_ERROR_CODES = frozenset({3024, 1317})
_MYSQL_SYNTAX_ERROR_CODES = frozenset({1064, 1149})
_PASSWORD_DECRYPT_ERROR = "Unable to decrypt connection password. Please update the saved password."


@dataclass(slots=True)
class Column:
    name: str
    sql_type: str
    inferred_type: InferredType


@dataclass(slots=True)
class ExecutorResult:
    columns: list[Column]
    rows: list[dict[str, Any]]
    duration_ms: int
    truncated: bool


class ExecutorService:
    def __init__(self, crypto_service: SecretDecryptor | None = None) -> None:
        self._crypto_service = crypto_service or CryptoService()
        self._engine_cache: dict[int, Engine] = {}
        self._engine_lock = threading.Lock()

    def execute(
        self,
        connection: Connection,
        sql: str,
        *,
        timeout: int,
        row_limit: int,
    ) -> ExecutorResult:
        validate_sql(sql)
        start = time.perf_counter()

        try:
            engine = self._get_or_create_engine(connection)
            with engine.connect() as raw_conn:
                conn = raw_conn.execution_options(
                    isolation_level="AUTOCOMMIT",
                    stream_results=True,
                    max_row_buffer=row_limit + 1,
                )
                conn.exec_driver_sql(f"SET SESSION MAX_EXECUTION_TIME={timeout * 1000}")
                result = conn.exec_driver_sql(sql)
                try:
                    cursor = result.cursor
                    description = cursor.description if cursor is not None else ()
                    rows_raw = result.fetchmany(row_limit + 1)
                finally:
                    result.close()
        except DBAPIError as exc:
            self._raise_sql_error(exc, timeout=timeout)
        except (OSError, TypeError, ValueError) as exc:
            raise SqlExecutionError(
                code="SQL_EXECUTION_ERROR",
                detail={"orig": str(exc)},
            ) from exc

        truncated = len(rows_raw) > row_limit
        if truncated:
            rows_raw = rows_raw[:row_limit]

        columns = self._build_columns(description)
        self._promote_text_json_columns(columns, rows_raw)
        rows = self._build_rows(columns, rows_raw)
        duration_ms = int((time.perf_counter() - start) * 1000)
        return ExecutorResult(
            columns=columns,
            rows=rows,
            duration_ms=duration_ms,
            truncated=truncated,
        )

    def _get_or_create_engine(self, connection: Connection) -> Engine:
        with self._engine_lock:
            cached = self._engine_cache.get(connection.id)
            if cached is not None:
                return cached

            try:
                url = _build_sqlalchemy_url(connection, self._crypto_service)
            except InvalidToken as exc:
                raise ConnectionTestError(
                    code="CONN_SECRET_DECRYPT_FAILED",
                    message=_PASSWORD_DECRYPT_ERROR,
                    detail={"connection_id": connection.id},
                ) from exc
            connect_args = {
                **_build_sqlalchemy_connect_args(connection),
                "connect_timeout": 5,
            }

            engine = create_engine(
                url,
                pool_size=5,
                pool_recycle=3600,
                pool_pre_ping=True,
                connect_args=connect_args,
            )
            self._engine_cache[connection.id] = engine
            return engine

    def invalidate_engine(self, connection_id: int) -> None:
        with self._engine_lock:
            engine = self._engine_cache.pop(connection_id, None)
        if engine is not None:
            engine.dispose()

    def _build_columns(self, description: Iterable[Sequence[Any]]) -> list[Column]:
        columns: list[Column] = []
        column_name_counts: dict[str, int] = {}
        used_column_names: set[str] = set()
        for desc_item in description:
            sql_type, inferred = from_cursor_description(desc_item)
            column_name = _unique_column_name(
                str(desc_item[0]),
                column_name_counts,
                used_column_names,
            )
            columns.append(Column(name=column_name, sql_type=sql_type, inferred_type=inferred))
        return columns

    def _promote_text_json_columns(
        self,
        columns: list[Column],
        rows_raw: Sequence[Sequence[Any]],
    ) -> None:
        for index, column in enumerate(columns):
            if column.inferred_type != "text":
                continue
            for row_raw in rows_raw:
                row_values = _row_values(row_raw)
                if index >= len(row_values):
                    continue
                if infer_from_value(row_values[index]) == "json":
                    column.inferred_type = "json"
                    break

    def _build_rows(
        self,
        columns: Sequence[Column],
        rows_raw: Sequence[Sequence[Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row_raw in rows_raw:
            row_values = _row_values(row_raw)
            row: dict[str, Any] = {}
            for column, value in zip(columns, row_values, strict=False):
                row[column.name] = _serialize_value(value, column.inferred_type)
            rows.append(row)
        return rows

    def _raise_sql_error(self, exc: DBAPIError, *, timeout: int) -> NoReturn:
        error_code = _extract_operational_error_code(exc)
        if error_code in _MYSQL_TIMEOUT_ERROR_CODES or "max_execution_time" in str(exc).lower():
            raise SqlTimeoutError(
                detail={"timeout": timeout, "orig": str(exc)},
            ) from exc
        if error_code in _MYSQL_SYNTAX_ERROR_CODES:
            raise SqlSyntaxError(
                code="SQL_SYNTAX_ERROR",
                detail={"orig": str(exc)},
            ) from exc

        raise SqlExecutionError(
            code="SQL_EXECUTION_ERROR",
            detail={"orig": str(exc)},
        ) from exc


def _row_values(row_raw: Sequence[Any]) -> tuple[Any, ...]:
    return tuple(row_raw)


def _unique_column_name(
    base_name: str,
    column_name_counts: dict[str, int],
    used_column_names: set[str],
) -> str:
    count = column_name_counts.get(base_name, 0) + 1
    column_name_counts[base_name] = count
    candidate = base_name if count == 1 else f"{base_name}__{count}"
    while candidate in used_column_names:
        count += 1
        column_name_counts[base_name] = count
        candidate = f"{base_name}__{count}"
    used_column_names.add(candidate)
    return candidate


def _serialize_value(value: Any, inferred_type: InferredType) -> Any:
    serialized: Any
    if value is None:
        serialized = None
    elif inferred_type == "json":
        serialized = _serialize_json_value(value)
    elif inferred_type == "timestamp" and isinstance(value, datetime | date):
        serialized = value.isoformat()
    elif inferred_type == "binary" and isinstance(value, bytes | bytearray | memoryview):
        serialized = base64.b64encode(bytes(value)).decode("ascii")
    elif inferred_type == "text" and isinstance(value, bytes | bytearray | memoryview):
        try:
            serialized = bytes(value).decode("utf-8")
        except UnicodeDecodeError:
            serialized = base64.b64encode(bytes(value)).decode("ascii")
    elif inferred_type == "float" and isinstance(value, Decimal):
        serialized = float(value)
    else:
        serialized = value
    return serialized


def _serialize_json_value(value: Any) -> Any:
    if isinstance(value, dict | list):
        return value
    if isinstance(value, bytes | bytearray | memoryview):
        try:
            value = bytes(value).decode("utf-8")
        except UnicodeDecodeError:
            return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _extract_operational_error_code(exc: DBAPIError) -> int | None:
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", ())
    if isinstance(args, tuple) and args and isinstance(args[0], int):
        return args[0]
    return None
