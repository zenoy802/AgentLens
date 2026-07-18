from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import tiktoken
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session
from tiktoken import Encoding

from app.db.session import get_session_factory
from app.models.connection import Connection
from app.services.connection_service import _build_sqlalchemy_connect_args, _build_sqlalchemy_url

DEFAULT_DATASET_ID = "trajectory-performance-v1"
DEFAULT_TABLE = "agentlens_trajectory_performance_mock"
DEFAULT_TRAJECTORY_COUNT = 10
DEFAULT_MESSAGES_PER_TRAJECTORY = 21
DEFAULT_TOKENS_PER_MESSAGE = 10_000
DEFAULT_ENCODING = "cl100k_base"
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[2]
    / ".agentlens-test-data"
    / "trajectory-performance"
    / "trajectories.jsonl"
)
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ROLES = ("system", "user", "assistant", "tool")
_CONTENT_FILLER = """
## Diagnostic context

The agent is investigating a trajectory rendering performance regression. Preserve this
markdown, the nested JSON, and the code block so the viewer exercises realistic rich content.

```python
def summarize_trace(session_id: str, message_index: int) -> dict[str, object]:
    return {"session_id": session_id, "message_index": message_index, "status": "observed"}
```

```json
{"metrics":{"latency_ms":418,"tokens":10000},"tags":["performance","trajectory","mock"]}
```

| phase | status | note |
| --- | --- | --- |
| query | complete | long payload fetched |
| aggregate | complete | messages grouped |
| render | pending | markdown and JSON remain visible |

The payload intentionally repeats structured prose to approximate a long LLM message while
remaining deterministic and safe to inspect. performance trajectory rendering payload datum.
""".strip()


@dataclass(frozen=True, slots=True)
class SeedConfig:
    trajectory_count: int = DEFAULT_TRAJECTORY_COUNT
    messages_per_trajectory: int = DEFAULT_MESSAGES_PER_TRAJECTORY
    tokens_per_message: int = DEFAULT_TOKENS_PER_MESSAGE
    dataset_id: str = DEFAULT_DATASET_ID

    @property
    def row_count(self) -> int:
        return self.trajectory_count * self.messages_per_trajectory


@dataclass(frozen=True, slots=True)
class ImportSummary:
    connection_id: int
    connection_name: str
    database: str
    table: str
    row_count: int


def build_content(
    *,
    encoding: Encoding,
    token_count: int,
    session_id: str,
    message_index: int,
    role: str,
) -> str:
    if token_count <= 0:
        raise ValueError("token_count must be positive")

    prefix = (
        f"# Performance fixture message\n\n"
        f"- session_id: `{session_id}`\n"
        f"- message_index: `{message_index}`\n"
        f"- role: `{role}`\n\n"
    )
    prefix_tokens = encoding.encode(prefix)
    if len(prefix_tokens) >= token_count:
        return encoding.decode(prefix_tokens[:token_count])

    filler_tokens = encoding.encode(_CONTENT_FILLER + "\n\n")
    remaining = token_count - len(prefix_tokens)
    repeats = (remaining + len(filler_tokens) - 1) // len(filler_tokens)
    content_tokens = prefix_tokens + (filler_tokens * repeats)[:remaining]
    return encoding.decode(content_tokens)


