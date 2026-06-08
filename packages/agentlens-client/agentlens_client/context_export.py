from __future__ import annotations

import json
import secrets
import shutil
import tempfile
from collections.abc import Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentlens_client.errors import BackendBusinessError
from agentlens_client.sync_client import AgentLensSyncClient
from agentlens_client.types import ContextExportResult, ContextScope, OutputTarget

_MAX_EXPORT_ROWS = 100000
_PRIMARY_ROW_IDENTITY_KEY = "_row_identity"
_FALLBACK_ROW_IDENTITY_PREFIX = "_agent_lens_row_identity"


def export_context(
    *,
    client: AgentLensSyncClient,
    query_id: int,
    selection_id: str | None = None,
    scope: ContextScope | None = None,
    output_dir: Path | None = None,
    target: OutputTarget = "generic",
    backend_url: str | None = None,
) -> ContextExportResult:
    resolved_scope = _resolve_scope(scope, selection_id)
    created_at = datetime.now(UTC)
    context_id = f"ctx_{created_at:%Y%m%d_%H%M%S}_{secrets.token_hex(4)}"
    destination = _resolve_output_dir(output_dir, query_id, created_at)

    selection = None
    selected_identities: set[str] | None = None
    selected_identity_list: list[str] | None = None
    if resolved_scope == "selection":
        if selection_id is None:
            raise BackendBusinessError(
                "--selection is required when --scope selection is used.",
                code="CONTEXT_SELECTION_REQUIRED",
                status_code=400,
            )
        selection = client.get_selection(selection_id)
        if isinstance(selection, dict) and selection.get("query_id") != query_id:
            raise BackendBusinessError(
                "Selection snapshot belongs to a different query.",
                code="CONTEXT_SELECTION_QUERY_MISMATCH",
                detail={"query_id": query_id, "selection_query_id": selection.get("query_id")},
                status_code=400,
                backend_url=client.base_url,
            )
        selected_identity_list = _selection_identities(selection)
        selected_identities = set(selected_identity_list)

    rows_envelope = client.get_rows(query_id, limit=_MAX_EXPORT_ROWS, offset=0)
    if _is_truncated(rows_envelope):
        raise BackendBusinessError(
            "Context export would be incomplete because the backend truncated the query result.",
            code="CONTEXT_EXPORT_TRUNCATED",
            detail={"query_id": query_id, "max_rows": _MAX_EXPORT_ROWS},
            status_code=400,
            backend_url=client.base_url,
        )

    identity_key = _identity_key(rows_envelope)
    source_rows = _rows(rows_envelope)
    source_row_identities = {
        identity
        for row in source_rows
        if (identity := _row_identity(row, identity_key)) is not None
    }
    missing_row_identities = (
        [identity for identity in selected_identity_list if identity not in source_row_identities]
        if selected_identity_list is not None
        else []
    )
    rows = _filter_rows(source_rows, selected_identities, identity_key)
    exported_row_identities = [
        identity for row in rows if (identity := _row_identity(row, identity_key)) is not None
    ]
    labels_payload = (
        client.get_labels_for_rows(query_id, exported_row_identities)
        if hasattr(client, "get_labels_for_rows")
        else client.get_labels(query_id)
    )
    labels = _filter_labels(labels_payload, selected_identities)
    annotations = _filter_annotations(client.get_annotations(query_id), selected_identities)
    columns = {
        "query_id": query_id,
        "columns": rows_envelope.get("columns", []) if isinstance(rows_envelope, dict) else [],
        "suggested_field_renders": (
            rows_envelope.get("suggested_field_renders", {})
            if isinstance(rows_envelope, dict)
            else {}
        ),
    }

    files: dict[str, str] = {
        "columns": "columns.json",
        "rows": "rows.jsonl",
        "labels": "labels.jsonl",
        "annotations": "annotations.jsonl",
    }
    if selection is not None:
        files["selection"] = "selection.json"

    manifest = {
        "context_id": context_id,
        "query_id": query_id,
        "selection_id": selection_id if resolved_scope == "selection" else None,
        "scope": resolved_scope,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "backend_url": backend_url or client.base_url,
        "files": files,
        "fingerprints": (
            rows_envelope.get("fingerprints", {}) if isinstance(rows_envelope, dict) else {}
        ),
        "selection": (
            {
                "requested_row_count": len(selected_identity_list),
                "exported_row_count": len(exported_row_identities),
                "missing_row_count": len(missing_row_identities),
                "missing_row_identities": missing_row_identities,
            }
            if selected_identity_list is not None
            else None
        ),
    }
    extra_files = {
        "manifest": "manifest.json",
        "context": "AGENTLENS_CONTEXT.md",
    }
    if target == "claude-code":
        extra_files["claude"] = "CLAUDE.md"

    _write_export_files(
        destination=destination,
        files=files,
        extra_files=extra_files,
        columns=columns,
        rows=rows,
        labels=labels,
        annotations=annotations,
        selection=selection,
        manifest=manifest,
        context_text=_agentlens_context_md(target, selection),
        claude_text=_claude_md(selection is not None) if target == "claude-code" else None,
        backend_url=client.base_url,
    )

    return {
        "context_id": context_id,
        "query_id": query_id,
        "selection_id": manifest["selection_id"],
        "scope": resolved_scope,
        "output_dir": str(destination),
        "manifest_path": str(destination / "manifest.json"),
        "files": {
            **files,
            **extra_files,
        },
    }


