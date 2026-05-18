from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from json import JSONDecodeError
from time import perf_counter
from typing import TYPE_CHECKING, Any, Protocol

import pymysql  # type: ignore[import-untyped]
from cryptography.fernet import InvalidToken
from pymysql import MySQLError
from sqlalchemy import URL, Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.connection import Connection
from app.schemas.common import Pagination
from app.schemas.connection import (
    ConnectionCreate,
    ConnectionListResponse,
    ConnectionRead,
    ConnectionTestResponse,
    ConnectionUpdate,
)

if TYPE_CHECKING:
    from app.services.query_executor import ExecutorService

_DB_TYPE_MYSQL = "mysql"
_DB_TYPE_ODPS = "odps"
_SUPPORTED_DB_TYPES = frozenset({_DB_TYPE_MYSQL, _DB_TYPE_ODPS})
_PROTECTED_EXTRA_PARAM_KEYS = frozenset(
    {
        "access_id",
        "access_key",
        "connect_timeout",
        "database",
        "db",
        "endpoint",
        "host",
        "passwd",
        "password",
        "port",
        "project",
        "secret_access_key",
        "user",
        "username",
    }
)
_MYSQL_ALLOWED_EXTRA_PARAM_KEYS = frozenset(
    {
        "charset",
        "read_timeout",
        "ssl_ca",
        "ssl_cert",
        "ssl_key",
        "ssl_verify_cert",
        "ssl_verify_identity",
        "write_timeout",
    }
)
_ODPS_ALLOWED_EXTRA_PARAM_KEYS = frozenset(
    {
        "limit",
        "quota_name",
        "tunnel",
        "tunnel_endpoint",
    }
)
_PASSWORD_DECRYPT_ERROR = "Unable to decrypt connection password. Please update the saved password."
_PYODPS_MISSING_ERROR = "PyODPS is not installed. Install the backend dependency 'pyodps'."


class SecretDecryptor(Protocol):
    def decrypt_secret(self, value: bytes | None) -> str | None: ...


@dataclass(slots=True)
class ConnectionTestResult:
    ok: bool
    latency_ms: int | None
    server_version: str | None
    tested_at: datetime
    error: str | None = None


