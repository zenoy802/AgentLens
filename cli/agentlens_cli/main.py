from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar, cast

import click
from agentlens_client import AgentLensSyncClient

from agentlens_cli.config import OUTPUT_FORMATS, CliConfig, ConfigError, resolve_config


@dataclass
class CliState:
    config: CliConfig
    client: AgentLensSyncClient


F = TypeVar("F", bound=Callable[..., Any])


@click.group(
    context_settings={"help_option_names": ["-h", "--help"], "max_content_width": 100},
    help="""AgentLens CLI for live data access and snapshot context export.

\b
Live access:
  agentlens data rows --query 42
Snapshot export:
  agentlens context export --query 42

Data commands read current backend state by reference on every call. Context export materializes
the current query or selection as local files for reproducible analysis.
""",
)
@click.option("--backend-url", type=str, default=None, help="AgentLens backend URL.")
@click.option("--timeout", type=int, default=None, help="HTTP timeout in seconds.")
@click.option("--author", type=str, default=None, help="Default annotation author.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(OUTPUT_FORMATS),
    default=None,
    help="Default output format.",
)
@click.pass_context
def cli(
    ctx: click.Context,
    backend_url: str | None,
    timeout: int | None,
    author: str | None,
    output_format: str | None,
) -> None:
    try:
        config = resolve_config(
            backend_url=backend_url,
            timeout=timeout,
            author=author,
            output_format=output_format,
        )
    except ConfigError as exc:
        raise click.UsageError(str(exc), ctx=ctx) from exc
    ctx.obj = CliState(
        config=config,
        client=AgentLensSyncClient(config.backend_url, timeout=config.timeout),
    )


def format_option(func: F) -> F:
    return click.option(
        "--format",
        "fmt",
        type=click.Choice(OUTPUT_FORMATS),
        default=None,
        help="Output format for this command.",
    )(func)  # type: ignore[return-value]


def output_option(func: F) -> F:
    return click.option(
        "--output",
        "output_file",
        type=click.Path(path_type=Path, dir_okay=False),
        default=None,
        help="Write data output to a file instead of stdout.",
    )(func)  # type: ignore[return-value]


def resolved_format(state: CliState, fmt: str | None) -> str:
    return fmt or state.config.output_format


from agentlens_cli.commands.annotation import annotate, annotation, highlight  # noqa: E402
from agentlens_cli.commands.connection import connection  # noqa: E402
from agentlens_cli.commands.context import context  # noqa: E402
from agentlens_cli.commands.data import data  # noqa: E402
from agentlens_cli.commands.query import query  # noqa: E402
from agentlens_cli.commands.schema import schema  # noqa: E402

cli.add_command(cast(click.Command, connection))  # type: ignore[has-type]
cli.add_command(cast(click.Command, query))  # type: ignore[has-type]
cli.add_command(cast(click.Command, data))  # type: ignore[has-type]
cli.add_command(cast(click.Command, annotation))  # type: ignore[has-type]
cli.add_command(cast(click.Command, annotate))  # type: ignore[has-type]
cli.add_command(cast(click.Command, highlight))  # type: ignore[has-type]
cli.add_command(cast(click.Command, schema))  # type: ignore[has-type]
cli.add_command(cast(click.Command, context))  # type: ignore[has-type]


def main() -> None:
    cli()


__all__ = ["CliState", "cli", "main", "resolved_format"]