def _resolve_scope(scope: ContextScope | None, selection_id: str | None) -> ContextScope:
    if scope is not None:
        return scope
    return "selection" if selection_id is not None else "all"


def _resolve_output_dir(output_dir: Path | None, query_id: int, created_at: datetime) -> Path:
    if output_dir is not None:
        return output_dir.expanduser().resolve()
    timestamp = created_at.strftime("%Y%m%d_%H%M%S")
    return (Path.home() / ".agentlens" / "contexts" / f"query_{query_id}_{timestamp}").resolve()


def _rows(envelope: Any) -> list[dict[str, Any]]:
    if isinstance(envelope, dict) and isinstance(envelope.get("rows"), list):
        return [row for row in envelope["rows"] if isinstance(row, dict)]
    return []


def _filter_rows(
    rows: list[dict[str, Any]],
    selected_identities: set[str] | None,
    identity_key: str | None = None,
) -> list[dict[str, Any]]:
    if selected_identities is None:
        return rows
    return [
        row
        for row in rows
        if (identity := _row_identity(row, identity_key)) is not None
        and identity in selected_identities
    ]


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


def _is_truncated(envelope: Any) -> bool:
    if not isinstance(envelope, dict):
        return False
    if envelope.get("truncated") is True:
        return True
    execution = envelope.get("execution")
    if isinstance(execution, dict) and execution.get("truncated") is True:
        return True
    return any(
        isinstance(warning, dict) and warning.get("code") == "RESULT_TRUNCATED"
        for warning in _as_list(envelope.get("warnings"))
    )


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _selection_identities(selection: Any) -> list[str]:
    if not isinstance(selection, dict):
        return []
    identities = selection.get("row_identities")
    if not isinstance(identities, list):
        return []
    return [str(identity) for identity in identities]


def _filter_labels(
    labels_payload: Any,
    selected_identities: set[str] | None,
) -> list[dict[str, Any]]:
    labels_by_row = (
        labels_payload.get("labels_by_row", {}) if isinstance(labels_payload, dict) else {}
    )
    if not isinstance(labels_by_row, dict):
        return []
    records = [
        {"row_identity": str(row_identity), "labels": labels}
        for row_identity, labels in labels_by_row.items()
        if selected_identities is None or str(row_identity) in selected_identities
    ]
    return records


def _filter_annotations(
    annotations_payload: Any,
    selected_identities: set[str] | None,
) -> list[dict[str, Any]]:
    if not isinstance(annotations_payload, list):
        return []
    annotations = [item for item in annotations_payload if isinstance(item, dict)]
    if selected_identities is None:
        return annotations
    return [
        annotation
        for annotation in annotations
        if str(annotation.get("row_identity")) in selected_identities
    ]


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str))
            handle.write("\n")


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _write_export_files(
    *,
    destination: Path,
    files: dict[str, str],
    extra_files: dict[str, str],
    columns: dict[str, Any],
    rows: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
    selection: Any,
    manifest: dict[str, Any],
    context_text: str,
    claude_text: str | None,
    backend_url: str,
) -> None:
    all_file_names = [*files.values(), *extra_files.values()]
    working_dir = _create_working_dir(destination, backend_url=backend_url)
    try:
        _write_json(working_dir / files["columns"], columns)
        _write_jsonl(working_dir / files["rows"], rows)
        _write_jsonl(working_dir / files["labels"], labels)
        _write_jsonl(working_dir / files["annotations"], annotations)
        if selection is not None:
            _write_json(working_dir / files["selection"], selection)
        _write_json(working_dir / extra_files["manifest"], manifest)
        _write_text(working_dir / extra_files["context"], context_text)
        if claude_text is not None:
            _write_text(working_dir / extra_files["claude"], claude_text)
        _commit_working_dir(working_dir, destination, all_file_names, backend_url=backend_url)
    except BackendBusinessError:
        _cleanup_working_dir(working_dir)
        raise
    except OSError as exc:
        _cleanup_working_dir(working_dir)
        raise BackendBusinessError(
            "Context export output directory is not writable.",
            code="CONTEXT_EXPORT_OUTPUT_DIR_NOT_WRITABLE",
            detail={"output_dir": str(destination), "error": str(exc)},
            status_code=400,
            backend_url=backend_url,
        ) from exc
    except Exception:
        _cleanup_working_dir(working_dir)
        raise


