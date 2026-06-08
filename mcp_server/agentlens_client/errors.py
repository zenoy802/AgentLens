from __future__ import annotations

import json
from typing import Any

import httpx

from agentlens_client.config import API_PREFIX

HTTP_NO_CONTENT = 204
HTTP_BAD_REQUEST = 400
HTTP_INTERNAL_SERVER_ERROR = 500


class AgentLensClientError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        detail: Any | None = None,
        status_code: int | None = None,
        backend_url: str | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.detail = detail
        self.status_code = status_code
        self.backend_url = backend_url
        super().__init__(message)


class BackendUnavailableError(AgentLensClientError):
    pass


class BackendBusinessError(AgentLensClientError):
    pass


class BackendServerError(AgentLensClientError):
    pass


def api_path(path: str) -> str:
    normalized = f"/{path.lstrip('/')}"
    if normalized == API_PREFIX or normalized.startswith(f"{API_PREFIX}/"):
        return normalized
    return f"{API_PREFIX}{normalized}"


def request_url(base_url: str, path: str) -> str:
    normalized_base_url = base_url.rstrip("/")
    normalized_path = api_path(path)
    if normalized_base_url.endswith(API_PREFIX):
        return f"{normalized_base_url}{normalized_path.removeprefix(API_PREFIX)}"
    return f"{normalized_base_url}{normalized_path}"


def raise_unavailable(exc: httpx.RequestError, *, backend_url: str) -> None:
    raise BackendUnavailableError(
        f"Cannot connect to AgentLens backend at {backend_url}: {exc}",
        backend_url=backend_url,
    ) from exc


def decode_response(response: httpx.Response, *, backend_url: str) -> Any:
    if response.status_code == HTTP_NO_CONTENT:
        return None

    if HTTP_BAD_REQUEST <= response.status_code < HTTP_INTERNAL_SERVER_ERROR:
        message, code, detail = _error_payload(response)
        raise BackendBusinessError(
            message,
            code=code,
            detail=detail,
            status_code=response.status_code,
            backend_url=backend_url,
        )

    if response.status_code >= HTTP_INTERNAL_SERVER_ERROR:
        message, code, detail = _error_payload(response)
        raise BackendServerError(
            message,
            code=code,
            detail=detail,
            status_code=response.status_code,
            backend_url=backend_url,
        )

    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise AgentLensClientError(
            "AgentLens backend returned invalid JSON.",
            status_code=response.status_code,
            backend_url=backend_url,
        ) from exc


def _error_payload(response: httpx.Response) -> tuple[str, str | None, Any | None]:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return response.text or f"HTTP {response.status_code}", None, None

    if not isinstance(payload, dict):
        return f"HTTP {response.status_code}", None, payload

    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        code = error.get("code")
        detail = error.get("detail")
        return (
            str(message) if message is not None else f"HTTP {response.status_code}",
            str(code) if code is not None else None,
            detail,
        )

    message = payload.get("message")
    return str(message) if message is not None else f"HTTP {response.status_code}", None, payload
