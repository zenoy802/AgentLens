from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, TypedDict

OutputTarget = Literal["generic", "claude-code"]
ContextScope = Literal["all", "selection"]


class ContextExportResult(TypedDict):
    context_id: str
    query_id: int
    selection_id: str | None
    scope: ContextScope
    output_dir: str
    manifest_path: str
    files: dict[str, str]


class ContextExportOptions(TypedDict, total=False):
    query_id: int
    selection_id: str | None
    scope: ContextScope
    output_dir: Path | None
    target: OutputTarget
    backend_url: str


JsonObject = dict[str, Any]
