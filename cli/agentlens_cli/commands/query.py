from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from agentlens_cli.errors import handle_errors
from agentlens_cli.formatters import format_output
from agentlens_cli.main import CliState, format_option, output_option, resolved_format


@click.group(
    help="""Read and execute AgentLens queries through the backend.

Examples:
  agentlens query list
  agentlens query exec --connection local-mysql --sql "SELECT * FROM traces LIMIT 10"

Query commands are live backend operations. Use `agentlens context export` when you need a
local, reproducible snapshot for file-based analysis.
""",
)
def query() -> None:
    pass


@query.command(
    "list",
    help="""List saved and temporary queries.

Example:
  agentlens query list --format json

This is live access by reference. Snapshot export is available through `agentlens context export`.
""",
)
@format_option
@output_option
@click.pass_obj
@handle_errors
def list_queries(state: CliState, fmt: str | None, output_file: Path | None) -> None:
    format_output(
        state.client.list_queries(),
        resolved_format(state, fmt),
        output_file=output_file,
    )


@query.command(
    "show",
    help="""Show a query definition.

Example:
  agentlens query show 42

This is live access by reference. Snapshot export is available through `agentlens context export`.
""",
)
@click.argument("query_id", type=int)
@format_option
@output_option
@click.pass_obj
@handle_errors
def show_query(
    state: CliState,
    query_id: int,
    fmt: str | None,
    output_file: Path | None,
) -> None:
    format_output(
        state.client.show_query(query_id),
        resolved_format(state, fmt),
        output_file=output_file,
    )


@query.command(
    "exec",
    help="""Execute SQL against a named AgentLens connection.

Examples:
  agentlens query exec --connection local-mysql --sql "SELECT * FROM traces LIMIT 10"
  agentlens query exec --connection local-mysql --sql-file query.sql

This is live access by reference and does not export files. Use `agentlens context export` for
snapshot read by value.
""",
)
@click.option("--connection", "connection_name", required=True, help="Connection name.")
@click.option("--sql", default=None, help="SQL string to execute.")
@click.option(
    "--sql-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to a SQL file.",
)
@click.option("--row-limit", type=click.IntRange(min=1, max=100000), default=None)
@format_option
@output_option
@click.pass_obj
@handle_errors
def exec_query(
    state: CliState,
    connection_name: str,
    sql: str | None,
    sql_file: Path | None,
    row_limit: int | None,
    fmt: str | None,
    output_file: Path | None,
) -> None:
    sql_text = _resolve_sql(sql, sql_file)
    result = state.client.exec_query(connection_name, sql_text, row_limit=row_limit)
    format_output(
        _execution_summary(result),
        resolved_format(state, fmt),
        output_file=output_file,
    )


@query.command(
    "rerun",
    help="""Rerun an existing query through the backend.

Example:
  agentlens query rerun 42

This is live access by reference and does not export files. Use `agentlens context export` for
snapshot read by value.
""",
)
@click.argument("query_id", type=int)
@format_option
@output_option
@click.pass_obj
@handle_errors
def rerun_query(
    state: CliState,
    query_id: int,
    fmt: str | None,
    output_file: Path | None,
) -> None:
    format_output(
        _execution_summary(state.client.rerun_query(query_id)),
        resolved_format(state, fmt),
        output_file=output_file,
    )


def _resolve_sql(sql: str | None, sql_file: Path | None) -> str:
    if (sql is None) == (sql_file is None):
        raise click.UsageError("Provide exactly one of --sql or --sql-file.")
    if sql_file is not None:
        return sql_file.read_text(encoding="utf-8")
    assert sql is not None
    return sql


def _execution_summary(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"result": result}
    execution = result.get("execution", {})
    row_count = execution.get("row_count") if isinstance(execution, dict) else None
    columns = result.get("columns", [])
    rows = result.get("rows", [])
    return {
        "query_id": result.get("query_id"),
        "row_count": row_count,
        "columns_preview": columns[:20] if isinstance(columns, list) else [],
        "column_count": len(columns) if isinstance(columns, list) else 0,
        "fingerprints": result.get("fingerprints", {}),
        "preview_rows": rows[:5] if isinstance(rows, list) else [],
        "execution": execution,
        "warnings": result.get("warnings", []),
    }


__all__ = ["query"]
