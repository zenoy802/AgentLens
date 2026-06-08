from __future__ import annotations

from pathlib import Path
from typing import cast

import click
from agentlens_client.context_export import export_context
from agentlens_client.types import ContextScope, OutputTarget

from agentlens_cli.errors import handle_errors
from agentlens_cli.formatters import format_output
from agentlens_cli.main import CliState, format_option, output_option, resolved_format


@click.group(
    help="""Materialize AgentLens context as local files.

Example:
  agentlens context export --query 42

Context export is snapshot read by value: it writes the current query or selection context to
files. Data commands are live access by reference and do not create snapshots.
""",
)
def context() -> None:
    pass


@context.command(
    "export",
    help="""Export query context to a static local directory.

Examples:
  agentlens context export --query 42
  agentlens context export --query 42 --selection sel_abc123
  agentlens context export --query 42 --target claude-code

This is snapshot read by value. It creates AGENTLENS_CONTEXT.md and data files without calling an
LLM. Use `agentlens data rows` for live access by reference.
""",
)
@click.option("--query", "query_id", required=True, type=int, help="Query id.")
@click.option("--selection", "selection_id", default=None, help="Selection snapshot id.")
@click.option("--scope", type=click.Choice(("all", "selection")), default=None)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=None,
    help="Output directory. Defaults to ~/.agentlens/contexts/query_<id>_<timestamp>/.",
)
@click.option(
    "--target",
    type=click.Choice(("generic", "claude-code")),
    default="generic",
    show_default=True,
)
@format_option
@output_option
@click.pass_obj
@handle_errors
def export(
    state: CliState,
    query_id: int,
    selection_id: str | None,
    scope: str | None,
    output_dir: Path | None,
    target: str,
    fmt: str | None,
    output_file: Path | None,
) -> None:
    if scope == "selection" and selection_id is None:
        raise click.UsageError("--selection is required when --scope selection is used.")
    result = export_context(
        client=state.client,
        query_id=query_id,
        selection_id=selection_id,
        scope=cast(ContextScope | None, scope),
        output_dir=output_dir,
        target=cast(OutputTarget, target),
        backend_url=state.config.backend_url,
    )
    format_output(result, resolved_format(state, fmt), output_file=output_file)


__all__ = ["context"]
