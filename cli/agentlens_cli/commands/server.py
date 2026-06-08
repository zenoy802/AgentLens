from __future__ import annotations

from pathlib import Path

import click


@click.command(
    "run",
    help="Run the AgentLens web app and API server.",
)
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
    from app.server_runtime import run_server

    run_server(
        host=host,
        port=port,
        reload=reload,
        data_dir=data_dir,
        emit=click.echo,
    )


@click.command(
    "cleanup",
    help="Clean expired temporary queries, annotations, and selection snapshots.",
)
@click.option("--dry-run", is_flag=True, help="Report what would be deleted without deleting it.")
def cleanup(dry_run: bool) -> None:
    from app.server_runtime import cleanup_metadata, json_dumps

    click.echo(json_dumps(cleanup_metadata(dry_run=dry_run)))


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
    from app.server_runtime import export_config_payload, write_json_payload

    payload = export_config_payload(include_encrypted_secrets=include_encrypted_secrets)
    output = write_json_payload(payload, output_file)
    if output is not None:
        click.echo(output)
        return
    if output_file is not None:
        click.echo(f"Exported AgentLens config to {output_file}")


@click.command(
    "import-config",
    help="Import a metadata configuration backup.",
)
@click.argument("input_file", required=False, type=click.Path(path_type=Path, dir_okay=False))
def import_config(input_file: Path | None) -> None:
    _ = input_file
    from app.server_runtime import import_config_notice

    click.echo(import_config_notice())


__all__ = ["cleanup", "export_config", "import_config", "run"]
