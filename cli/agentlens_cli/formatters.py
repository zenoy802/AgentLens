from __future__ import annotations

import csv
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TextIO

from rich.console import Console
from rich.table import Table

_RECORD_KEYS = ("rows", "items", "annotations", "trajectories")


def format_output(
    data: Any,
    fmt: str,
    output_file: Path | None = None,
    metadata_output_file: Path | None = None,
) -> None:
    with _output_stream(output_file) as stream:
        if fmt == "json":
            json.dump(data, stream, indent=2, ensure_ascii=False, default=str)
            stream.write("\n")
            return
        if fmt == "jsonl":
            records, metadata = _extract_records(data)
            if metadata_output_file is not None and metadata is not None:
                metadata_output_file.parent.mkdir(parents=True, exist_ok=True)
                metadata_output_file.write_text(
                    json.dumps(metadata, indent=2, ensure_ascii=False, default=str) + "\n",
                    encoding="utf-8",
                )
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False, default=str))
                stream.write("\n")
            return
        if fmt == "csv":
            _write_csv(stream, _extract_records(data)[0])
            return
        if fmt == "pretty":
            _write_pretty(stream, data)
            return
    raise ValueError(f"Unsupported output format: {fmt}")


@contextmanager
def _output_stream(output_file: Path | None) -> Iterator[TextIO]:
    if output_file is None:
        yield sys.stdout
        return
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8", newline="") as handle:
        yield handle


def _extract_records(data: Any) -> tuple[list[Any], dict[str, Any] | None]:
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict):
        for key in _RECORD_KEYS:
            value = data.get(key)
            if isinstance(value, list):
                metadata = {
                    metadata_key: item for metadata_key, item in data.items() if metadata_key != key
                }
                return value, metadata
        labels_by_row = data.get("labels_by_row")
        if isinstance(labels_by_row, dict):
            records = [
                {"row_identity": row_identity, "labels": labels}
                for row_identity, labels in labels_by_row.items()
            ]
            return records, {"query_id": data.get("query_id")} if "query_id" in data else None
    raise ValueError("jsonl and csv output require records, rows, items, or annotations.")


def _write_csv(stream: TextIO, records: list[Any]) -> None:
    normalized = [_normalize_record(record) for record in records]
    fieldnames = _fieldnames(normalized)
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    for record in normalized:
        writer.writerow({key: _csv_cell(record.get(key)) for key in fieldnames})


def _normalize_record(record: Any) -> dict[str, Any]:
    if isinstance(record, dict):
        return record
    return {"value": record}


def _fieldnames(records: list[dict[str, Any]]) -> list[str]:
    fields: list[str] = []
    seen: set[str] = set()
    for record in records:
        for key in record:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    return fields or ["value"]


def _csv_cell(value: Any) -> Any:
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False, default=str)
    return value


def _write_pretty(stream: TextIO, data: Any) -> None:
    console = Console(file=stream, force_terminal=stream.isatty(), color_system="auto")
    records, metadata = _records_for_pretty(data)
    if metadata:
        console.print_json(json.dumps(metadata, ensure_ascii=False, default=str))
    if not records:
        console.print("(no records)")
        return
    normalized = [_normalize_record(record) for record in records]
    fieldnames = _fieldnames(normalized)
    table = Table(show_lines=False)
    for field in fieldnames:
        table.add_column(field)
    for record in normalized:
        table.add_row(*[_pretty_cell(record.get(field)) for field in fieldnames])
    console.print(table)


def _records_for_pretty(data: Any) -> tuple[list[Any], dict[str, Any] | None]:
    try:
        return _extract_records(data)
    except ValueError:
        if isinstance(data, dict):
            return [{"key": key, "value": value} for key, value in data.items()], None
        return [{"value": data}], None


def _pretty_cell(value: Any) -> str:
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False, default=str)
    return "" if value is None else str(value)
