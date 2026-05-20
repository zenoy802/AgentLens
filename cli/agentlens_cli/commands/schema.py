from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import click

from agentlens_cli import __version__
from agentlens_cli.errors import handle_errors
from agentlens_cli.formatters import format_output
from agentlens_cli.main import CliState, format_option, output_option, resolved_format


@click.group(
    help="""Inspect AgentLens bridge schemas and limits.

Examples:
  agentlens schema info
  agentlens schema columns --query 42

Schema commands are live access by reference. Use `agentlens context export` when you need a
local snapshot that includes columns, labels, annotations, and rows.
""",
)
def schema() -> None:
    pass


@schema.command(
    "info",
    help="""Show backend and CLI schema information.

Example:
  agentlens schema info --format json

This is live access by reference. Use `agentlens context export` for snapshot read by value.
""",
)
@format_option
@output_option
@click.pass_obj
@handle_errors
def info(state: CliState, fmt: str | None, output_file: Path | None) -> None:
    payload = state.client.schema_info()
    if isinstance(payload, dict):
        payload["cli_version"] = _cli_version()
        payload["recommended_workflow"] = (
            "Small data: use `agentlens data rows --query <id>` for live access. "
            "Large data: use `agentlens context export --query <id>` for a reproducible "
            "snapshot. Write back with `agentlens annotate` or `agentlens highlight`."
        )
    format_output(payload, resolved_format(state, fmt), output_file=output_file)


@schema.command(
    "columns",
    help="""Show inferred columns and render hints for a query.

Example:
  agentlens schema columns --query 42

This is live access by reference. Use `agentlens context export` for a snapshot containing
columns.json.
""",
)
@click.option("--query", "query_id", required=True, type=int, help="Query id.")
@format_option
@output_option
@click.pass_obj
@handle_errors
def columns(
    state: CliState,
    query_id: int,
    fmt: str | None,
    output_file: Path | None,
) -> None:
    format_output(
        state.client.get_column_schema(query_id),
        resolved_format(state, fmt),
        output_file=output_file,
    )


@schema.command(
    "labels",
    help="""Show label schema for a query.

Example:
  agentlens schema labels --query 42

This is live access by reference. Use `agentlens context export` for snapshot files that include
labels.
""",
)
@click.option("--query", "query_id", required=True, type=int, help="Query id.")
@format_option
@output_option
@click.pass_obj
@handle_errors
def labels(
    state: CliState,
    query_id: int,
    fmt: str | None,
    output_file: Path | None,
) -> None:
    format_output(
        state.client.get_label_schema(query_id),
        resolved_format(state, fmt),
        output_file=output_file,
    )


def _cli_version() -> str:
    try:
        return version("agentlens-cli")
    except PackageNotFoundError:
        return __version__


__all__ = ["schema"]