def iter_rows(config: SeedConfig, encoding: Encoding) -> Iterator[dict[str, Any]]:
    started_at = datetime(2026, 1, 1, tzinfo=UTC)
    for trajectory_number in range(1, config.trajectory_count + 1):
        session_id = f"perf-trajectory-{trajectory_number:02d}"
        for message_index in range(config.messages_per_trajectory):
            role = _ROLES[message_index % len(_ROLES)]
            message_id = f"perf-t{trajectory_number:02d}-m{message_index:03d}"
            tool_calls: list[dict[str, Any]] | None = None
            if role == "assistant":
                tool_calls = [
                    {
                        "id": f"call-{trajectory_number:02d}-{message_index:03d}",
                        "type": "function",
                        "function": {
                            "name": "inspect_render_metrics",
                            "arguments": json.dumps(
                                {
                                    "session_id": session_id,
                                    "message_index": message_index,
                                },
                                separators=(",", ":"),
                            ),
                        },
                    }
                ]

            yield {
                "message_id": message_id,
                "dataset_id": config.dataset_id,
                "session_id": session_id,
                "message_index": message_index,
                "role": role,
                "content": build_content(
                    encoding=encoding,
                    token_count=config.tokens_per_message,
                    session_id=session_id,
                    message_index=message_index,
                    role=role,
                ),
                "content_token_count": config.tokens_per_message,
                "tool_calls": tool_calls,
                "metadata": {
                    "fixture": "trajectory-performance",
                    "trajectory_number": trajectory_number,
                    "render_hints": ["markdown", "code", "json", "table"],
                },
                "created_at": (
                    started_at + timedelta(minutes=trajectory_number, seconds=message_index)
                ).isoformat(),
            }


def write_jsonl(path: Path, config: SeedConfig, encoding: Encoding) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0
    with path.open("w", encoding="utf-8") as output:
        for row in iter_rows(config, encoding):
            output.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            output.write("\n")
            row_count += 1
    return row_count


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number} of {path}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected a JSON object on line {line_number} of {path}")
            yield value


def resolve_connection(
    session: Session,
    *,
    connection_id: int | None,
    connection_name: str | None,
) -> Connection:
    statement = select(Connection).where(Connection.db_type == "mysql")
    if connection_id is not None:
        statement = statement.where(Connection.id == connection_id)
    if connection_name is not None:
        statement = statement.where(Connection.name == connection_name)
    connections = list(session.scalars(statement.order_by(Connection.id)))
    if not connections:
        selector = connection_id if connection_id is not None else connection_name
        raise ValueError(f"No matching MySQL connection found: {selector!r}")
    if len(connections) > 1:
        names = ", ".join(connection.name for connection in connections)
        raise ValueError(f"Multiple MySQL connections found; select one explicitly: {names}")
    return connections[0]


def validate_table_name(table: str) -> str:
    if _IDENTIFIER_PATTERN.fullmatch(table) is None:
        raise ValueError("table must contain only letters, digits, and underscores")
    return table


def import_jsonl(engine: Engine, path: Path, table: str, *, batch_size: int = 25) -> int:
    validated_table = validate_table_name(table)
    create_statement = text(
        f"""
        CREATE TABLE IF NOT EXISTS `{validated_table}` (
            message_id VARCHAR(64) NOT NULL PRIMARY KEY,
            dataset_id VARCHAR(64) NOT NULL,
            session_id VARCHAR(64) NOT NULL,
            message_index INT NOT NULL,
            role VARCHAR(32) NOT NULL,
            content LONGTEXT NOT NULL,
            content_token_count INT NOT NULL,
            tool_calls JSON NULL,
            metadata JSON NOT NULL,
            created_at DATETIME(6) NOT NULL,
            UNIQUE KEY uq_perf_dataset_session_message
                (dataset_id, session_id, message_index),
            KEY idx_perf_dataset_session (dataset_id, session_id)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """
    )
    upsert_statement = text(
        f"""
        INSERT INTO `{validated_table}` (
            message_id, dataset_id, session_id, message_index, role, content,
            content_token_count, tool_calls, metadata, created_at
        ) VALUES (
            :message_id, :dataset_id, :session_id, :message_index, :role, :content,
            :content_token_count, :tool_calls, :metadata, :created_at
        )
        ON DUPLICATE KEY UPDATE
            dataset_id = VALUES(dataset_id),
            session_id = VALUES(session_id),
            message_index = VALUES(message_index),
            role = VALUES(role),
            content = VALUES(content),
            content_token_count = VALUES(content_token_count),
            tool_calls = VALUES(tool_calls),
            metadata = VALUES(metadata),
            created_at = VALUES(created_at)
        """
    )

    imported_count = 0
    batch: list[dict[str, Any]] = []
    with engine.begin() as connection:
        connection.execute(create_statement)
        for row in iter_jsonl(path):
            batch.append(_to_insert_params(row))
            if len(batch) >= batch_size:
                connection.execute(upsert_statement, batch)
                imported_count += len(batch)
                batch.clear()
        if batch:
            connection.execute(upsert_statement, batch)
            imported_count += len(batch)
    return imported_count


