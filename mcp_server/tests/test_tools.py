from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from agentlens_client.errors import BackendUnavailableError

from agentlens_mcp.errors import McpError
from agentlens_mcp.tools import TOOL_DEFINITIONS, AgentLensMcpTools

pytestmark = pytest.mark.asyncio

EXPECTED_TRAJECTORY_COUNT = 2
EXPECTED_BATCH_COUNT = 2


class FakeAsyncClient:
    def __init__(self) -> None:
        self.created_annotations: list[dict[str, Any]] = []
        self.batch_annotations: list[list[dict[str, Any]]] = []
        self.clear_filters: list[dict[str, Any]] = []
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def schema_info(self) -> dict[str, Any]:
        return {"backend_version": "0.1.0", "status": "ok"}

    async def list_queries(self) -> dict[str, Any]:
        return {"items": [{"id": 1, "name": "q"}], "pagination": {"total": 1}}

    async def show_query(self, query_id: int) -> dict[str, Any]:
        return {"id": query_id, "name": "q", "sql_text": "SELECT 1"}

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert params is None
        if path == "/queries/1/view-config":
            return {"query_id": 1, "field_renders": {}}
        raise AssertionError(path)

    async def get_label_schema(self, query_id: int) -> dict[str, Any]:
        return {"query_id": query_id, "fields": []}

    async def get_column_schema(self, query_id: int) -> dict[str, Any]:
        return {"query_id": query_id, "columns": [{"name": "value"}]}

    async def get_rows(self, query_id: int, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        rows = [
            {"_row_identity": "a", "value": 1},
            {"_row_identity": "b", "value": 2},
            {"_row_identity": "c", "value": 3},
        ]
        return {
            "query_id": query_id,
            "columns": [{"name": "value"}],
            "rows": rows[offset : offset + limit],
            "total": len(rows),
            "fingerprints": {"sql": "s", "schema": "c", "result": "r"},
        }

    async def get_trajectories(
        self,
        query_id: int,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        trajectories = [
            {
                "group_key": "s1",
                "message_count": 1,
                "messages": [{"role": "user", "content": "hi"}],
            },
            {
                "group_key": "s2",
                "message_count": 1,
                "messages": [{"role": "assistant", "content": "ok"}],
            },
        ]
        if session_id is not None:
            trajectories = [item for item in trajectories if item["group_key"] == session_id]
        return {"query_id": query_id, "trajectories": trajectories, "warnings": []}

    async def get_labels(self, query_id: int) -> dict[str, Any]:
        return {"query_id": query_id, "labels_by_row": {"a": {"quality": "bad"}}}

    async def get_annotations(self, query_id: int, **filters: Any) -> list[dict[str, Any]]:
        return [{"id": 1, "query_id": query_id, "row_identity": "a", **filters}]

    async def get_selection(self, selection_id: str) -> dict[str, Any]:
        return {
            "id": selection_id,
            "query_id": 1,
            "row_identities": ["a"],
            "count": 1,
            "source": "ui",
        }

    async def create_annotation(self, query_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        annotation = {"id": 10, "query_id": query_id, **payload}
        self.created_annotations.append(annotation)
        return annotation

    async def create_annotations_batch(
        self,
        query_id: int,
        annotations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        self.batch_annotations.append(annotations)
        return [
            {"id": index + 1, "query_id": query_id, **annotation}
            for index, annotation in enumerate(annotations)
        ]

    async def clear_annotations(self, query_id: int, **filters: Any) -> dict[str, Any]:
        self.clear_filters.append(filters)
        return {"query_id": query_id, "deleted_count": 1, "filters": filters}


class UnavailableAsyncClient(FakeAsyncClient):
    async def schema_info(self) -> dict[str, Any]:
        raise BackendUnavailableError(
            "Cannot connect to AgentLens backend at http://testserver",
            backend_url="http://testserver",
        )


class FakeSyncClient:
    def __init__(self, base_url: str, timeout: int) -> None:
        self.base_url = base_url
        self.timeout = timeout

    def __enter__(self) -> FakeSyncClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get_selection(self, selection_id: str) -> dict[str, Any]:
        return {
            "id": selection_id,
            "query_id": 1,
            "row_identities": ["a"],
            "count": 1,
            "source": "ui",
        }

    def get_rows(self, query_id: int, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        assert limit >= 1
        assert offset >= 0
        return {
            "query_id": query_id,
            "columns": [{"name": "value"}],
            "rows": [{"_row_identity": "a", "value": 1}],
            "total": 1,
            "truncated": False,
            "fingerprints": {"sql": "s", "schema": "c", "result": "r"},
            "warnings": [],
        }

    def get_labels(self, query_id: int) -> dict[str, Any]:
        return {"query_id": query_id, "labels_by_row": {"a": {"quality": "bad"}}}

    def get_annotations(self, query_id: int, **filters: Any) -> list[dict[str, Any]]:
        return [{"id": 1, "query_id": query_id, "row_identity": "a", **filters}]


def make_tools(client: FakeAsyncClient | None = None) -> AgentLensMcpTools:
    return AgentLensMcpTools(
        client=client or FakeAsyncClient(),
        backend_url="http://testserver",
        author="agent:pytest",
        timeout=30,
        sync_client_factory=FakeSyncClient,
    )


async def test_tool_definitions_cover_expected_tools() -> None:
    names = {tool.name for tool in TOOL_DEFINITIONS}

    assert names == {
        "get_agent_guide",
        "get_backend_info",
        "list_queries",
        "get_query",
        "get_rows",
        "get_trajectories",
        "get_labels",
        "get_annotations",
        "list_annotations",
        "get_selection",
        "export_context",
        "add_annotation",
        "highlight_rows",
        "clear_annotations",
    }
    assert "Use this for large analysis" in next(
        tool.description for tool in TOOL_DEFINITIONS if tool.name == "export_context"
    )


async def test_guide_and_backend_info() -> None:
    tools = make_tools()

    guide = await tools.get_agent_guide()
    info = await tools.get_backend_info()

    assert "SQL-first LLM trajectory analysis tool" in guide
    assert "red: hard failures / errors" in guide
    assert info["backend_version"] == "0.1.0"
    assert info["author"] == "agent:pytest"
    assert "red" in info["available_colors"]


async def test_query_discovery_and_metadata() -> None:
    tools = make_tools()

    queries = await tools.list_queries()
    query = await tools.get_query(1)

    assert queries == [{"id": 1, "name": "q"}]
    assert query["sql_text"] == "SELECT 1"
    assert query["view_config"]["query_id"] == 1
    assert query["label_schema"]["fields"] == []
    assert query["column_metadata"]["columns"] == [{"name": "value"}]


async def test_live_access_tools() -> None:
    tools = make_tools()

    rows = await tools.get_rows(query_id=1, limit=2)
    trajectories_summary = await tools.get_trajectories(query_id=1)
    trajectory = await tools.get_trajectories(query_id=1, session_id="s1")
    labels = await tools.get_labels(query_id=1)
    annotations = await tools.get_annotations(query_id=1, author_prefix="agent:")
    annotations_alias = await tools.list_annotations(query_id=1, color="yellow")
    selection = await tools.get_selection(selection_id="sel_1")

    assert rows["rows"] == [
        {"_row_identity": "a", "value": 1},
        {"_row_identity": "b", "value": 2},
    ]
    assert rows["fingerprints"] == {"sql": "s", "schema": "c", "result": "r"}
    assert trajectories_summary["trajectory_count"] == EXPECTED_TRAJECTORY_COUNT
    assert trajectories_summary["trajectories"] == [
        {"group_key": "s1", "message_count": 1},
        {"group_key": "s2", "message_count": 1},
    ]
    assert trajectory["trajectories"][0]["messages"][0]["content"] == "hi"
    assert labels == [{"row_identity": "a", "labels": {"quality": "bad"}}]
    assert annotations[0]["author_prefix"] == "agent:"
    assert annotations_alias[0]["color"] == "yellow"
    assert selection["id"] == "sel_1"


async def test_get_rows_rejects_large_limit() -> None:
    tools = make_tools()

    with pytest.raises(McpError) as exc_info:
        await tools.get_rows(query_id=1, limit=501)

    assert "Use export_context" in str(exc_info.value)


async def test_export_context_writes_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    tools = make_tools()

    result = await tools.export_context(query_id=1)

    assert result["scope"] == "all"
    assert await _path_exists(result["path"])
    assert await _path_exists(result["files"]["manifest"])
    assert await _path_exists(result["files"]["rows"])
    assert await _path_exists(result["files"]["columns"])
    assert await _path_exists(result["files"]["labels"])
    assert await _path_exists(result["files"]["annotations"])
    assert "selection" not in result["files"]
    assert await _path_exists(result["files"]["agentlens_context"])
    manifest = json.loads(await _read_text(result["files"]["manifest"]))
    assert manifest["query_id"] == 1


async def test_export_context_uses_selection_scope_when_selection_id_is_supplied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    tools = make_tools()

    result = await tools.export_context(query_id=1, selection_id="sel_1")

    assert result["scope"] == "selection"
    assert await _path_exists(result["path"])
    assert await _path_exists(result["files"]["manifest"])
    assert await _path_exists(result["files"]["rows"])
    assert await _path_exists(result["files"]["columns"])
    assert await _path_exists(result["files"]["labels"])
    assert await _path_exists(result["files"]["annotations"])
    assert await _path_exists(result["files"]["selection"])
    assert await _path_exists(result["files"]["agentlens_context"])
    manifest = json.loads(await _read_text(result["files"]["manifest"]))
    assert manifest["query_id"] == 1


async def test_export_context_requires_selection_id_for_selection_scope() -> None:
    tools = make_tools()

    with pytest.raises(McpError) as exc_info:
        await tools.export_context(query_id=1, scope="selection")

    assert "selection_id is required" in str(exc_info.value)


async def test_write_back_tools_force_author_and_use_batch() -> None:
    client = FakeAsyncClient()
    tools = make_tools(client)

    annotation = await tools.add_annotation(
        query_id=1,
        row_identity="a",
        color="red",
        text="bad answer",
    )
    batch = await tools.highlight_rows(
        query_id=1,
        row_identities=["a", "b"],
        color="yellow",
        note="same issue",
    )

    assert annotation["author"] == "agent:pytest"
    assert client.created_annotations[0]["author"] == "agent:pytest"
    assert batch["created_count"] == EXPECTED_BATCH_COUNT
    assert len(client.batch_annotations) == 1
    assert [item["row_identity"] for item in client.batch_annotations[0]] == ["a", "b"]


async def test_write_back_validation_errors() -> None:
    tools = make_tools()

    with pytest.raises(McpError, match="color must be one of"):
        await tools.add_annotation(query_id=1, row_identity="a", color="purple")
    with pytest.raises(McpError, match="row_identities is limited"):
        await tools.highlight_rows(query_id=1, row_identities=["x"] * 201, color="red")
    with pytest.raises(McpError, match="Refusing to clear"):
        await tools.clear_annotations(query_id=1)


async def test_clear_annotations_passes_filters() -> None:
    client = FakeAsyncClient()
    tools = make_tools(client)

    result = await tools.clear_annotations(query_id=1, author="agent:pytest")

    assert result["deleted_count"] == 1
    assert client.clear_filters == [
        {
            "author": "agent:pytest",
            "author_prefix": None,
            "color": None,
            "annotation_set": None,
        }
    ]


async def test_backend_unavailable_becomes_mcp_error() -> None:
    tools = make_tools(UnavailableAsyncClient())

    with pytest.raises(McpError) as exc_info:
        await tools.get_backend_info()

    assert "Start AgentLens backend" in str(exc_info.value)


async def _path_exists(path: str) -> bool:
    return await asyncio.to_thread(Path(path).exists)


async def _read_text(path: str) -> str:
    return await asyncio.to_thread(Path(path).read_text, encoding="utf-8")
