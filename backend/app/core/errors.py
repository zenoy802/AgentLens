from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError


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


class ConflictError(AppError):
    default_code = "CONFLICT"
    default_message = "Resource conflict."
    default_http_status = status.HTTP_409_CONFLICT


class SqlForbiddenError(AppError):
    default_code = "SQL_FORBIDDEN_STATEMENT"
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


class SqlRowLimitError(AppError):
    default_code = "SQL_ROW_LIMIT_EXCEEDED"
    default_message = "SQL row limit exceeded."
    default_http_status = status.HTTP_400_BAD_REQUEST


class ConnectionTestError(AppError):
    default_code = "CONN_TEST_FAILED"
    default_message = "Connection test failed."
    default_http_status = status.HTTP_400_BAD_REQUEST


class LLMError(AppError):
    default_code = "LLM_ERROR"
    default_message = "LLM request failed."
    default_http_status = status.HTTP_500_INTERNAL_SERVER_ERROR


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] | list[Any] | str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


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
        return _build_error_response(
            code=exc.code,
            message=exc.message,
            http_status=exc.http_status,
            detail=exc.detail,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _build_error_response(
            code="VALIDATION_ERROR",
            message="Request validation failed.",
            http_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=jsonable_encoder(exc.errors()),
        )

    @app.exception_handler(PydanticValidationError)
    async def pydantic_validation_handler(
        _: Request, exc: PydanticValidationError
    ) -> JSONResponse:
        return _build_error_response(
            code="VALIDATION_ERROR",
            message="Validation failed.",
            http_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=jsonable_encoder(exc.errors()),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: {}", exc)
        return _build_error_response(
            code="INTERNAL_ERROR",
            message="Internal server error.",
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