def seed_connection(
    *,
    path: Path,
    table: str,
    connection_id: int | None,
    connection_name: str | None,
) -> ImportSummary:
    session_factory = get_session_factory()
    with session_factory() as session:
        selected_connection = resolve_connection(
            session,
            connection_id=connection_id,
            connection_name=connection_name,
        )
        engine = create_engine(
            _build_sqlalchemy_url(selected_connection),
            connect_args=_build_sqlalchemy_connect_args(selected_connection),
        )
        try:
            row_count = import_jsonl(engine, path, table)
        finally:
            engine.dispose()
        return ImportSummary(
            connection_id=selected_connection.id,
            connection_name=selected_connection.name,
            database=selected_connection.database,
            table=table,
            row_count=row_count,
        )


def _to_insert_params(row: dict[str, Any]) -> dict[str, Any]:
    required_fields = {
        "message_id",
        "dataset_id",
        "session_id",
        "message_index",
        "role",
        "content",
        "content_token_count",
        "metadata",
        "created_at",
    }
    missing_fields = sorted(required_fields.difference(row))
    if missing_fields:
        raise ValueError(f"JSONL row is missing required fields: {', '.join(missing_fields)}")
    return {
        **{field: row[field] for field in required_fields if field != "created_at"},
        "created_at": _parse_mysql_datetime(row["created_at"]),
        "tool_calls": (
            None
            if row.get("tool_calls") is None
            else json.dumps(row["tool_calls"], ensure_ascii=False, separators=(",", ":"))
        ),
        "metadata": json.dumps(row["metadata"], ensure_ascii=False, separators=(",", ":")),
    }


def _parse_mysql_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("created_at must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"created_at is not valid ISO 8601: {value!r}") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate and import large trajectory data for local UI performance testing."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--table", default=DEFAULT_TABLE)
    parser.add_argument("--connection-id", type=_positive_int)
    parser.add_argument("--connection-name")
    parser.add_argument("--trajectories", type=_positive_int, default=DEFAULT_TRAJECTORY_COUNT)
    parser.add_argument(
        "--messages-per-trajectory",
        type=_positive_int,
        default=DEFAULT_MESSAGES_PER_TRAJECTORY,
    )
    parser.add_argument(
        "--tokens-per-message",
        type=_positive_int,
        default=DEFAULT_TOKENS_PER_MESSAGE,
    )
    parser.add_argument("--generate-only", action="store_true")
    args = parser.parse_args(argv)
    if args.connection_id is not None and args.connection_name is not None:
        parser.error("--connection-id and --connection-name are mutually exclusive")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = SeedConfig(
        trajectory_count=args.trajectories,
        messages_per_trajectory=args.messages_per_trajectory,
        tokens_per_message=args.tokens_per_message,
    )
    encoding = tiktoken.get_encoding(DEFAULT_ENCODING)
    generated_count = write_jsonl(args.output, config, encoding)
    print(
        f"Generated {generated_count} rows at {args.output} ({args.output.stat().st_size} bytes)."
    )
    if args.generate_only:
        return 0

    summary = seed_connection(
        path=args.output,
        table=args.table,
        connection_id=args.connection_id,
        connection_name=args.connection_name,
    )
    print(
        f"Imported {summary.row_count} rows into connection "
        f"{summary.connection_name!r} (id={summary.connection_id}), "
        f"database {summary.database!r}, table {summary.table!r}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
