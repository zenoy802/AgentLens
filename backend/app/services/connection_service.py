from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter

import pymysql  # type: ignore[import-untyped]
from pymysql import MySQLError
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.errors import ConflictError, NotFoundError
from app.models.connection import Connection
from app.schemas.common import Pagination
from app.schemas.connection import (
    ConnectionCreate,
    ConnectionListResponse,
    ConnectionRead,
    ConnectionTestResponse,
    ConnectionUpdate,
)


@dataclass(slots=True)
class ConnectionTestResult:
    ok: bool
    latency_ms: int | None
    server_version: str | None
    tested_at: datetime
    error: str | None = None


class ConnectionService:
    def __init__(self, session: Session) -> None:
        self.session = session

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
        return self._to_read_model(connection)

    def delete_connection(self, connection_id: int) -> None:
        connection = self._get_connection_or_raise(connection_id)
        self.session.delete(connection)
        self.session.commit()

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
            connect_kwargs: dict[str, object] = {
                "host": connection.host,
                "port": connection.port or 3306,
                "user": connection.username,
                "password": decrypt_secret(connection.password_enc),
                "database": connection.database,
                "connect_timeout": connection.default_timeout,
                **extra_params,
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

    def _commit_or_raise_conflict(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
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
        return json.dumps(dict(extra_params))

    @staticmethod
    def _load_extra_params(raw_extra_params: str | None) -> dict[str, object]:
        if raw_extra_params is None:
            return {}
        loaded = json.loads(raw_extra_params)
        if isinstance(loaded, dict):
            return loaded
        return {}

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