def _create_working_dir(destination: Path, *, backend_url: str) -> Path:
    try:
        if destination.exists() and not destination.is_dir():
            raise BackendBusinessError(
                "Context export output path is not a directory.",
                code="CONTEXT_EXPORT_OUTPUT_DIR_NOT_WRITABLE",
                detail={"output_dir": str(destination)},
                status_code=400,
                backend_url=backend_url,
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        return Path(
            tempfile.mkdtemp(
                prefix=f".{destination.name}.tmp-",
                dir=destination.parent,
            )
        )
    except OSError as exc:
        raise BackendBusinessError(
            "Context export output directory is not writable.",
            code="CONTEXT_EXPORT_OUTPUT_DIR_NOT_WRITABLE",
            detail={"output_dir": str(destination), "error": str(exc)},
            status_code=400,
            backend_url=backend_url,
        ) from exc


def _commit_working_dir(
    working_dir: Path,
    destination: Path,
    file_names: Sequence[str],
    *,
    backend_url: str,
) -> None:
    if destination.exists():
        existing_files = [name for name in file_names if (destination / name).exists()]
        if existing_files:
            raise BackendBusinessError(
                "Context export output directory already contains AgentLens export files.",
                code="CONTEXT_EXPORT_OUTPUT_DIR_NOT_EMPTY",
                detail={"output_dir": str(destination), "files": existing_files},
                status_code=400,
                backend_url=backend_url,
            )
        moved_files: list[Path] = []
        try:
            for source in working_dir.iterdir():
                target = destination / source.name
                source.replace(target)
                moved_files.append(target)
            working_dir.rmdir()
        except OSError:
            for moved_file in moved_files:
                with suppress(OSError):
                    moved_file.unlink()
            raise
        return

    working_dir.replace(destination)


def _cleanup_working_dir(working_dir: Path) -> None:
    shutil.rmtree(working_dir, ignore_errors=True)


def _agentlens_context_md(target: OutputTarget, selection: Any) -> str:
    selection_line = (
        "- `selection.json` is the user selection snapshot for this export.\n"
        if selection is not None
        else ""
    )
    target_line = (
        "- `CLAUDE.md` is included because this export was created for Claude Code.\n"
        if target == "claude-code"
        else ""
    )
    return f"""# AgentLens Context

This directory is a static AgentLens context export.
It is a snapshot read by value, not a live link.

## Files

- `rows.jsonl` is the query result. Each line is one JSON object.
- `columns.json` contains column structure and render hints.
- `labels.jsonl` contains human labels keyed by row identity.
- `annotations.jsonl` contains existing visual annotations from AgentLens.
{selection_line}{target_line}- `manifest.json` records query id, scope, timestamps,
  fingerprints, and file names.

## Write Back

Use `agentlens annotate` or `agentlens highlight` to write annotations back to the AgentLens UI.
MCP clients can use `add_annotation` or `highlight_rows` for the same write-back flow.

Live access reads current backend state by reference:

```bash
agentlens data rows --query <query_id>
```

Context export is a reproducible snapshot read by value:

```bash
agentlens context export --query <query_id>
```
"""


def _claude_md(has_selection: bool) -> str:
    selection_text = (
        "Use `selection.json` to identify which row identities were selected by the user.\n"
        if has_selection
        else ""
    )
    return f"""# Claude Code AgentLens Context

This directory contains a static AgentLens context export.

Read `AGENTLENS_CONTEXT.md` first, then inspect:

- `manifest.json`
- `columns.json`
- `rows.jsonl`
- `labels.jsonl`
- `annotations.jsonl`

{selection_text}To write findings back to AgentLens, use:

```bash
agentlens annotate --query <query_id> --row <row_identity> --color red --author agent:claude-code
agentlens highlight --query <query_id> --rows <row1,row2> --color yellow --author agent:claude-code
```

Do not call an LLM to regenerate this context. The files are already the exported snapshot.
"""


__all__ = ["export_context"]
