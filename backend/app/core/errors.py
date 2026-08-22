import re
from collections.abc import Mapping
from typing import Any

import httpx
import pymysql  # type: ignore[import-untyped]
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.config import get_settings
from app.core.logging import (
    has_database_exception_context,
    safe_exception_context,
    sanitize_traceback,
)


class AppError(Exception):
    default_code = "APP_ERROR"
    default_message = "Application error."
    default_http_status = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        http_status: int | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = code or self.default_code
        self.message = message or self.default_message
        self.http_status = http_status or self.default_http_status
        self.detail = dict(detail) if detail is not None else None
        super().__init__(self.message)


class NotFoundError(AppError):
    default_code = "NOT_FOUND"
    default_message = "Resource not found."
    default_http_status = status.HTTP_404_NOT_FOUND


class ValidationError(AppError):
    default_code = "VALIDATION_ERROR"
    default_message = "Validation failed."
    default_http_status = status.HTTP_422_UNPROCESSABLE_CONTENT


class TraceContractError(ValidationError):
    default_code = "TRACE_CONTRACT_INVALID"
    default_message = "Trace contract validation failed."


class SnapshotRowError(ValidationError):
    default_code = "SNAPSHOT_ROW_INVALID"
    default_message = "Snapshot source row validation failed."


class ConflictError(AppError):
    default_code = "CONFLICT"
    default_message = "Resource conflict."
    default_http_status = status.HTTP_409_CONFLICT


class SqlForbiddenError(AppError):
    default_code = "SQL_NOT_ALLOWED"
    default_message = "Only SELECT and WITH statements are allowed."
    default_http_status = status.HTTP_400_BAD_REQUEST


class SqlSyntaxError(AppError):
    default_code = "SQL_SYNTAX_ERROR"
    default_message = "The SQL statement is invalid."
    default_http_status = status.HTTP_400_BAD_REQUEST


class SqlTimeoutError(AppError):
    default_code = "SQL_TIMEOUT"
    default_message = "SQL execution timed out."
    default_http_status = status.HTTP_504_GATEWAY_TIMEOUT


class SqlExecutionError(AppError):
    default_code = "SQL_EXECUTION_ERROR"
    default_message = "SQL execution failed."
    default_http_status = status.HTTP_400_BAD_REQUEST


class SqlRowLimitError(AppError):
    default_code = "SQL_ROW_LIMIT_EXCEEDED"
    default_message = "SQL row limit exceeded."
    default_http_status = status.HTTP_400_BAD_REQUEST


class ConnectionTestError(AppError):
    default_code = "CONN_TEST_FAILED"
    default_message = "Connection test failed."
    default_http_status = status.HTTP_400_BAD_REQUEST


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] | list[Any] | str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


def _traceback_detail(exc: BaseException) -> dict[str, Any]:
    return {
        "traceback": sanitize_traceback(exc),
    }


