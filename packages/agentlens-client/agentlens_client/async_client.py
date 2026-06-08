from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from agentlens_client.config import DEFAULT_TIMEOUT
from agentlens_client.errors import (
    BackendBusinessError,
    decode_response,
    raise_unavailable,
    request_url,
)

_SENSITIVE_KEYS = {"password", "api_key", "token", "secret"}
_MAX_ROWS_REQUEST = 100000
_LABEL_QUERY_CHUNK_SIZE = 1000
_PRIMARY_ROW_IDENTITY_KEY = "_row_identity"
_FALLBACK_ROW_IDENTITY_PREFIX = "_agent_lens_row_identity"


class AgentLensAsyncClient:
    def __init__(self, base_url: str, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AgentLensAsyncClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=_clean_params(params))

    async def post(self, path: str, json: dict[str, Any] | None = None) -> Any:
        return await self._request("POST", path, json=json)

    async def delete(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("DELETE", path, params=_clean_params(params))

    async def list_connections(self) -> Any:
        data = await self.get("/connections", params={"page_size": 100})
        return _redact_sensitive(data)

    async def show_connection(self, name: str) -> Any:
        for connection in await _list_paginated(self, "/connections"):
            if isinstance(connection, dict) and connection.get("name") == name:
                return _redact_sensitive(connection)
        raise BackendBusinessError(
            f"Connection '{name}' was not found.",
            code="NOT_FOUND",
            detail={"name": name},
            status_code=404,
            backend_url=self.base_url,
        )

    async def list_queries(self) -> Any:
        return await self.get("/queries", params={"page_size": 100})

    async def show_query(self, query_id: int) -> Any:
        return await self.get(f"/queries/{query_id}")

    async def exec_query(self, connection: str, sql: str, row_limit: int | None = None) -> Any:
        connection_info = await self.show_connection(connection)
        connection_id = _require_int(connection_info, "id")
        payload: dict[str, Any] = {
            "connection_id": connection_id,
            "sql": sql,
            "save_as_temporary": True,
        }
        if row_limit is not None:
            payload["row_limit"] = row_limit
        return await self.post("/execute", json=payload)

    async def rerun_query(self, query_id: int) -> Any:
        return await self.post(f"/queries/{query_id}/execute", json={})

    async def get_rows(self, query_id: int, limit: int = 100, offset: int = 0) -> Any:
        requested_limit = max(min(limit + offset, _MAX_ROWS_REQUEST), 1)
        result = await self.post(
            f"/queries/{query_id}/execute",
            json={"row_limit": requested_limit},
        )
        all_rows = _as_list(result.get("rows") if isinstance(result, dict) else None)
        rows = all_rows[offset : offset + limit]
        execution = result.get("execution", {}) if isinstance(result, dict) else {}
        truncated = bool(execution.get("truncated")) if isinstance(execution, dict) else False
        total = None if truncated else len(all_rows)
        return {
            "query_id": query_id,
            "columns": result.get("columns", []) if isinstance(result, dict) else [],
            "rows": rows,
            "total": total,
            "limit": limit,
            "offset": offset,
            "returned_count": len(rows),
            "fetched_count": len(all_rows),
            "truncated": truncated,
            "fingerprints": result.get("fingerprints", {}) if isinstance(result, dict) else {},
            "suggested_field_renders": (
                result.get("suggested_field_renders", {}) if isinstance(result, dict) else {}
            ),
            "execution": execution,
            "warnings": result.get("warnings", []) if isinstance(result, dict) else [],
        }

    async def get_trajectories(self, query_id: int, session_id: str | None = None) -> Any:
        result = await self.post(f"/queries/{query_id}/trajectories", json={})
        if session_id is None or not isinstance(result, dict):
            return result
        trajectories = [
            trajectory
            for trajectory in _as_list(result.get("trajectories"))
            if isinstance(trajectory, dict) and trajectory.get("group_key") == session_id
        ]
        return {**result, "trajectories": trajectories}

    async def get_labels(self, query_id: int) -> Any:
        rows_envelope = await self.get_rows(query_id, limit=_MAX_ROWS_REQUEST, offset=0)
        rows = _as_list(rows_envelope.get("rows") if isinstance(rows_envelope, dict) else None)
        identity_key = _identity_key(rows_envelope)
        row_identities = [
            identity
            for row in rows
            if isinstance(row, dict) and (identity := _row_identity(row, identity_key)) is not None
        ]
        labels_by_row: dict[str, Any] = {}
        for chunk in _chunks(row_identities, _LABEL_QUERY_CHUNK_SIZE):
            payload = await self.post(
                f"/queries/{query_id}/labels/query",
                json={"row_identities": chunk},
            )
            if isinstance(payload, dict) and isinstance(payload.get("labels_by_row"), dict):
                labels_by_row.update(payload["labels_by_row"])
        return {"query_id": query_id, "labels_by_row": labels_by_row}

    async def get_annotations(self, query_id: int, **filters: Any) -> Any:
        return await self.get(f"/queries/{query_id}/annotations", params=_clean_params(filters))

    async def get_selection(self, selection_id: str) -> Any:
        return await self.get(f"/selections/{selection_id}")

    async def create_annotation(self, query_id: int, payload: dict[str, Any]) -> Any:
        return await self.post(f"/queries/{query_id}/annotations", json=payload)

    async def create_annotations_batch(
        self,
        query_id: int,
        annotations: list[dict[str, Any]],
    ) -> Any:
        return await self.post(
            f"/queries/{query_id}/annotations/batch",
            json={"annotations": annotations},
        )

    async def clear_annotations(self, query_id: int, **filters: Any) -> Any:
        return await self.delete(f"/queries/{query_id}/annotations", params=_clean_params(filters))

    async def create_selection_snapshot(
        self,
        query_id: int,
        row_identities: list[str],
        source: str,
    ) -> Any:
        return await self.post(
            f"/queries/{query_id}/selection-snapshots",
            json={"row_identities": row_identities, "source": source},
        )

    async def schema_info(self) -> Any:
        health = await self.get("/health")
        backend_version = (
            health.get("version", "unknown") if isinstance(health, dict) else "unknown"
        )
        return {
            "backend_version": backend_version,
            "cli_version": "unknown",
            "annotation": {
                "colors": ["red", "yellow", "green", "blue", "gray"],
                "severities": ["info", "warning", "error"],
                "max_text_length": 2000,
                "author_pattern": "^[a-zA-Z0-9_:.-]+$",
            },
            "recommended_workflow": (
                "Use `agentlens data rows` for small live reads, "
                "`agentlens context export` for large reproducible snapshots, and "
                "`agentlens annotate` or `agentlens highlight` to write annotations back."
            ),
        }

    async def get_column_schema(self, query_id: int) -> Any:
        rows = await self.get_rows(query_id, limit=1, offset=0)
        return {
            "query_id": query_id,
            "columns": rows.get("columns", []) if isinstance(rows, dict) else [],
            "suggested_field_renders": (
                rows.get("suggested_field_renders", {}) if isinstance(rows, dict) else {}
            ),
            "fingerprints": rows.get("fingerprints", {}) if isinstance(rows, dict) else {},
        }

    async def get_label_schema(self, query_id: int) -> Any:
        return await self.get(f"/queries/{query_id}/label-schema")

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(
                method,
                request_url(self.base_url, path),
                **kwargs,
            )
        except httpx.RequestError as exc:
            raise_unavailable(exc, backend_url=self.base_url)
        return decode_response(response, backend_url=self.base_url)


def _clean_params(params: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if params is None:
        return None
    cleaned = {key: value for key, value in params.items() if value is not None}
    return cleaned or None


async def _list_paginated(client: AgentLensAsyncClient, path: str) -> list[dict[str, Any]]:
    page = 1
    items: list[dict[str, Any]] = []
    while True:
        data = await client.get(path, params={"page": page, "page_size": 100})
        if not isinstance(data, dict):
            return items
        page_items = [item for item in _as_list(data.get("items")) if isinstance(item, dict)]
        items.extend(page_items)
        pagination = data.get("pagination")
        if not isinstance(pagination, dict) or page >= int(pagination.get("total_pages", page)):
            return items
        page += 1


def _require_int(data: Any, key: str) -> int:
    if isinstance(data, dict) and isinstance(data.get(key), int):
        return data[key]
    raise BackendBusinessError(
        f"Connection response did not include integer '{key}'.",
        code="INVALID_BACKEND_RESPONSE",
    )


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _identity_key(envelope: Any) -> str | None:
    if not isinstance(envelope, dict):
        return None

    warning_fallback = _identity_key_from_warnings(envelope.get("warnings"))
    if warning_fallback is not None:
        return warning_fallback

    column_names = {
        column.get("name")
        for column in _as_list(envelope.get("columns"))
        if isinstance(column, dict)
    }
    if column_names:
        return _identity_key_from_columns(column_names)

    rows = [row for row in _as_list(envelope.get("rows")) if isinstance(row, dict)]
    return _identity_key_from_row(rows[0]) if rows else None


def _identity_key_from_columns(column_names: set[Any]) -> str:
    if _PRIMARY_ROW_IDENTITY_KEY not in column_names:
        return _PRIMARY_ROW_IDENTITY_KEY

    suffix = 1
    while True:
        candidate = (
            _FALLBACK_ROW_IDENTITY_PREFIX
            if suffix == 1
            else f"{_FALLBACK_ROW_IDENTITY_PREFIX}_{suffix}"
        )
        if candidate not in column_names:
            return candidate
        suffix += 1


def _identity_key_from_row(row: dict[str, Any]) -> str | None:
    if _PRIMARY_ROW_IDENTITY_KEY in row:
        return _PRIMARY_ROW_IDENTITY_KEY
    for key in row:
        if key.startswith(_FALLBACK_ROW_IDENTITY_PREFIX):
            return key
    return None


def _identity_key_from_warnings(warnings: Any) -> str | None:
    for warning in _as_list(warnings):
        if not isinstance(warning, dict) or warning.get("code") != "ROW_IDENTITY_KEY_COLLISION":
            continue
        detail = warning.get("detail")
        if isinstance(detail, dict) and isinstance(detail.get("fallback_key"), str):
            return detail["fallback_key"]
    return None


def _row_identity(row: dict[str, Any], identity_key: str | None) -> str | None:
    if identity_key is not None:
        return str(value) if (value := row.get(identity_key)) is not None else None
    if row.get(_PRIMARY_ROW_IDENTITY_KEY) is not None:
        return str(row[_PRIMARY_ROW_IDENTITY_KEY])
    for key, value in row.items():
        if key.startswith(_FALLBACK_ROW_IDENTITY_PREFIX) and value is not None:
            return str(value)
    return None


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if any(marker in key.lower() for marker in _SENSITIVE_KEYS):
                redacted[key] = "***"
            else:
                redacted[key] = _redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


__all__ = ["AgentLensAsyncClient"]
