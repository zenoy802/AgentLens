from __future__ import annotations

from typing import NoReturn, cast

import pytest
from loguru import logger
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.errors import SqlTimeoutError
from app.db.session import get_session_factory, initialize_metadata_database
from app.models.connection import Connection
from app.models.label import LabelSchema
from app.models.misc import QueryHistory
from app.models.named_query import NamedQuery
from app.models.view_config import ViewConfig
from app.services.query_executor import ExecutorService
from app.services.query_service import QueryService


class FailingExecutor:
    def execute(
        self,
        connection: Connection,
        sql: str,
        *,
        timeout: int,
        row_limit: int,
        query_id: int | None = None,
        sql_fingerprint: str | None = None,
    ) -> NoReturn:
        assert connection.id > 0
        assert sql == "SELECT 'super-secret'"
        assert timeout > 0
        assert row_limit > 0
        assert query_id is None or query_id > 0
        assert sql_fingerprint is None or sql_fingerprint.startswith("sha256:")
        cause = OperationalError(
            sql,
            {"password": "super-secret"},
            Exception(3024, "query timeout"),
        )
        raise SqlTimeoutError() from cause


def _create_query(session: Session) -> int:
    connection = Connection(
        name="query-service-mysql",
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
    query = NamedQuery(
        connection_id=connection.id,
        name=None,
        sql_text="SELECT 'super-secret'",
        is_named=False,
    )
    query.view_config = ViewConfig(field_renders="{}", table_config="{}")
    query.label_schema = LabelSchema(fields="[]")
    session.add(query)
    session.commit()
    return query.id


def _capture_warning_logs() -> tuple[list[str], int]:
    messages: list[str] = []
    sink_id = logger.add(
        lambda message: messages.append(str(message)),
        format="{message}\n{exception}",
        level="WARNING",
    )
    return messages, sink_id


def _assert_logs_do_not_contain_sql_or_params(logs: str) -> None:
    assert "super-secret" not in logs
    assert "SELECT" not in logs
    assert "parameters" not in logs.lower()


def test_execute_and_record_failure_log_omits_statement_and_parameters() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    messages, sink_id = _capture_warning_logs()
    try:
        query_id = _create_query(session)
        query = session.get(NamedQuery, query_id)
        assert query is not None
        service = QueryService(session, cast(ExecutorService, FailingExecutor()))

        with pytest.raises(SqlTimeoutError):
            service.execute_and_record(query, timeout=1, row_limit=10)

        logs = "\n".join(messages)
        assert "Query execution failed" in logs
        assert "SQL_TIMEOUT" in logs
        _assert_logs_do_not_contain_sql_or_params(logs)
        history = session.query(QueryHistory).filter_by(query_id=query_id).one()
        assert history.error_message == "SQL execution timed out."
    finally:
        logger.remove(sink_id)
        session.close()


def test_execute_readonly_failure_log_omits_statement_and_parameters() -> None:
    initialize_metadata_database()
    session = get_session_factory()()
    messages, sink_id = _capture_warning_logs()
    try:
        query_id = _create_query(session)
        query = session.get(NamedQuery, query_id)
        assert query is not None
        service = QueryService(session, cast(ExecutorService, FailingExecutor()))

        with pytest.raises(SqlTimeoutError):
            service.execute_readonly(query, timeout=1, row_limit=10)

        logs = "\n".join(messages)
        assert "Readonly query execution failed" in logs
        assert "SQL_TIMEOUT" in logs
        _assert_logs_do_not_contain_sql_or_params(logs)
    finally:
        logger.remove(sink_id)
        session.close()