def _server_error_detail(
    exc: BaseException,
    *,
    base_detail: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not get_settings().debug:
        return None

    detail: dict[str, Any] = dict(base_detail or {})
    detail.update(_traceback_detail(exc))
    return detail


def _build_error_response(
    *,
    code: str,
    message: str,
    http_status: int,
    detail: dict[str, Any] | list[Any] | str | None = None,
) -> JSONResponse:
    payload = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            detail=detail,
        )
    )
    return JSONResponse(status_code=http_status, content=payload.model_dump(mode="json"))


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        log_context = safe_exception_context(exc)
        if exc.http_status >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            logger.error(
                "Application error: code={} message={} status={} context={}",
                exc.code,
                exc.message,
                exc.http_status,
                log_context,
            )
            detail = _server_error_detail(exc, base_detail=exc.detail)
        else:
            detail = exc.detail
            logger.warning(
                "Application error: code={} message={} status={} context={}",
                exc.code,
                exc.message,
                exc.http_status,
                log_context,
            )
        return _build_error_response(
            code=exc.code,
            message=exc.message,
            http_status=exc.http_status,
            detail=detail,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.warning(
            "Request validation failed: path={} errors={}",
            request.url.path,
            _validation_error_log_summary(exc),
        )
        special_error = _request_validation_error_response(request.url.path, exc)
        if special_error is not None:
            return special_error
        return _build_error_response(
            code="VALIDATION_ERROR",
            message="Request validation failed.",
            http_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=jsonable_encoder(exc.errors()),
        )

    @app.exception_handler(PydanticValidationError)
    async def pydantic_validation_handler(_: Request, exc: PydanticValidationError) -> JSONResponse:
        logger.warning("Pydantic validation failed: errors={}", _validation_error_log_summary(exc))
        return _build_error_response(
            code="VALIDATION_ERROR",
            message="Validation failed.",
            http_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=jsonable_encoder(exc.errors()),
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
        constraint = _extract_constraint_name(exc)
        logger.warning(
            "Database integrity error: constraint={} context={}",
            constraint,
            safe_exception_context(exc),
        )
        return _build_error_response(
            code="DB_INTEGRITY_ERROR",
            message="Database integrity constraint failed.",
            http_status=status.HTTP_400_BAD_REQUEST,
            detail={"constraint": constraint},
        )

    @app.exception_handler(OperationalError)
    async def sqlalchemy_operational_error_handler(
        _: Request,
        exc: OperationalError,
    ) -> JSONResponse:
        logger.error("Database operational error: context={}", safe_exception_context(exc))
        return _build_error_response(
            code="DB_OPERATIONAL_ERROR",
            message="Database operation failed.",
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_server_error_detail(exc),
        )

    @app.exception_handler(pymysql.err.OperationalError)
    async def pymysql_operational_error_handler(
        _: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.error("MySQL operational error: context={}", safe_exception_context(exc))
        return _build_error_response(
            code="MYSQL_OPERATIONAL_ERROR",
            message="MySQL operation failed. Check database connection, permissions, or network.",
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_server_error_detail(exc),
        )

    @app.exception_handler(httpx.TimeoutException)
    async def http_client_timeout_handler(_: Request, exc: httpx.TimeoutException) -> JSONResponse:
        logger.warning("HTTP client request timed out: context={}", safe_exception_context(exc))
        return _build_error_response(
            code="HTTP_CLIENT_TIMEOUT",
            message="HTTP client request timed out.",
            http_status=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=_server_error_detail(exc),
        )

    @app.exception_handler(httpx.ConnectError)
    async def http_client_connect_error_handler(
        _: Request,
        exc: httpx.ConnectError,
    ) -> JSONResponse:
        logger.warning("HTTP client connection failed: context={}", safe_exception_context(exc))
        return _build_error_response(
            code="HTTP_CLIENT_CONNECT_ERROR",
            message="HTTP client connection failed.",
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_server_error_detail(exc),
        )

    @app.exception_handler(pymysql.err.ProgrammingError)
    async def pymysql_programming_error_handler(
        _: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.warning("MySQL query error: context={}", safe_exception_context(exc))
        return _build_error_response(
            code="MYSQL_QUERY_ERROR",
            message="MySQL query failed.",
            http_status=status.HTTP_400_BAD_REQUEST,
            detail=safe_exception_context(exc),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        if has_database_exception_context(exc):
            _log_unhandled_exception("Unhandled database exception", exc)
        else:
            _log_unhandled_exception("Unhandled exception", exc)
        return _build_error_response(
            code="INTERNAL_ERROR",
            message="Internal server error.",
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_server_error_detail(exc),
        )


def _log_unhandled_exception(message: str, exc: Exception) -> None:
    context = safe_exception_context(exc)
    if get_settings().debug:
        logger.error(
            "{}: context={} traceback={}",
            message,
            context,
            sanitize_traceback(exc),
        )
        return
    logger.error("{}: context={}", message, context)


def _extract_constraint_name(exc: IntegrityError) -> str | None:
    orig = getattr(exc, "orig", None)
    message = str(orig or exc)
    patterns = (
        r"constraint failed:\s*([^\n]+)",
        r"for key ['\"]([^'\"]+)['\"]",
        r"constraint ['\"]([^'\"]+)['\"]",
        r"UNIQUE constraint failed:\s*([^\n]+)",
        r"FOREIGN KEY constraint failed",
    )
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match is None:
            continue
        if match.lastindex:
            return match.group(1).strip()
        return match.group(0).strip()
    return None


def _validation_error_log_summary(
    exc: RequestValidationError | PydanticValidationError,
) -> list[dict[str, object]]:
    summary: list[dict[str, object]] = []
    for error in exc.errors():
        loc = error.get("loc", ())
        loc_items = loc if isinstance(loc, tuple | list) else (loc,)
        summary.append(
            {
                "loc": [str(item) for item in loc_items],
                "type": str(error.get("type", "")),
                "msg": str(error.get("msg", "")),
            }
        )
    return summary


def _request_validation_error_response(
    path: str,
    exc: RequestValidationError,
) -> JSONResponse | None:
    errors = exc.errors()
    for error in errors:
        loc = tuple(str(item) for item in error.get("loc", ()))
        error_type = str(error.get("type", ""))
        if "/annotations" in path and "color" in loc:
            return _build_error_response(
                code="ANNOTATION_INVALID_COLOR",
                message="Annotation color is invalid.",
                http_status=status.HTTP_400_BAD_REQUEST,
                detail=jsonable_encoder(errors),
            )
        if "/annotations" in path and "author" in loc:
            return _build_error_response(
                code="ANNOTATION_INVALID_AUTHOR",
                message="Annotation author is invalid.",
                http_status=status.HTTP_400_BAD_REQUEST,
                detail=jsonable_encoder(errors),
            )
        if "/annotations/batch" in path and "annotations" in loc and error_type == "too_long":
            return _build_error_response(
                code="ANNOTATION_BATCH_TOO_LARGE",
                message="Annotation batch is too large.",
                http_status=status.HTTP_400_BAD_REQUEST,
                detail=jsonable_encoder(errors),
            )
        if "/selection-snapshots" in path:
            if "row_identities" in loc and error_type == "too_short":
                logger.warning("Selection snapshot rejected: code=SELECTION_EMPTY")
                return _build_error_response(
                    code="SELECTION_EMPTY",
                    message="Selection row_identities must not be empty.",
                    http_status=status.HTTP_400_BAD_REQUEST,
                    detail=jsonable_encoder(errors),
                )
            if "row_identities" in loc and error_type == "too_long":
                logger.warning("Selection snapshot rejected: code=SELECTION_TOO_LARGE")
                return _build_error_response(
                    code="SELECTION_TOO_LARGE",
                    message="Selection row_identities exceeds the limit.",
                    http_status=status.HTTP_400_BAD_REQUEST,
                    detail=jsonable_encoder(errors),
                )
    return None
