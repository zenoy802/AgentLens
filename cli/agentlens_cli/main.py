from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, TypeVar, cast

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


def _server_command_error(command_name: str, exc: ModuleNotFoundError) -> NoReturn:
    missing_name = exc.name or str(exc)
    raise click.ClickException(
        f"The 'agentlens {command_name.replace('_', '-')}' command requires the unified "
        "agentlens package with backend server dependencies. Install the unified package "
        "from the AgentLens repository, for example "
        "'git clone --branch v0.1.0 --depth 1 "
        "https://github.com/zenoy802/AgentLens.git && cd AgentLens && "
        "pipx run --spec build pyproject-build && "
        "pipx install dist/agentlens-0.1.0-py3-none-any.whl', "
        "or run it from an AgentLens server environment. "
        f"Missing dependency: {missing_name}."
    ) from exc


def _server_command(command_name: str) -> click.Command:
    try:
        from agentlens_cli.commands import server as server_commands  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        _server_command_error(command_name, exc)
    return cast(click.Command, getattr(server_commands, command_name))


def _invoke_server_command(command_name: str, **kwargs: Any) -> None:
    try:
        click.get_current_context().invoke(_server_command(command_name), **kwargs)
    except ModuleNotFoundError as exc:
        _server_command_error(command_name, exc)


@click.command("run", help="Run the AgentLens web app and API server.")
@click.option("--host", default=None, help="Host to bind. Defaults to AgentLens settings.")
@click.option(
    "--port",
    default=None,
    type=int,
    help="Port to bind. Defaults to AgentLens settings.",
)
@click.option("--reload", is_flag=True, help="Enable auto-reload for local development.")
@click.option(
    "--data-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=None,
    help="Directory for metadata, logs, and context files.",
)
def run(host: str | None, port: int | None, reload: bool, data_dir: Path | None) -> None:
    _invoke_server_command(
        "run",
        host=host,
        port=port,
        reload=reload,
        data_dir=data_dir,
    )


@click.command(
    "cleanup",
    help="Clean expired temporary queries, annotations, and selection snapshots.",
)
@click.option("--dry-run", is_flag=True, help="Report what would be deleted without deleting it.")
def cleanup(dry_run: bool) -> None:
    _invoke_server_command("cleanup", dry_run=dry_run)


@click.command(
    "export-config",
    help="Export metadata configuration without plaintext secrets.",
)
@click.option(
    "-o",
    "--output",
    "output_file",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Write backup JSON to a file instead of stdout.",
)
@click.option(
    "--include-encrypted-secrets",
    is_flag=True,
    help="Include encrypted password bytes. Plaintext secrets are never exported.",
)
def export_config(output_file: Path | None, include_encrypted_secrets: bool) -> None:
    _invoke_server_command(
        "export_config",
        output_file=output_file,
        include_encrypted_secrets=include_encrypted_secrets,
    )


@click.command(
    "import-config",
    help="Import a metadata configuration backup.",
)
@click.argument("input_file", required=False, type=click.Path(path_type=Path, dir_okay=False))
def import_config(input_file: Path | None) -> None:
    _invoke_server_command("import_config", input_file=input_file)


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
cli.add_command(cast(click.Command, run))  # type: ignore[has-type]
cli.add_command(cast(click.Command, cleanup))  # type: ignore[has-type]
cli.add_command(cast(click.Command, export_config))  # type: ignore[has-type]
cli.add_command(cast(click.Command, import_config))  # type: ignore[has-type]


def main() -> None:
    cli()


__all__ = ["CliState", "cli", "main", "resolved_format"]
