from __future__ import annotations

import base64
import json
import threading
import time
from collections.abc import Iterable, Mapping, Sequence
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
    ConnectionService,
    SecretDecryptor,
    _build_odps_client,
    _build_odps_reader_kwargs,
    _build_odps_run_kwargs,
    _build_sqlalchemy_connect_args,
    _build_sqlalchemy_url,
    _is_odps_timeout_error,
    _stop_odps_instance,
)
from app.services.inferred_type import (
    InferredType,
    from_cursor_description,
    from_sql_type_name,
    infer_from_value,
)

_DB_TYPE_MYSQL = "mysql"
_DB_TYPE_ODPS = "odps"
_MYSQL_TIMEOUT_ERROR_CODES = frozenset({3024, 1317})
_MYSQL_SYNTAX_ERROR_CODES = frozenset({1064, 1149})
_PASSWORD_DECRYPT_ERROR = "Unable to decrypt connection password. Please update the saved password."
_PYODPS_MISSING_ERROR = "PyODPS is not installed. Install the backend dependency 'pyodps'."


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
        if connection.db_type == _DB_TYPE_ODPS:
            return self._execute_odps(connection, sql, timeout=timeout, row_limit=row_limit)
        if connection.db_type != _DB_TYPE_MYSQL:
            raise SqlExecutionError(
                code="SQL_UNSUPPORTED_DB_TYPE",
                detail={"db_type": connection.db_type},
            )

        return self._execute_mysql(connection, sql, timeout=timeout, row_limit=row_limit)

    def _execute_mysql(
        self,
        connection: Connection,
        sql: str,
        *,
        timeout: int,
        row_limit: int,
    ) -> ExecutorResult:
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
                result = conn.exec_driver_sql(sql.replace("%", "%%"))
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

    def _execute_odps(
        self,
        connection: Connection,
        sql: str,
        *,
        timeout: int,
        row_limit: int,
    ) -> ExecutorResult:
        start = time.perf_counter()
        instance: Any | None = None
        try:
            extra_params = _load_odps_extra_params(connection)
            odps_client = _build_odps_client(connection, self._crypto_service)
            instance = odps_client.run_sql(sql, **_build_odps_run_kwargs(extra_params))
            try:
                instance.wait_for_success(timeout=timeout)
            except Exception as exc:
                if _is_odps_timeout_error(exc):
                    _stop_odps_instance(instance)
                    raise SqlTimeoutError(detail={"timeout": timeout, "orig": str(exc)}) from exc
                raise

            with instance.open_reader(**_build_odps_reader_kwargs(extra_params)) as reader:
                rows_raw = _fetch_odps_rows(reader, row_limit + 1)
                columns = self._build_odps_columns(reader, rows_raw)
        except InvalidToken as exc:
            raise ConnectionTestError(
                code="CONN_SECRET_DECRYPT_FAILED",
                message=_PASSWORD_DECRYPT_ERROR,
                detail={"connection_id": connection.id},
            ) from exc
        except ModuleNotFoundError as exc:
            raise SqlExecutionError(
                code="SQL_EXECUTION_ERROR",
                message=_PYODPS_MISSING_ERROR,
                detail={"db_type": connection.db_type},
            ) from exc
        except SqlTimeoutError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise SqlExecutionError(
                code="SQL_EXECUTION_ERROR",
                detail={"orig": str(exc)},
            ) from exc
        except Exception as exc:
            if _is_odps_timeout_error(exc):
                if instance is not None:
                    _stop_odps_instance(instance)
                raise SqlTimeoutError(detail={"timeout": timeout, "orig": str(exc)}) from exc
            raise SqlExecutionError(
                code="SQL_EXECUTION_ERROR",
                detail={"orig": str(exc)},
            ) from exc

        truncated = len(rows_raw) > row_limit
        if truncated:
            rows_raw = rows_raw[:row_limit]

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

    def _build_odps_columns(self, reader: Any, rows_raw: Sequence[Any]) -> list[Column]:
        column_specs = _extract_odps_column_specs(reader)
        if not column_specs and rows_raw:
            column_specs = _extract_odps_column_specs(rows_raw[0])
        if not column_specs and rows_raw:
            column_specs = [
                (f"column_{index + 1}", "UNKNOWN") for index in range(len(_row_values(rows_raw[0])))
            ]

        columns: list[Column] = []
        column_name_counts: dict[str, int] = {}
        used_column_names: set[str] = set()
        for column_name_raw, type_name_raw in column_specs:
            sql_type, inferred = from_sql_type_name(type_name_raw)
            column_name = _unique_column_name(
                str(column_name_raw),
                column_name_counts,
                used_column_names,
            )
            columns.append(Column(name=column_name, sql_type=sql_type, inferred_type=inferred))
        return columns

    def _promote_text_json_columns(
        self,
        columns: list[Column],
        rows_raw: Sequence[Any],
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
        rows_raw: Sequence[Any],
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


def _load_odps_extra_params(connection: Connection) -> dict[str, object]:
    return ConnectionService._load_extra_params(
        connection.extra_params,
        db_type=connection.db_type,
    )


def _fetch_odps_rows(reader: Any, size: int) -> list[Any]:
    rows: list[Any] = []
    for row in reader:
        rows.append(row)
        if len(rows) >= size:
            break
    return rows


def _extract_odps_column_specs(source: Any) -> list[tuple[str, object]]:
    schema = _first_present_attr(source, ("schema", "_schema"))
    specs = _extract_odps_column_specs_from_schema(schema)
    if specs:
        return specs

    columns = _first_present_attr(source, ("columns", "_columns"))
    return _extract_odps_column_specs_from_columns(columns)


def _extract_odps_column_specs_from_schema(schema: Any) -> list[tuple[str, object]]:
    if schema is None:
        return []
    columns = _first_present_attr(schema, ("columns", "_columns"))
    specs = _extract_odps_column_specs_from_columns(columns)
    if specs:
        return specs

    names = getattr(schema, "names", None)
    types = getattr(schema, "types", None)
    if isinstance(names, Sequence) and isinstance(types, Sequence):
        return [(str(name), type_name) for name, type_name in zip(names, types, strict=False)]
    return []


def _extract_odps_column_specs_from_columns(columns: Any) -> list[tuple[str, object]]:
    if not isinstance(columns, Sequence):
        return []
    specs: list[tuple[str, object]] = []
    for column in columns:
        name = getattr(column, "name", None)
        type_name = getattr(column, "type", None)
        if name is not None:
            specs.append((str(name), type_name if type_name is not None else "UNKNOWN"))
    return specs


def _first_present_attr(source: Any, names: Sequence[str]) -> Any:
    if source is None:
        return None
    for name in names:
        value = getattr(source, name, None)
        if value is not None:
            return value
    return None


def _row_values(row_raw: Any) -> tuple[Any, ...]:
    if isinstance(row_raw, Mapping):
        return tuple(row_raw.values())
    values_attr = getattr(row_raw, "values", None)
    if isinstance(values_attr, Sequence) and not isinstance(values_attr, str | bytes | bytearray):
        return tuple(values_attr)
    if isinstance(row_raw, Sequence) and not isinstance(row_raw, str | bytes | bytearray):
        return tuple(row_raw)
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
