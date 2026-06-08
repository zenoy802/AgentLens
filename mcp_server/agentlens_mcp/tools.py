from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, Literal, ParamSpec, TypeVar, cast

from agentlens_client.async_client import AgentLensAsyncClient
from agentlens_client.context_export import export_context as export_context_helper
from agentlens_client.errors import AgentLensClientError
from agentlens_client.sync_client import AgentLensSyncClient
from agentlens_client.types import ContextScope, OutputTarget

from agentlens_mcp.errors import McpError, backend_error, internal_error, invalid_params
from agentlens_mcp.guide import AGENT_GUIDE

AnnotationColor = Literal["red", "yellow", "green", "blue", "gray"]
AnnotationSeverity = Literal["info", "warning", "error"]

ALLOWED_COLORS = ("red", "yellow", "green", "blue", "gray")
ALLOWED_SEVERITIES = ("info", "warning", "error")
ALLOWED_SCOPES = ("selection", "all")
ALLOWED_TARGETS = ("generic", "claude-code")
MAX_ROWS_LIMIT = 500
DEFAULT_ROWS_LIMIT = 100
MAX_HIGHLIGHT_ROWS = 200
MAX_ANNOTATION_TEXT_LENGTH = 2000
MAX_TRAJECTORIES_RETURNED = 25
MAX_MESSAGES_PER_TRAJECTORY = 200

P = ParamSpec("P")
R = TypeVar("R")


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]