class ConnectionService:
    def __init__(
        self,
        session: Session,
        executor_service: ExecutorService | None = None,
    ) -> None:
        self.session = session
        self._executor_service = executor_service

    def list_connections(self, *, page: int, page_size: int) -> ConnectionListResponse:
        total = self.session.scalar(select(func.count()).select_from(Connection))
        total_records = total or 0
        total_pages = max((total_records + page_size - 1) // page_size, 1)

        stmt: Select[tuple[Connection]] = (
            select(Connection)
            .order_by(Connection.created_at.desc(), Connection.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = self.session.scalars(stmt).all()
        return ConnectionListResponse(
            items=[self._to_read_model(connection) for connection in items],
            pagination=Pagination(
                page=page,
                page_size=page_size,
                total=total_records,
                total_pages=total_pages,
            ),
        )

    def create_connection(self, payload: ConnectionCreate) -> ConnectionRead:
        password_enc = encrypt_secret(payload.password) if payload.password else None
        self._validate_connection_fields(
            db_type=payload.db_type,
            host=payload.host,
            database=payload.database,
            username=payload.username,
            password_enc=password_enc,
        )
        connection = Connection(
            name=payload.name,
            db_type=payload.db_type,
            host=payload.host,
            port=payload.port,
            database=payload.database,
            username=payload.username,
            password_enc=password_enc,
            extra_params=self._dump_extra_params(payload.extra_params, db_type=payload.db_type),
            default_timeout=payload.default_timeout,
            default_row_limit=payload.default_row_limit,
        )
        self.session.add(connection)
        self._commit_or_raise_conflict()
        self.session.refresh(connection)
        return self._to_read_model(connection)

    def get_connection(self, connection_id: int) -> ConnectionRead:
        connection = self._get_connection_or_raise(connection_id)
        return self._to_read_model(connection)

    def update_connection(self, connection_id: int, payload: ConnectionUpdate) -> ConnectionRead:
        connection = self._get_connection_or_raise(connection_id)
        updates = payload.model_dump(exclude_unset=True)
        new_db_type_raw = updates.get("db_type", connection.db_type)
        if not isinstance(new_db_type_raw, str):
            raise ValidationError(
                code="CONN_UNSUPPORTED_DB_TYPE",
                message="Unsupported database type.",
                detail={"db_type": new_db_type_raw},
            )
        new_db_type = new_db_type_raw
        if connection.db_type != new_db_type:
            new_password = updates.get("password")
            if not isinstance(new_password, str) or not new_password:
                raise ValidationError(
                    code="CONN_REQUIRED_FIELD_MISSING",
                    message="Changing database type requires a new password or secret.",
                    detail={"fields": ["password"]},
                )

        for field_name in (
            "name",
            "db_type",
            "host",
            "port",
            "database",
            "username",
            "default_timeout",
            "default_row_limit",
        ):
            if field_name in updates:
                setattr(connection, field_name, updates[field_name])

        if "password" in updates:
            password = updates["password"]
            connection.password_enc = encrypt_secret(password) if password else None

        if "extra_params" in updates:
            connection.extra_params = self._dump_extra_params(
                updates["extra_params"],
                db_type=new_db_type,
            )
        elif "db_type" in updates:
            self._load_extra_params(connection.extra_params, db_type=new_db_type)

        self._validate_connection_fields(
            db_type=new_db_type,
            host=connection.host,
            database=connection.database,
            username=connection.username,
            password_enc=connection.password_enc,
        )

        self._commit_or_raise_conflict()
        self.session.refresh(connection)
        self._invalidate_executor_engine(connection_id)
        return self._to_read_model(connection)

    def delete_connection(self, connection_id: int) -> None:
        connection = self._get_connection_or_raise(connection_id)
        self.session.delete(connection)
        self.session.commit()
        self._invalidate_executor_engine(connection_id)

    def test_connection(self, connection_id: int) -> ConnectionTestResponse:
        connection = self._get_connection_or_raise(connection_id)
        result = self._execute_connection_test(connection)
        connection.last_tested_at = result.tested_at
        connection.last_test_ok = result.ok
        self.session.commit()
        self.session.refresh(connection)
        return ConnectionTestResponse(
            ok=result.ok,
            latency_ms=result.latency_ms,
            server_version=result.server_version,
            tested_at=result.tested_at,
            error=result.error,
        )

    def _get_connection_or_raise(self, connection_id: int) -> Connection:
        connection = self.session.get(Connection, connection_id)
        if connection is None:
            raise NotFoundError(
                code="NOT_FOUND",
                message="Connection not found.",
                detail={"connection_id": connection_id},
            )
        return connection

    def _execute_connection_test(self, connection: Connection) -> ConnectionTestResult:
        if connection.db_type == _DB_TYPE_ODPS:
            return self._execute_odps_connection_test(connection)
        if connection.db_type != _DB_TYPE_MYSQL:
            return ConnectionTestResult(
                ok=False,
                latency_ms=None,
                server_version=None,
                tested_at=datetime.now(UTC),
                error=f"Unsupported database type: {connection.db_type}",
            )
        return self._execute_mysql_connection_test(connection)

    def _execute_mysql_connection_test(self, connection: Connection) -> ConnectionTestResult:
        tested_at = datetime.now(UTC)
        start = perf_counter()
        try:
            extra_params = self._load_extra_params(
                connection.extra_params,
                db_type=connection.db_type,
            )
            try:
                password = decrypt_secret(connection.password_enc)
            except InvalidToken:
                return ConnectionTestResult(
                    ok=False,
                    latency_ms=None,
                    server_version=None,
                    tested_at=tested_at,
                    error=_PASSWORD_DECRYPT_ERROR,
                )

            connect_kwargs: dict[str, object] = {
                **extra_params,
                "host": connection.host,
                "port": connection.port or 3306,
                "user": connection.username,
                "password": password,
                "database": connection.database,
                "connect_timeout": connection.default_timeout,
            }
            connect_kwargs = {
                key: value for key, value in connect_kwargs.items() if value is not None
            }

            db_connection = pymysql.connect(**connect_kwargs)
            try:
                with db_connection.cursor() as cursor:
                    cursor.execute("SELECT VERSION()")
                    version_row = cursor.fetchone()
                server_version = (
                    self._extract_server_version(version_row) or db_connection.get_server_info()
                )
            finally:
                db_connection.close()

            latency_ms = int((perf_counter() - start) * 1000)
            return ConnectionTestResult(
                ok=True,
                latency_ms=latency_ms,
                server_version=server_version,
                tested_at=tested_at,
            )
        except MySQLError as exc:
            return ConnectionTestResult(
                ok=False,
                latency_ms=None,
                server_version=None,
                tested_at=tested_at,
                error=str(exc),
            )
        except OSError as exc:
            return ConnectionTestResult(
                ok=False,
                latency_ms=None,
                server_version=None,
                tested_at=tested_at,
                error=f"Invalid MySQL connection parameters: {exc}",
            )
        except (TypeError, ValueError) as exc:
            return ConnectionTestResult(
                ok=False,
                latency_ms=None,
                server_version=None,
                tested_at=tested_at,
                error=f"Invalid MySQL connection parameters: {exc}",
            )

    def _execute_odps_connection_test(self, connection: Connection) -> ConnectionTestResult:
        tested_at = datetime.now(UTC)
        start = perf_counter()
        try:
            extra_params = self._load_extra_params(
                connection.extra_params,
                db_type=connection.db_type,
            )
            odps_client = _build_odps_client(connection)
            instance = odps_client.run_sql("SELECT 1", **_build_odps_run_kwargs(extra_params))
            try:
                instance.wait_for_success(timeout=connection.default_timeout)
            except Exception as exc:
                if _is_odps_timeout_error(exc):
                    _stop_odps_instance(instance)
                raise
            with instance.open_reader(**_build_odps_reader_kwargs(extra_params)) as reader:
                _read_single_odps_row(reader)
            latency_ms = int((perf_counter() - start) * 1000)
            return ConnectionTestResult(
                ok=True,
                latency_ms=latency_ms,
                server_version="MaxCompute/ODPS",
                tested_at=tested_at,
            )
        except InvalidToken:
            return ConnectionTestResult(
                ok=False,
                latency_ms=None,
                server_version=None,
                tested_at=tested_at,
                error=_PASSWORD_DECRYPT_ERROR,
            )
        except ModuleNotFoundError:
            return ConnectionTestResult(
                ok=False,
                latency_ms=None,
                server_version=None,
                tested_at=tested_at,
                error=_PYODPS_MISSING_ERROR,
            )
        except (OSError, TypeError, ValueError) as exc:
            return ConnectionTestResult(
                ok=False,
                latency_ms=None,
                server_version=None,
                tested_at=tested_at,
                error=f"Invalid MaxCompute connection parameters: {exc}",
            )
        except Exception as exc:
            return ConnectionTestResult(
                ok=False,
                latency_ms=None,
                server_version=None,
                tested_at=tested_at,
                error=str(exc),
            )

    def _commit_or_raise_conflict(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            if not self._is_connection_name_conflict(exc):
                raise ConflictError(
                    code="DB_INTEGRITY_CONFLICT",
                    message="Database integrity constraint failed.",
                ) from exc

            raise ConflictError(
                code="CONN_NAME_CONFLICT",
                message="Connection name already exists.",
            ) from exc

    @staticmethod
    def _extract_server_version(version_row: object) -> str | None:
        if isinstance(version_row, tuple) and version_row:
            raw = version_row[0]
            return str(raw) if raw is not None else None
        return None

    @staticmethod
    def _dump_extra_params(
        extra_params: Mapping[str, object] | None,
        *,
        db_type: str,
    ) -> str | None:
        if extra_params is None:
            return None
        normalized_extra_params = dict(extra_params)
        protected_keys = ConnectionService._find_forbidden_extra_param_keys(
            normalized_extra_params,
            db_type=db_type,
        )
        if protected_keys:
            raise ValidationError(
                code="CONN_EXTRA_PARAMS_FORBIDDEN",
                message="extra_params contains unsupported or unsafe keys.",
                detail={"keys": protected_keys},
            )
        invalid_keys = ConnectionService._find_invalid_extra_param_value_keys(
            normalized_extra_params,
            db_type=db_type,
        )
        if invalid_keys:
            raise ValidationError(
                code="CONN_EXTRA_PARAMS_INVALID",
                message="extra_params contains invalid value types.",
                detail={"keys": invalid_keys},
            )
        return json.dumps(normalized_extra_params)

    @staticmethod
    def _load_extra_params(raw_extra_params: str | None, *, db_type: str) -> dict[str, object]:
        if raw_extra_params is None:
            return {}
        try:
            loaded = json.loads(raw_extra_params)
        except JSONDecodeError as exc:
            raise ValidationError(
                code="CONN_EXTRA_PARAMS_INVALID",
                message="extra_params must be a valid JSON object.",
            ) from exc
        if isinstance(loaded, dict):
            protected_keys = ConnectionService._find_forbidden_extra_param_keys(
                loaded,
                db_type=db_type,
            )
            if protected_keys:
                raise ValidationError(
                    code="CONN_EXTRA_PARAMS_FORBIDDEN",
                    message="extra_params contains unsupported or unsafe keys.",
                    detail={"keys": protected_keys},
                )
            invalid_keys = ConnectionService._find_invalid_extra_param_value_keys(
                loaded,
                db_type=db_type,
            )
            if invalid_keys:
                raise ValidationError(
                    code="CONN_EXTRA_PARAMS_INVALID",
                    message="extra_params contains invalid value types.",
                    detail={"keys": invalid_keys},
                )
            return loaded
        return {}

    @staticmethod
    def _find_forbidden_extra_param_keys(
        extra_params: Mapping[str, object],
        *,
        db_type: str,
    ) -> list[str]:
        allowed_keys = ConnectionService._allowed_extra_param_keys(db_type)
        return sorted(
            key
            for key in extra_params
            if key.lower() in _PROTECTED_EXTRA_PARAM_KEYS or key not in allowed_keys
        )

    @staticmethod
    def _find_invalid_extra_param_value_keys(
        extra_params: Mapping[str, object],
        *,
        db_type: str,
    ) -> list[str]:
        if db_type == _DB_TYPE_ODPS:
            return ConnectionService._find_invalid_odps_extra_param_value_keys(extra_params)

        invalid_keys: list[str] = []
        for key, value in extra_params.items():
            invalid_string_value = key in {
                "charset",
                "ssl_ca",
                "ssl_cert",
                "ssl_key",
            } and not isinstance(value, str)
            invalid_boolean_value = key in {
                "ssl_verify_cert",
                "ssl_verify_identity",
            } and not isinstance(value, bool)
            invalid_timeout_value = key in {"read_timeout", "write_timeout"} and (
                isinstance(value, bool) or not isinstance(value, int | float) or value <= 0
            )
            if invalid_string_value or invalid_boolean_value or invalid_timeout_value:
                invalid_keys.append(key)
        return sorted(invalid_keys)

    @staticmethod
    def _find_invalid_odps_extra_param_value_keys(
        extra_params: Mapping[str, object],
    ) -> list[str]:
        invalid_keys: list[str] = []
        for key, value in extra_params.items():
            invalid_string_value = key in {"quota_name", "tunnel_endpoint"} and not isinstance(
                value,
                str,
            )
            invalid_boolean_value = key in {"limit", "tunnel"} and not isinstance(value, bool)
            if invalid_string_value or invalid_boolean_value:
                invalid_keys.append(key)
        return sorted(invalid_keys)

    @staticmethod
    def _allowed_extra_param_keys(db_type: str) -> frozenset[str]:
        if db_type == _DB_TYPE_ODPS:
            return _ODPS_ALLOWED_EXTRA_PARAM_KEYS
        return _MYSQL_ALLOWED_EXTRA_PARAM_KEYS

    @staticmethod
    def _validate_connection_fields(
        *,
        db_type: str,
        host: str | None,
        database: str | None,
        username: str | None,
        password_enc: bytes | None,
    ) -> None:
        if db_type not in _SUPPORTED_DB_TYPES:
            raise ValidationError(
                code="CONN_UNSUPPORTED_DB_TYPE",
                message="Unsupported database type.",
                detail={"db_type": db_type},
            )
        if db_type != _DB_TYPE_ODPS:
            return

        missing_fields: list[str] = []
        if not host:
            missing_fields.append("host")
        if not database:
            missing_fields.append("database")
        if not username:
            missing_fields.append("username")
        if password_enc is None:
            missing_fields.append("password")
        if missing_fields:
            raise ValidationError(
                code="CONN_REQUIRED_FIELD_MISSING",
                message=(
                    "MaxCompute connections require endpoint, project, AccessKey ID and secret."
                ),
                detail={"fields": missing_fields},
            )

    @staticmethod
    def _is_connection_name_conflict(exc: IntegrityError) -> bool:
        return "connections.name" in str(exc.orig)

    def _invalidate_executor_engine(self, connection_id: int) -> None:
        if self._executor_service is not None:
            self._executor_service.invalidate_engine(connection_id)

    def _to_read_model(self, connection: Connection) -> ConnectionRead:
        return ConnectionRead.model_validate(
            {
                "id": connection.id,
                "name": connection.name,
                "db_type": connection.db_type,
                "host": connection.host,
                "port": connection.port,
                "database": connection.database,
                "username": connection.username,
                "extra_params": self._load_extra_params(
                    connection.extra_params,
                    db_type=connection.db_type,
                ),
                "default_timeout": connection.default_timeout,
                "default_row_limit": connection.default_row_limit,
                "created_at": connection.created_at,
                "updated_at": connection.updated_at,
                "last_tested_at": connection.last_tested_at,
                "last_test_ok": connection.last_test_ok,
            }
        )


def _build_sqlalchemy_url(
    connection: Connection,
    crypto_service: SecretDecryptor | None = None,
) -> URL:
    if connection.db_type != _DB_TYPE_MYSQL:
        raise ValidationError(
            code="CONN_UNSUPPORTED_DB_TYPE",
            message="SQLAlchemy execution is only available for MySQL connections.",
            detail={"db_type": connection.db_type},
        )
    password = (
        crypto_service.decrypt_secret(connection.password_enc)
        if crypto_service is not None
        else decrypt_secret(connection.password_enc)
    )
    return URL.create(
        "mysql+pymysql",
        username=connection.username,
        password=password,
        host=connection.host,
        port=connection.port or 3306,
        database=connection.database,
    )


def _build_sqlalchemy_connect_args(connection: Connection) -> dict[str, object]:
    return {
        key: value
        for key, value in ConnectionService._load_extra_params(
            connection.extra_params,
            db_type=connection.db_type,
        ).items()
        if value is not None
    }


def _build_odps_client(
    connection: Connection,
    crypto_service: SecretDecryptor | None = None,
) -> Any:
    if connection.db_type != _DB_TYPE_ODPS:
        raise ValidationError(
            code="CONN_UNSUPPORTED_DB_TYPE",
            message="ODPS execution is only available for MaxCompute connections.",
            detail={"db_type": connection.db_type},
        )
    password = (
        crypto_service.decrypt_secret(connection.password_enc)
        if crypto_service is not None
        else decrypt_secret(connection.password_enc)
    )
    ConnectionService._validate_connection_fields(
        db_type=connection.db_type,
        host=connection.host,
        database=connection.database,
        username=connection.username,
        password_enc=connection.password_enc,
    )
    extra_params = ConnectionService._load_extra_params(
        connection.extra_params,
        db_type=connection.db_type,
    )
    odps_class = _load_odps_class()
    odps_kwargs = _build_odps_client_kwargs(extra_params)
    return odps_class(
        connection.username,
        password,
        connection.database,
        endpoint=connection.host,
        **odps_kwargs,
    )


def _build_odps_client_kwargs(extra_params: Mapping[str, object]) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    for key in ("quota_name", "tunnel_endpoint"):
        value = extra_params.get(key)
        if value is not None:
            kwargs[key] = value
    return kwargs


def _build_odps_run_kwargs(extra_params: Mapping[str, object]) -> dict[str, object]:
    quota_name = extra_params.get("quota_name")
    if quota_name is None:
        return {}
    return {"quota_name": quota_name}


def _build_odps_reader_kwargs(extra_params: Mapping[str, object]) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    for key in ("limit", "tunnel"):
        value = extra_params.get(key)
        if value is not None:
            kwargs[key] = value
    return kwargs


def _read_single_odps_row(reader: Any) -> None:
    for _row in reader:
        break


def _load_odps_class() -> type[Any]:
    odps_module = import_module("odps")
    odps_class = odps_module.ODPS
    if not isinstance(odps_class, type):
        raise TypeError("odps.ODPS is not a class")
    return odps_class


def _is_odps_timeout_error(exc: BaseException) -> bool:
    class_name = exc.__class__.__name__
    return class_name == "WaitTimeoutError" or "timed out" in str(exc).lower()


def _stop_odps_instance(instance: Any) -> None:
    stop = getattr(instance, "stop", None)
    if callable(stop):
        stop()
