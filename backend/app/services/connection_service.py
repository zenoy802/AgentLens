from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from json import JSONDecodeError
from time import perf_counter
from typing import TYPE_CHECKING, Protocol

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

_PROTECTED_EXTRA_PARAM_KEYS = frozenset(
    {
        "connect_timeout",
        "database",
        "db",
        "host",
        "passwd",
        "password",
        "port",
        "user",
        "username",
    }
)
_ALLOWED_EXTRA_PARAM_KEYS = frozenset(
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
_PASSWORD_DECRYPT_ERROR = "Unable to decrypt connection password. Please update the saved password."


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
        connection = Connection(
            name=payload.name,
            db_type=payload.db_type,
            host=payload.host,
            port=payload.port,
            database=payload.database,
            username=payload.username,
            password_enc=encrypt_secret(payload.password) if payload.password else None,
            extra_params=self._dump_extra_params(payload.extra_params),
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
            connection.extra_params = self._dump_extra_params(updates["extra_params"])

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
        tested_at = datetime.now(UTC)
        start = perf_counter()
        try:
            extra_params = self._load_extra_params(connection.extra_params)
            try:
                password = decrypt_secret(connection.password_enc)
            except (InvalidToken, ValueError):
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
    def _dump_extra_params(extra_params: Mapping[str, object] | None) -> str | None:
        if extra_params is None:
            return None
        normalized_extra_params = dict(extra_params)
        protected_keys = ConnectionService._find_forbidden_extra_param_keys(normalized_extra_params)
        if protected_keys:
            raise ValidationError(
                code="CONN_EXTRA_PARAMS_FORBIDDEN",
                message="extra_params contains unsupported or unsafe keys.",
                detail={"keys": protected_keys},
            )
        invalid_keys = ConnectionService._find_invalid_extra_param_value_keys(
            normalized_extra_params
        )
        if invalid_keys:
            raise ValidationError(
                code="CONN_EXTRA_PARAMS_INVALID",
                message="extra_params contains invalid value types.",
                detail={"keys": invalid_keys},
            )
        return json.dumps(normalized_extra_params)

    @staticmethod
    def _load_extra_params(raw_extra_params: str | None) -> dict[str, object]:
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
            protected_keys = ConnectionService._find_forbidden_extra_param_keys(loaded)
            if protected_keys:
                raise ValidationError(
                    code="CONN_EXTRA_PARAMS_FORBIDDEN",
                    message="extra_params contains unsupported or unsafe keys.",
                    detail={"keys": protected_keys},
                )
            invalid_keys = ConnectionService._find_invalid_extra_param_value_keys(loaded)
            if invalid_keys:
                raise ValidationError(
                    code="CONN_EXTRA_PARAMS_INVALID",
                    message="extra_params contains invalid value types.",
                    detail={"keys": invalid_keys},
                )
            return loaded
        return {}

    @staticmethod
    def _find_forbidden_extra_param_keys(extra_params: Mapping[str, object]) -> list[str]:
        return sorted(
            key
            for key in extra_params
            if key.lower() in _PROTECTED_EXTRA_PARAM_KEYS or key not in _ALLOWED_EXTRA_PARAM_KEYS
        )

    @staticmethod
    def _find_invalid_extra_param_value_keys(extra_params: Mapping[str, object]) -> list[str]:
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
                "extra_params": self._load_extra_params(connection.extra_params),
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
        for key, value in ConnectionService._load_extra_params(connection.extra_params).items()
        if value is not None
    }
