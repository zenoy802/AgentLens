from __future__ import annotations

import re
from pathlib import Path

import click

from agentlens_cli.errors import AgentLensCliError, handle_errors
from agentlens_cli.formatters import format_output
from agentlens_cli.main import CliState, format_option, output_option, resolved_format

_AUTHOR_PATTERN = re.compile(r"^[a-zA-Z0-9_:.-]+$")
_COLORS = ("red", "yellow", "green", "blue", "gray")
_SEVERITIES = ("info", "warning", "error")


@click.command(
    help="""Create one visual annotation.

Example:
  agentlens annotate --query 42 --row abc --color red --text "Failure analysis"

This writes back to AgentLens through the backend. Use `agentlens data annotations` for live
reads and `agentlens context export` for snapshot read by value.
""",
)
@click.option("--query", "query_id", required=True, type=int, help="Query id.")
@click.option("--row", "row_identity", required=True, help="Row identity.")
@click.option("--column", "column_key", default=None, help="Optional column key.")
@click.option("--color", required=True, type=click.Choice(_COLORS), help="Annotation color.")
@click.option("--title", default=None, help="Short annotation title.")
@click.option("--text", default=None, help="Annotation text.")
@click.option("--severity", default=None, type=click.Choice(_SEVERITIES))
@click.option("--set", "annotation_set", default=None, help="Annotation set name.")
@click.option("--author", default=None, help="Annotation author.")
@format_option
@output_option
@click.pass_obj
@handle_errors
def annotate(
    state: CliState,
    query_id: int,
    row_identity: str,
    column_key: str | None,
    color: str,
    title: str | None,
    text: str | None,
    severity: str | None,
    annotation_set: str | None,
    author: str | None,
    fmt: str | None,
    output_file: Path | None,
) -> None:
    resolved_author = _author(state, author)
    payload = _clean_payload(
        {
            "row_identity": row_identity,
            "column_key": column_key,
            "author": resolved_author,
            "color": color,
            "title": title,
            "text": text,
            "severity": severity,
            "annotation_set": annotation_set,
        }
    )
    format_output(
        state.client.create_annotation(query_id, payload),
        resolved_format(state, fmt),
        output_file=output_file,
    )


@click.command(
    help="""Highlight multiple rows with one batch annotation request.

Example:
  agentlens highlight --query 42 --rows a,b,c --color yellow --note "Inspect these"

This writes back to AgentLens through the backend batch endpoint. Use `agentlens data rows` for
live reads and `agentlens context export` for snapshot read by value.
""",
)
@click.option("--query", "query_id", required=True, type=int, help="Query id.")
@click.option("--rows", "row_identities", required=True, help="Comma-separated row identities.")
@click.option("--color", required=True, type=click.Choice(_COLORS), help="Annotation color.")
@click.option("--note", default=None, help="Annotation text for each highlighted row.")
@click.option("--author", default=None, help="Annotation author.")
@format_option
@output_option
@click.pass_obj
@handle_errors
def highlight(
    state: CliState,
    query_id: int,
    row_identities: str,
    color: str,
    note: str | None,
    author: str | None,
    fmt: str | None,
    output_file: Path | None,
) -> None:
    rows = [item.strip() for item in row_identities.split(",") if item.strip()]
    if not rows:
        raise click.UsageError("--rows must contain at least one row identity.")
    resolved_author = _author(state, author)
    annotations = [
        _clean_payload(
            {
                "row_identity": row_identity,
                "author": resolved_author,
                "color": color,
                "title": "Highlight",
                "text": note,
            }
        )
        for row_identity in rows
    ]
    format_output(
        state.client.create_annotations_batch(query_id, annotations),
        resolved_format(state, fmt),
        output_file=output_file,
    )


@click.group(
    help="""Read or clear visual annotations.

Examples:
  agentlens annotation list --query 42
  agentlens annotation clear --query 42 --author-prefix agent:

List is live access by reference. Clear writes back to AgentLens. Use `agentlens context export`
for snapshot read by value.
""",
)
def annotation() -> None:
    pass


@annotation.command(
    "list",
    help="""List annotations for a query.

Example:
  agentlens annotation list --query 42 --author agent:claude-code

This is live access by reference. Use `agentlens context export` for local snapshot files.
""",
)
@click.option("--query", "query_id", required=True, type=int, help="Query id.")
@click.option("--author", default=None, help="Exact author filter.")
@click.option("--author-prefix", default=None, help="Author prefix filter.")
@click.option("--color", default=None, type=click.Choice(_COLORS), help="Color filter.")
@format_option
@output_option
@click.pass_obj
@handle_errors
def list_annotations(
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


@annotation.command(
    "clear",
    help="""Clear annotations matching filters.

Example:
  agentlens annotation clear --query 42 --author-prefix agent:

This writes back to AgentLens. At least one filter is required. Use `agentlens data annotations`
for live reads and `agentlens context export` for snapshot read by value.
""",
)
@click.option("--query", "query_id", required=True, type=int, help="Query id.")
@click.option("--author", default=None, help="Exact author filter.")
@click.option("--author-prefix", default=None, help="Author prefix filter.")
@click.option("--color", default=None, type=click.Choice(_COLORS), help="Color filter.")
@click.option("--set", "annotation_set", default=None, help="Annotation set filter.")
@format_option
@output_option
@click.pass_obj
@handle_errors
def clear_annotations(
    state: CliState,
    query_id: int,
    author: str | None,
    author_prefix: str | None,
    color: str | None,
    annotation_set: str | None,
    fmt: str | None,
    output_file: Path | None,
) -> None:
    filters = {
        "author": author,
        "author_prefix": author_prefix,
        "color": color,
        "annotation_set": annotation_set,
    }
    if not any(value is not None and value != "" for value in filters.values()):
        raise AgentLensCliError(
            "Refusing to clear annotations without at least one filter.",
            exit_code=4,
        )
    format_output(
        state.client.clear_annotations(query_id, **filters),
        resolved_format(state, fmt),
        output_file=output_file,
    )


def _author(state: CliState, author: str | None) -> str:
    resolved = author or state.config.author
    if not _AUTHOR_PATTERN.fullmatch(resolved):
        raise click.UsageError("Author must match ^[a-zA-Z0-9_:.-]+$.")
    return resolved


def _clean_payload(payload: dict[str, object | None]) -> dict[str, object]:
    return {key: value for key, value in payload.items() if value is not None}


__all__ = ["annotate", "annotation", "highlight"]
