from __future__ import annotations

from pathlib import Path

import click

from agentlens_cli.errors import handle_errors
from agentlens_cli.formatters import format_output
from agentlens_cli.main import CliState, format_option, output_option, resolved_format


@click.group(
    help="""Read AgentLens data source connections.

Examples:
  agentlens connection list
  agentlens connection show local-mysql

Connection commands are live access: every call reads current backend state. Use context export
when you need a local snapshot of query data.
""",
)
def connection() -> None:
    pass


@connection.command(
    "list",
    help="""List configured data source connections.

Example:
  agentlens connection list --format json

This is live access by reference. Snapshot export is available through `agentlens context export`.
""",
)
@format_option
@output_option
@click.pass_obj
@handle_errors
def list_connections(state: CliState, fmt: str | None, output_file: Path | None) -> None:
    format_output(
        state.client.list_connections(),
        resolved_format(state, fmt),
        output_file=output_file,
    )


@connection.command(
    "show",
    help="""Show one configured data source connection by name.

Example:
  agentlens connection show local-mysql

This is live access by reference. Snapshot export is available through `agentlens context export`.
Sensitive fields are redacted.
""",
)
@click.argument("name")
@format_option
@output_option
@click.pass_obj
@handle_errors
def show_connection(
    state: CliState,
    name: str,
    fmt: str | None,
    output_file: Path | None,
) -> None:
    format_output(
        state.client.show_connection(name),
        resolved_format(state, fmt),
        output_file=output_file,
    )


__all__ = ["connection"]
