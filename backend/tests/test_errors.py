from __future__ import annotations

import logging
from typing import Any, cast

import httpx
import pymysql  # type: ignore[import-untyped]
import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from loguru import logger
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette import status

from app.core.config import get_settings
from app.core.errors import (
    SqlTimeoutError,
    _validation_error_log_summary,
    register_exception_handlers,
)
from app.core.logging import InterceptHandler, mask_sensitive, sanitize_log_message


def _app_with_error_route(error: Exception) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise error

    return app


def _app_with_chained_error_route(error: Exception, cause: Exception) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise error from cause

    return app


async def _request_and_capture_logs(app: FastAPI) -> tuple[httpx.Response, str]:
    messages: list[str] = []
    sink_id = logger.add(
        lambda message: messages.append(str(message)),
        format="{message}\n{exception}",
        level="WARNING",
    )
    try:
        transport = httpx.ASGITransport(app=cast(Any, app), raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/boom")
    finally:
        logger.remove(sink_id)
    return response, "\n".join(messages)


@pytest.mark.asyncio
async def test_integrity_error_returns_constraint_detail() -> None:
    error = IntegrityError(
        "INSERT",
        {},
        Exception("UNIQUE constraint failed: label_records.query_id, label_records.field_key"),
    )
    transport = httpx.ASGITransport(
        app=cast(Any, _app_with_error_route(error)),
        raise_app_exceptions=False,
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/boom")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    payload = response.json()
    assert payload["error"]["code"] == "DB_INTEGRITY_ERROR"
    assert payload["error"]["detail"]["constraint"] == (
        "label_records.query_id, label_records.field_key"
    )


@pytest.mark.asyncio
async def test_operational_error_hides_traceback_when_debug_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTLENS_DEBUG", "false")
    get_settings.cache_clear()
    error = OperationalError("SELECT 1", {}, Exception("database is locked"))
    transport = httpx.ASGITransport(
        app=cast(Any, _app_with_error_route(error)),
        raise_app_exceptions=False,
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/boom")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json() == {
        "error": {
            "code": "DB_OPERATIONAL_ERROR",
            "message": "Database operation failed.",
            "detail": None,
        }
    }


@pytest.mark.asyncio
async def test_app_error_log_omits_chained_sqlalchemy_statement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTLENS_DEBUG", "false")
    get_settings.cache_clear()
    cause = OperationalError(
        "SELECT 'super-secret'",
        {"password": "super-secret"},
        Exception(3024, "query timeout"),
    )
    response, logs = await _request_and_capture_logs(
        _app_with_chained_error_route(SqlTimeoutError(), cause)
    )

    assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT
    assert response.json()["error"]["code"] == "SQL_TIMEOUT"
    assert "SQL_TIMEOUT" in logs
    assert "SELECT" not in logs
    assert "super-secret" not in logs
    assert "parameters" not in logs.lower()


@pytest.mark.asyncio
async def test_global_sqlalchemy_log_omits_statement_and_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTLENS_DEBUG", "false")
    get_settings.cache_clear()
    error = OperationalError(
        "INSERT INTO annotations (text) VALUES ('super-secret')",
        {"text": "super-secret"},
        Exception("database is locked"),
    )
    response, logs = await _request_and_capture_logs(_app_with_error_route(error))

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["error"]["code"] == "DB_OPERATIONAL_ERROR"
    assert "Database operational error" in logs
    assert "INSERT" not in logs
    assert "super-secret" not in logs
    assert "parameters" not in logs.lower()


@pytest.mark.asyncio
async def test_unhandled_error_log_omits_raw_exception_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTLENS_DEBUG", "false")
    get_settings.cache_clear()
    response, logs = await _request_and_capture_logs(
        _app_with_error_route(RuntimeError("password=super-secret"))
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Unhandled exception" in logs
    assert "password=***" in logs
    assert "super-secret" not in logs
    assert "Traceback" not in logs


@pytest.mark.asyncio
async def test_unhandled_error_includes_traceback_when_debug_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTLENS_DEBUG", "true")
    get_settings.cache_clear()
    transport = httpx.ASGITransport(
        app=cast(Any, _app_with_error_route(RuntimeError("broken"))),
        raise_app_exceptions=False,
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/boom")

    payload = response.json()
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert "RuntimeError: broken" in payload["error"]["detail"]["traceback"]


@pytest.mark.asyncio
async def test_debug_sqlalchemy_error_detail_omits_statement_and_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTLENS_DEBUG", "true")
    get_settings.cache_clear()
    error = OperationalError(
        "INSERT INTO annotations (text) VALUES ('super-secret')",
        {"password": "super-secret"},
        Exception("database is locked"),
    )
    transport = httpx.ASGITransport(
        app=cast(Any, _app_with_error_route(error)),
        raise_app_exceptions=False,
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/boom")

    payload = response.json()
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert payload["error"]["code"] == "DB_OPERATIONAL_ERROR"
    detail = str(payload["error"]["detail"])
    assert "OperationalError" in detail
    assert "INSERT" not in detail
    assert "super-secret" not in detail
    assert "parameters" not in detail.lower()


@pytest.mark.asyncio
async def test_httpx_timeout_maps_to_http_client_timeout() -> None:
    transport = httpx.ASGITransport(
        app=cast(Any, _app_with_error_route(httpx.TimeoutException("timed out"))),
        raise_app_exceptions=False,
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/boom")

    assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT
    assert response.json()["error"]["code"] == "HTTP_CLIENT_TIMEOUT"


def test_mask_sensitive_scrubs_extra_and_message() -> None:
    record: dict[str, Any] = {
        "extra": {
            "password": "secret",
            "headers": {"Authorization": "Bearer token"},
            "safe": "value",
        },
        "message": (
            "password=secret api_key=abc Authorization: Bearer token "
            "password=\"super secret value\" api_key='another secret value'"
        ),
    }

    mask_sensitive(record)

    assert record["extra"]["password"] == "***"
    assert record["extra"]["headers"]["Authorization"] == "***"
    assert record["extra"]["safe"] == "value"
    assert "secret" not in record["message"]
    assert "super" not in record["message"]
    assert "another" not in record["message"]
    assert "abc" not in record["message"]
    assert "token" not in record["message"]


def test_sanitize_log_message_redacts_escaped_quoted_sensitive_values() -> None:
    message = sanitize_log_message(
        'password="abc\\" super secret value" '
        '{"password":"abc\\" json secret value"} '
        "api_key='xyz\\' another secret value'"
    )

    assert "abc" not in message
    assert "xyz" not in message
    assert "super" not in message
    assert "another" not in message
    assert "secret value" not in message
    assert 'password="***"' in message
    assert '"password":"***"' in message
    assert "api_key='***'" in message


def test_sanitize_log_message_redacts_unterminated_quoted_sensitive_values() -> None:
    message = sanitize_log_message(
        'password="unterminated super secret value\n'
        '{"password":"abc\\" json secret value\n'
        "api_key='unterminated another secret value"
    )

    assert "unterminated" not in message
    assert "abc" not in message
    assert "super" not in message
    assert "another" not in message
    assert "secret value" not in message
    assert 'password="***' in message
    assert '"password":"***' in message
    assert "api_key='***" in message


def test_sanitize_log_message_redacts_mysql_near_snippets() -> None:
    nested_quote_message = sanitize_log_message(
        "You have an error in your SQL syntax near 'name = 'super-secret'' at line 1"
    )
    backtick_message = sanitize_log_message(
        "You have an error in your SQL syntax near `secret@example.com` at line 1"
    )

    assert "super-secret" not in nested_quote_message
    assert "secret@example.com" not in backtick_message
    assert "near '***'" in nested_quote_message
    assert "near `***`" in backtick_message


@pytest.mark.asyncio
async def test_mysql_query_error_detail_omits_dbapi_text() -> None:
    error = pymysql.err.ProgrammingError(
        1064,
        "You have an error in your SQL syntax near `secret@example.com` at line 1",
    )
    transport = httpx.ASGITransport(
        app=cast(Any, _app_with_error_route(error)),
        raise_app_exceptions=False,
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/boom")

    payload = response.json()
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["error"]["code"] == "MYSQL_QUERY_ERROR"
    detail = payload["error"]["detail"]
    assert detail == {
        "error_class": "ProgrammingError",
        "database_error_class": "ProgrammingError",
        "dbapi_error_code": 1064,
    }
    assert "secret@example.com" not in str(detail)
    assert "near" not in str(detail).lower()


def test_intercept_handler_omits_database_exception_traceback() -> None:
    messages: list[str] = []
    sink_id = logger.add(
        lambda message: messages.append(str(message)),
        format="{message}\n{exception}",
        level="WARNING",
    )
    std_logger = logging.getLogger("agentlens-test-intercept")
    original_handlers = list(std_logger.handlers)
    original_propagate = std_logger.propagate
    std_logger.handlers = [InterceptHandler()]
    std_logger.propagate = False
    try:
        try:
            raise OperationalError(
                "SELECT 'super-secret'",
                {"password": "super-secret"},
                Exception(3024, "query timeout"),
            )
        except OperationalError:
            std_logger.exception("standard database failure")
    finally:
        std_logger.handlers = original_handlers
        std_logger.propagate = original_propagate
        logger.remove(sink_id)

    logs = "\n".join(messages)
    assert "standard database failure" in logs
    assert "SELECT" not in logs
    assert "super-secret" not in logs
    assert "parameters" not in logs.lower()


def test_intercept_handler_omits_non_database_exception_traceback() -> None:
    messages: list[str] = []
    sink_id = logger.add(
        lambda message: messages.append(str(message)),
        format="{message}\n{exception}",
        level="WARNING",
    )
    std_logger = logging.getLogger("agentlens-test-intercept-non-db")
    original_handlers = list(std_logger.handlers)
    original_propagate = std_logger.propagate
    std_logger.handlers = [InterceptHandler()]
    std_logger.propagate = False
    try:
        try:
            raise RuntimeError("password=super-secret")
        except RuntimeError:
            std_logger.exception("standard failure")
    finally:
        std_logger.handlers = original_handlers
        std_logger.propagate = original_propagate
        logger.remove(sink_id)

    logs = "\n".join(messages)
    assert "standard failure" in logs
    assert "password=***" in logs
    assert "super-secret" not in logs
    assert "Traceback" not in logs


def test_validation_error_log_summary_omits_raw_input() -> None:
    error = RequestValidationError(
        [
            {
                "type": "string_type",
                "loc": ("body", "password"),
                "msg": "Input should be a valid string",
                "input": "super-secret",
            }
        ]
    )

    summary = _validation_error_log_summary(error)

    assert summary == [
        {
            "loc": ["body", "password"],
            "type": "string_type",
            "msg": "Input should be a valid string",
        }
    ]
    assert "input" not in summary[0]
    assert "super-secret" not in repr(summary)
