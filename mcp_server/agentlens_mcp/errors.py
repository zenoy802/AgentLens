from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentlens_client.errors import (
    AgentLensClientError,
    BackendBusinessError,
    BackendServerError,
    BackendUnavailableError,
)

JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603

try:  # pragma: no cover - exercised when the mcp package is installed.
    from mcp.shared.exceptions import McpError
    from mcp.types import ErrorData
except ModuleNotFoundError:  # pragma: no cover - local tests run without mcp installed.

    @dataclass(slots=True)
    class ErrorData:  # type: ignore[no-redef]
        code: int
        message: str
        data: Any | None = None

    class McpError(Exception):  # type: ignore[no-redef]
        def __init__(self, error: ErrorData) -> None:
            self.error = error
            super().__init__(error.message)


def invalid_params(message: str, *, detail: Any | None = None) -> McpError:
    return McpError(ErrorData(code=JSONRPC_INVALID_PARAMS, message=message, data=detail))


def internal_error(message: str, *, detail: Any | None = None) -> McpError:
    return McpError(ErrorData(code=JSONRPC_INTERNAL_ERROR, message=message, data=detail))


def backend_error(exc: AgentLensClientError) -> McpError:
    if isinstance(exc, BackendUnavailableError):
        message = f"{exc.message}. Start AgentLens backend or check --backend-url."
    elif isinstance(exc, BackendBusinessError):
        message = exc.message
    elif isinstance(exc, BackendServerError):
        message = f"AgentLens backend error: {exc.message}"
    else:
        message = exc.message

    detail: dict[str, Any] = {}
    if exc.code is not None:
        detail["code"] = exc.code
    if exc.status_code is not None:
        detail["status_code"] = exc.status_code
    if exc.backend_url is not None:
        detail["backend_url"] = exc.backend_url
    if exc.detail is not None:
        detail["detail"] = exc.detail
    return internal_error(message, detail=detail or None)


__all__ = [
    "McpError",
    "backend_error",
    "internal_error",
    "invalid_params",
]
