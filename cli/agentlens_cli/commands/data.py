from __future__ import annotations

from pathlib import Path

import click

from agentlens_cli.errors import handle_errors
from agentlens_cli.formatters import format_output
from agentlens_cli.main import CliState, format_option, output_option, resolved_format


@click.group(
    help="""Live data access commands.

Examples:
  agentlens data rows --query 42
  agentlens data annotations --query 42 --author-prefix agent:

Data commands are live access: each call reads current backend state by reference. Use
`agentlens context export` for snapshot read by value when you need local files.
""",
)
def data() -> None:
    pass


@data.command(
    "rows",
    help="""Read query rows from the backend.

Example:
  agentlens data rows --query 42 --limit 100 --format jsonl

This is live access by reference. JSON output is an envelope; JSONL outputs only rows. Use
`agentlens context export` for a snapshot file set.
""",
)
@click.option("--query", "query_id", required=True, type=int, help="Query id.")
@click.option("--limit", type=click.IntRange(min=1, max=100000), default=100, show_default=True)
@click.option("--offset", type=click.IntRange(min=0), default=0, show_default=True)
@click.option(
    "--metadata-output",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="For JSONL rows, write envelope metadata to this file.",
)
@format_option
@output_option
@click.pass_obj
@handle_errors
def rows(
    state: CliState,
    query_id: int,
    limit: int,
    offset: int,
    metadata_output: Path | None,
    fmt: str | None,
    output_file: Path | None,
) -> None:
    format_output(
        state.client.get_rows(query_id, limit=limit, offset=offset),
        resolved_format(state, fmt),
        output_file=output_file,
        metadata_output_file=metadata_output,
    )


@data.command(
    "trajectories",
    help="""Read trajectory aggregates from the backend.

Example:
  agentlens data trajectories --query 42 --session session-1

This is live access by reference. Use `agentlens context export` when you need local snapshot
files for offline analysis.
""",
)
@click.option("--query", "query_id", required=True, type=int, help="Query id.")
@click.option("--session", "session_id", default=None, help="Filter by trajectory group key.")
@format_option
@output_option
@click.pass_obj
@handle_errors
def trajectories(
    state: CliState,
    query_id: int,
    session_id: str | None,
    fmt: str | None,
    output_file: Path | None,
) -> None:
    format_output(
        state.client.get_trajectories(query_id, session_id=session_id),
        resolved_format(state, fmt),
        output_file=output_file,
    )


@data.command(
    "labels",
    help="""Read labels for a query.

Example:
  agentlens data labels --query 42 --format json

This is live access by reference. Use `agentlens context export` for snapshot files that include
labels alongside rows.
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
        state.client.get_labels(query_id),
        resolved_format(state, fmt),
        output_file=output_file,
    )


@data.command(
    "annotations",
    help="""Read visual annotations for a query.

Example:
  agentlens data annotations --query 42 --author-prefix agent:

This is live access by reference. Use `agentlens context export` for snapshot files that include
annotations alongside rows.
""",
)
@click.option("--query", "query_id", required=True, type=int, help="Query id.")
@click.option("--author", default=None, help="Exact author filter.")
@click.option("--author-prefix", default=None, help="Author prefix filter.")
@click.option("--color", default=None, help="Annotation color filter.")
@format_option
@output_option
@click.pass_obj
@handle_errors
def data_annotations(
    state: CliState,
    query_id: int,
    author: str | None,
    author_prefix: str | None,
    color: str | None,
    fmt: str | None,
    output_file: Path | None,
) -> None:
    format_output(
        state.client.get_annotations(
            query_id,
            author=author,
            author_prefix=author_prefix,
            color=color,
        ),
        resolved_format(state, fmt),
        output_file=output_file,
    )


@data.command(
    "selection",
    help="""Read a selection snapshot by id.

Example:
  agentlens data selection --selection sel_abc123

This is live access by reference to the current backend snapshot record. Use
`agentlens context export --scope selection` to materialize selected rows as files.
""",
)
@click.option("--selection", "selection_id", required=True, help="Selection snapshot id.")
@format_option
@output_option
@click.pass_obj
@handle_errors
def selection(
    state: CliState,
    selection_id: str,
    fmt: str | None,
    output_file: Path | None,
) -> None:
    format_output(
        state.client.get_selection(selection_id),
        resolved_format(state, fmt),
        output_file=output_file,
    )


__all__ = ["data"]