def tool_errors(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await func(*args, **kwargs)
        except McpError:
            raise
        except AgentLensClientError as exc:
            raise backend_error(exc) from exc
        except Exception as exc:
            raise internal_error(f"AgentLens MCP tool failed: {exc}") from exc

    return wrapper


class AgentLensMcpTools:
    def __init__(
        self,
        *,
        client: AgentLensAsyncClient,
        backend_url: str,
        author: str,
        timeout: int,
        sync_client_factory: Callable[[str, int], AgentLensSyncClient] = AgentLensSyncClient,
    ) -> None:
        self.client = client
        self.backend_url = backend_url
        self.author = author
        self.timeout = timeout
        self._sync_client_factory = sync_client_factory

    async def close(self) -> None:
        await self.client.close()

    @tool_errors
    async def get_agent_guide(self) -> str:
        return AGENT_GUIDE

    @tool_errors
    async def get_backend_info(self) -> dict[str, Any]:
        info = await self.client.schema_info()
        backend_version = (
            info.get("backend_version", "unknown") if isinstance(info, dict) else "unknown"
        )
        return {
            "backend_url": self.backend_url,
            "backend_version": backend_version,
            "author": self.author,
            "available_colors": list(ALLOWED_COLORS),
            "limits": {
                "get_rows_default_limit": DEFAULT_ROWS_LIMIT,
                "get_rows_max_limit": MAX_ROWS_LIMIT,
                "highlight_rows_max_items": MAX_HIGHLIGHT_ROWS,
                "annotation_text_max_length": MAX_ANNOTATION_TEXT_LENGTH,
                "trajectory_summary_max_items": MAX_TRAJECTORIES_RETURNED,
                "trajectory_messages_max_items": MAX_MESSAGES_PER_TRAJECTORY,
            },
            "backend": info,
        }

    @tool_errors
    async def list_queries(self) -> list[dict[str, Any]]:
        payload = await self.client.list_queries()
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            return [item for item in payload["items"] if isinstance(item, dict)]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    @tool_errors
    async def get_query(self, query_id: int) -> dict[str, Any]:
        query = await self.client.show_query(query_id)
        payload = dict(query) if isinstance(query, dict) else {"query_id": query_id, "query": query}
        payload["view_config"] = await self._optional_backend_call(
            self.client.get(f"/queries/{query_id}/view-config")
        )
        payload["label_schema"] = await self._optional_backend_call(
            self.client.get_label_schema(query_id)
        )
        payload["column_metadata"] = await self._optional_backend_call(
            self.client.get_column_schema(query_id)
        )
        return payload

    @tool_errors
    async def get_rows(
        self,
        query_id: int,
        limit: int = DEFAULT_ROWS_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        _validate_limit_offset(limit, offset)
        rows = await self.client.get_rows(query_id, limit=limit, offset=offset)
        return cast(dict[str, Any], rows if isinstance(rows, dict) else {"rows": rows})

    @tool_errors
    async def get_trajectories(
        self,
        query_id: int,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        payload = await self.client.get_trajectories(query_id, session_id=session_id)
        if not isinstance(payload, dict):
            return {"query_id": query_id, "trajectories": payload}
        return _compact_trajectories(query_id, payload, session_id=session_id)

    @tool_errors
    async def get_labels(self, query_id: int) -> list[dict[str, Any]]:
        payload = await self.client.get_labels(query_id)
        return _labels_to_records(payload)

    @tool_errors
    async def get_annotations(
        self,
        query_id: int,
        author: str | None = None,
        author_prefix: str | None = None,
        color: str | None = None,
        annotation_set: str | None = None,
    ) -> list[dict[str, Any]]:
        if color is not None:
            _validate_color(color)
        payload = await self.client.get_annotations(
            query_id,
            author=author,
            author_prefix=author_prefix,
            color=color,
            annotation_set=annotation_set,
        )
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    @tool_errors
    async def list_annotations(
        self,
        query_id: int,
        author: str | None = None,
        author_prefix: str | None = None,
        color: str | None = None,
        annotation_set: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self.get_annotations(
            query_id=query_id,
            author=author,
            author_prefix=author_prefix,
            color=color,
            annotation_set=annotation_set,
        )

    @tool_errors
    async def get_selection(self, selection_id: str) -> dict[str, Any]:
        payload = await self.client.get_selection(selection_id)
        fallback = {"selection": payload}
        return cast(dict[str, Any], payload if isinstance(payload, dict) else fallback)

    @tool_errors
    async def export_context(
        self,
        query_id: int,
        selection_id: str | None = None,
        scope: str | None = None,
        target: str = "generic",
    ) -> dict[str, Any]:
        if scope is not None and scope not in ALLOWED_SCOPES:
            raise invalid_params("scope must be one of: selection, all.")
        if target not in ALLOWED_TARGETS:
            raise invalid_params("target must be one of: generic, claude-code.")
        if scope == "selection" and selection_id is None:
            raise invalid_params(
                "selection_id is required when scope=selection. Pass selection_id or use scope=all."
            )

        result = await asyncio.to_thread(
            self._export_context_sync,
            query_id,
            selection_id,
            cast(ContextScope | None, scope),
            cast(OutputTarget, target),
        )
        return _absolute_context_result(result)

    @tool_errors
    async def add_annotation(
        self,
        query_id: int,
        row_identity: str,
        color: str,
        text: str | None = None,
        column_key: str | None = None,
        title: str | None = None,
        severity: str | None = None,
        annotation_set: str | None = None,
        sql_fingerprint: str | None = None,
        schema_fingerprint: str | None = None,
        result_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        _validate_annotation_inputs(color=color, text=text, severity=severity)
        payload = _clean_payload(
            {
                "row_identity": row_identity,
                "column_key": column_key,
                "author": self.author,
                "color": color,
                "title": title,
                "text": text,
                "severity": severity,
                "annotation_set": annotation_set,
                "sql_fingerprint": sql_fingerprint,
                "schema_fingerprint": schema_fingerprint,
                "result_fingerprint": result_fingerprint,
            }
        )
        response = await self.client.create_annotation(query_id, payload)
        fallback = {"annotation": response}
        return cast(dict[str, Any], response if isinstance(response, dict) else fallback)

    @tool_errors
    async def highlight_rows(
        self,
        query_id: int,
        row_identities: list[str],
        color: str,
        note: str | None = None,
        title: str | None = None,
        severity: str | None = None,
        annotation_set: str | None = None,
    ) -> dict[str, Any]:
        _validate_annotation_inputs(color=color, text=note, severity=severity)
        if not row_identities:
            raise invalid_params("row_identities must include at least one row identity.")
        if len(row_identities) > MAX_HIGHLIGHT_ROWS:
            raise invalid_params(
                "row_identities is limited to 200 items. Use export_context for large result sets."
            )
        annotations = [
            _clean_payload(
                {
                    "row_identity": row_identity,
                    "author": self.author,
                    "color": color,
                    "title": title,
                    "text": note,
                    "severity": severity,
                    "annotation_set": annotation_set,
                }
            )
            for row_identity in row_identities
        ]
        response = await self.client.create_annotations_batch(query_id, annotations)
        annotations_out = response if isinstance(response, list) else []
        return {
            "query_id": query_id,
            "created_count": len(annotations_out),
            "annotations": annotations_out,
        }

    @tool_errors
    async def clear_annotations(
        self,
        query_id: int,
        author: str | None = None,
        author_prefix: str | None = None,
        color: str | None = None,
        annotation_set: str | None = None,
    ) -> dict[str, Any]:
        if color is not None:
            _validate_color(color)
        filters = {
            "author": author,
            "author_prefix": author_prefix,
            "color": color,
            "annotation_set": annotation_set,
        }
        if all(value is None for value in filters.values()):
            raise invalid_params(
                "Refusing to clear annotations without filters. Provide author, "
                "author_prefix, color, or annotation_set."
            )
        response = await self.client.clear_annotations(query_id, **filters)
        fallback = {"result": response}
        return cast(dict[str, Any], response if isinstance(response, dict) else fallback)

    async def _optional_backend_call(self, awaitable: Awaitable[Any]) -> Any:
        try:
            return await awaitable
        except AgentLensClientError as exc:
            return {
                "available": False,
                "error": {
                    "message": exc.message,
                    "code": exc.code,
                    "status_code": exc.status_code,
                },
            }

    def _export_context_sync(
        self,
        query_id: int,
        selection_id: str | None,
        scope: ContextScope | None,
        target: OutputTarget,
    ) -> dict[str, Any]:
        with self._sync_client_factory(self.backend_url, self.timeout) as sync_client:
            return cast(
                dict[str, Any],
                export_context_helper(
                    client=sync_client,
                    query_id=query_id,
                    selection_id=selection_id,
                    scope=scope,
                    target=target,
                    backend_url=self.backend_url,
                ),
            )


def get_tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="get_agent_guide",
            description=(
                "Get the AgentLens agent integration guide. Call this once at the start of a "
                "session if you are new to AgentLens. It explains workflow, live access vs "
                "context export, annotation color conventions, and write-back rules."
            ),
            input_schema=_schema(),
        ),
        ToolDefinition(
            name="get_backend_info",
            description=(
                "Get AgentLens backend version, available annotation colors, MCP limits, and "
                "the current fixed author used for write-back tools."
            ),
            input_schema=_schema(),
        ),
        ToolDefinition(
            name="list_queries",
            description=(
                "List saved and temporary queries available in AgentLens. Use this to discover "
                "query_id values that can be analyzed."
            ),
            input_schema=_schema(),
        ),
        ToolDefinition(
            name="get_query",
            description=(
                "Get full query metadata including SQL, name, view config, label schema, and "
                "best-effort column metadata when available."
            ),
            input_schema=_schema({"query_id": _integer("Query id.")}, required=["query_id"]),
        ),
        ToolDefinition(
            name="get_rows",
            description=(
                "Get rows of a query result using live backend access. Use limit and offset for "
                "pagination. For large analysis, do not repeatedly fetch thousands of rows "
                "through MCP; use export_context instead."
            ),
            input_schema=_schema(
                {
                    "query_id": _integer("Query id."),
                    "limit": _integer(
                        "Rows to return. Defaults to 100 and must be <= 500.",
                        minimum=1,
                        maximum=MAX_ROWS_LIMIT,
                    ),
                    "offset": _integer("Zero-based row offset. Defaults to 0.", minimum=0),
                },
                required=["query_id"],
            ),
        ),
        ToolDefinition(
            name="get_trajectories",
            description=(
                "Get query rows grouped as trajectories. Use this when the result represents "
                "LLM conversation messages. Without session_id this returns bounded summaries; "
                "for full large analysis use export_context."
            ),
            input_schema=_schema(
                {
                    "query_id": _integer("Query id."),
                    "session_id": {
                        "type": "string",
                        "description": "Optional trajectory group_key/session id to fetch.",
                    },
                },
                required=["query_id"],
            ),
        ),
        ToolDefinition(
            name="get_labels",
            description=(
                "Get human-defined labels for a query. Labels are read-only for agents in v1."
            ),
            input_schema=_schema({"query_id": _integer("Query id.")}, required=["query_id"]),
        ),
        ToolDefinition(
            name="get_annotations",
            description=(
                "List existing visual annotations for a query. Use this to avoid duplicating "
                "your own findings or inspect other agents' notes."
            ),
            input_schema=_annotation_filter_schema(),
        ),
        ToolDefinition(
            name="list_annotations",
            description="Alias for get_annotations with the same filters.",
            input_schema=_annotation_filter_schema(),
        ),
        ToolDefinition(
            name="get_selection",
            description=(
                "Get a temporary selection snapshot created from AgentLens UI. Use this when "
                "the prompt includes a selection_id from Copy Agent Prompt."
            ),
            input_schema=_schema(
                {
                    "selection_id": {
                        "type": "string",
                        "description": "Temporary selection snapshot id.",
                    }
                },
                required=["selection_id"],
            ),
        ),
        ToolDefinition(
            name="export_context",
            description=(
                "Export AgentLens query data into local context files and return file paths. "
                "Use this for large analysis, local file processing, or when MCP responses "
                "would be too large."
            ),
            input_schema=_schema(
                {
                    "query_id": _integer("Query id."),
                    "selection_id": {
                        "type": "string",
                        "description": "Optional selection snapshot id.",
                    },
                    "scope": {
                        "type": "string",
                        "enum": list(ALLOWED_SCOPES),
                        "description": (
                            "Optional export scope. Defaults to selection when selection_id is "
                            "provided, otherwise all query rows."
                        ),
                    },
                    "target": {
                        "type": "string",
                        "enum": list(ALLOWED_TARGETS),
                        "default": "generic",
                        "description": "Context target format.",
                    },
                },
                required=["query_id"],
            ),
        ),
        ToolDefinition(
            name="add_annotation",
            description=(
                "Add a visual annotation to a row or cell in AgentLens UI. Row-level "
                "annotations omit column_key; cell-level annotations specify column_key. "
                "The author is fixed by server startup arguments."
            ),
            input_schema=_add_annotation_schema(),
        ),
        ToolDefinition(
            name="highlight_rows",
            description=(
                "Batch highlight multiple rows with the same finding. Use this when several "
                "rows share the same failure mode or pattern; it uses the batch endpoint."
            ),
            input_schema=_highlight_rows_schema(),
        ),
        ToolDefinition(
            name="clear_annotations",
            description=(
                "Clear annotations matching filters. At least one filter is required. Common "
                "usage is author=<current_author> or author_prefix='agent:' for agent notes."
            ),
            input_schema=_annotation_filter_schema(),
        ),
    ]


def _schema(
    properties: dict[str, Any] | None = None,
    *,
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": False,
    }


def _integer(
    description: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "integer", "description": description}
    if minimum is not None:
        schema["minimum"] = minimum
    if maximum is not None:
        schema["maximum"] = maximum
    return schema


def _annotation_filter_schema() -> dict[str, Any]:
    return _schema(
        {
            "query_id": _integer("Query id."),
            "author": {"type": "string", "description": "Exact annotation author filter."},
            "author_prefix": {
                "type": "string",
                "description": "Author prefix filter, for example agent:.",
            },
            "color": {
                "type": "string",
                "enum": list(ALLOWED_COLORS),
                "description": "Annotation color filter.",
            },
            "annotation_set": {
                "type": "string",
                "description": "Optional annotation set filter.",
            },
        },
        required=["query_id"],
    )


def _add_annotation_schema() -> dict[str, Any]:
    return _schema(
        {
            "query_id": _integer("Query id."),
            "row_identity": {
                "type": "string",
                "description": "Row identity from get_rows, get_selection, or export_context.",
            },
            "color": {"type": "string", "enum": list(ALLOWED_COLORS)},
            "text": {
                "type": "string",
                "description": "Optional annotation text, max 2000 characters.",
            },
            "column_key": {"type": "string", "description": "Optional column key for cell notes."},
            "title": {"type": "string", "description": "Optional short title."},
            "severity": {"type": "string", "enum": list(ALLOWED_SEVERITIES)},
            "annotation_set": {"type": "string"},
            "sql_fingerprint": {"type": "string"},
            "schema_fingerprint": {"type": "string"},
            "result_fingerprint": {"type": "string"},
        },
        required=["query_id", "row_identity", "color"],
    )


def _highlight_rows_schema() -> dict[str, Any]:
    return _schema(
        {
            "query_id": _integer("Query id."),
            "row_identities": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": MAX_HIGHLIGHT_ROWS,
                "description": "Row identities to highlight, max 200.",
            },
            "color": {"type": "string", "enum": list(ALLOWED_COLORS)},
            "note": {
                "type": "string",
                "description": "Optional shared note, max 2000 characters.",
            },
            "title": {"type": "string"},
            "severity": {"type": "string", "enum": list(ALLOWED_SEVERITIES)},
            "annotation_set": {"type": "string"},
        },
        required=["query_id", "row_identities", "color"],
    )


def _validate_limit_offset(limit: int, offset: int) -> None:
    if limit < 1:
        raise invalid_params("limit must be at least 1.")
    if limit > MAX_ROWS_LIMIT:
        raise invalid_params("limit must be <= 500. Use export_context for large result sets.")
    if offset < 0:
        raise invalid_params("offset must be >= 0.")


def _validate_color(color: str) -> None:
    if color not in ALLOWED_COLORS:
        raise invalid_params("color must be one of: red, yellow, green, blue, gray.")


def _validate_annotation_inputs(
    *,
    color: str,
    text: str | None,
    severity: str | None,
) -> None:
    _validate_color(color)
    if text is not None and len(text) > MAX_ANNOTATION_TEXT_LENGTH:
        raise invalid_params("annotation text must be <= 2000 characters.")
    if severity is not None and severity not in ALLOWED_SEVERITIES:
        raise invalid_params("severity must be one of: info, warning, error.")


def _clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _labels_to_records(payload: Any) -> list[dict[str, Any]]:
    labels_by_row = payload.get("labels_by_row", {}) if isinstance(payload, dict) else {}
    if not isinstance(labels_by_row, dict):
        return []
    return [
        {"row_identity": str(row_identity), "labels": labels}
        for row_identity, labels in labels_by_row.items()
    ]


def _compact_trajectories(
    query_id: int,
    payload: dict[str, Any],
    *,
    session_id: str | None,
) -> dict[str, Any]:
    raw_trajectories = payload.get("trajectories")
    if not isinstance(raw_trajectories, list):
        return payload

    trajectories = [item for item in raw_trajectories if isinstance(item, dict)]
    if session_id is None:
        summaries = [
            {
                "group_key": item.get("group_key"),
                "message_count": item.get("message_count"),
            }
            for item in trajectories[:MAX_TRAJECTORIES_RETURNED]
        ]
        return {
            **{key: value for key, value in payload.items() if key != "trajectories"},
            "query_id": payload.get("query_id", query_id),
            "trajectory_count": len(trajectories),
            "trajectories": summaries,
            "truncated_by_mcp": len(trajectories) > MAX_TRAJECTORIES_RETURNED,
            "guidance": (
                "Pass session_id for one trajectory or use export_context for large analysis."
            ),
        }

    compacted = []
    truncated = False
    for item in trajectories:
        messages = item.get("messages")
        if isinstance(messages, list) and len(messages) > MAX_MESSAGES_PER_TRAJECTORY:
            compacted_item = {
                **item,
                "messages": messages[:MAX_MESSAGES_PER_TRAJECTORY],
                "truncated_by_mcp": True,
            }
            truncated = True
        else:
            compacted_item = item
        compacted.append(compacted_item)
    return {
        **payload,
        "query_id": payload.get("query_id", query_id),
        "trajectories": compacted,
        "truncated_by_mcp": truncated,
        "guidance": (
            "This session was truncated by MCP; use export_context for the complete trajectory."
            if truncated
            else "Use export_context for larger trajectory analysis."
        ),
    }


def _absolute_context_result(result: dict[str, Any]) -> dict[str, Any]:
    output_dir = Path(str(result["output_dir"])).expanduser().resolve()
    files: dict[str, str] = {}
    raw_files = result.get("files", {})
    if isinstance(raw_files, dict):
        for key, value in raw_files.items():
            mapped_key = "agentlens_context" if key == "context" else str(key)
            path = Path(str(value))
            files[mapped_key] = str(path if path.is_absolute() else output_dir / path)
    if "manifest" not in files and result.get("manifest_path") is not None:
        files["manifest"] = str(Path(str(result["manifest_path"])).expanduser().resolve())
    return {
        "context_id": result["context_id"],
        "query_id": result["query_id"],
        "selection_id": result.get("selection_id"),
        "scope": result["scope"],
        "path": str(output_dir),
        "files": files,
    }


TOOL_DEFINITIONS = get_tool_definitions()

__all__ = [
    "ALLOWED_COLORS",
    "MAX_ANNOTATION_TEXT_LENGTH",
    "MAX_HIGHLIGHT_ROWS",
    "MAX_ROWS_LIMIT",
    "TOOL_DEFINITIONS",
    "AgentLensMcpTools",
    "ToolDefinition",
    "get_tool_definitions",
]
