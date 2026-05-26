from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click
import uvicorn
from sqlalchemy import select
from sqlalchemy.orm import Session


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
    _configure_runtime_settings(host=host, port=port, data_dir=data_dir)

    from app.core.config import get_settings

    settings = get_settings()
    resolved_host = host or settings.host
    resolved_port = port or settings.port
    click.echo(f"AgentLens running at http://{resolved_host}:{resolved_port}")
    uvicorn.run(
        "app.main:app",
        host=resolved_host,
        port=resolved_port,
        reload=reload,
    )


@click.command(
    "cleanup",
    help="Clean expired temporary queries, annotations, and selection snapshots.",
)
@click.option("--dry-run", is_flag=True, help="Report what would be deleted without deleting it.")
def cleanup(dry_run: bool) -> None:
    _initialize_metadata()

    from app.db.session import get_session_factory
    from app.services.cleanup_service import CleanupService

    with get_session_factory()() as session:
        service = CleanupService()
        query_report = service.run(session, dry_run=dry_run)
        expired_annotations = service.delete_expired_annotations(session, dry_run=dry_run)
        expired_snapshots = service.delete_expired_selection_snapshots(session, dry_run=dry_run)

    report = query_report.model_dump()
    report.pop("cascade_analyses_deleted", None)
    click.echo(
        _json_dumps(
            {
                **report,
                "expired_annotations_deleted": expired_annotations,
                "expired_selection_snapshots_deleted": expired_snapshots,
            }
        )
    )


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
    _initialize_metadata()

    from app.db.session import get_session_factory

    with get_session_factory()() as session:
        payload = _build_config_export(
            session,
            include_encrypted_secrets=include_encrypted_secrets,
        )

    output = _json_dumps(payload)
    if output_file is None:
        click.echo(output)
        return
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(output + "\n", encoding="utf-8")
    click.echo(f"Exported AgentLens config to {output_file}")


@click.command(
    "import-config",
    help="Import a metadata configuration backup.",
)
@click.argument("input_file", required=False, type=click.Path(path_type=Path, dir_okay=False))
def import_config(input_file: Path | None) -> None:
    _ = input_file
    click.echo("import-config is planned for a future release.")


def _configure_runtime_settings(
    *,
    host: str | None,
    port: int | None,
    data_dir: Path | None,
) -> None:
    if host is not None:
        os.environ["AGENTLENS_HOST"] = host
        os.environ["AGENT_LENS_HOST"] = host
    if port is not None:
        os.environ["AGENTLENS_PORT"] = str(port)
        os.environ["AGENT_LENS_PORT"] = str(port)
    if data_dir is None:
        return
    os.environ["AGENTLENS_DATA_DIR"] = str(data_dir.expanduser().resolve())
    os.environ["AGENT_LENS_DATA_DIR"] = os.environ["AGENTLENS_DATA_DIR"]


def _initialize_metadata() -> None:
    from app.db.session import initialize_metadata_database

    initialize_metadata_database()


def _build_config_export(
    session: Session,
    *,
    include_encrypted_secrets: bool,
) -> dict[str, Any]:
    from app.models.annotation import Annotation
    from app.models.connection import Connection
    from app.models.label import LabelRecord, LabelSchema
    from app.models.misc import GlobalRenderRule
    from app.models.named_query import NamedQuery
    from app.models.view_config import ViewConfig

    return {
        "format": "agentlens-config-v1",
        "exported_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "secrets": (
            "encrypted_password_enc_base64"
            if include_encrypted_secrets
            else "omitted; plaintext secrets are never exported"
        ),
        "included_tables": [
            "connections",
            "named_queries",
            "view_configs",
            "label_schemas",
            "label_records",
            "global_render_rules",
            "annotations",
        ],
        "connections": [
            _connection_to_dict(item, include_encrypted_secrets=include_encrypted_secrets)
            for item in session.scalars(select(Connection).order_by(Connection.id))
        ],
        "named_queries": [
            _model_to_dict(
                item,
                [
                    "id",
                    "connection_id",
                    "name",
                    "description",
                    "sql_text",
                    "is_named",
                    "last_executed_at",
                    "expires_at",
                    "created_at",
                    "updated_at",
                ],
            )
            for item in session.scalars(select(NamedQuery).order_by(NamedQuery.id))
        ],
        "view_configs": [
            _model_to_dict(
                item,
                [
                    "id",
                    "query_id",
                    "field_renders",
                    "table_config",
                    "trajectory_config",
                    "trajectory_config_source",
                    "row_identity_column",
                    "created_at",
                    "updated_at",
                ],
            )
            for item in session.scalars(select(ViewConfig).order_by(ViewConfig.id))
        ],
        "label_schemas": [
            _model_to_dict(item, ["id", "query_id", "fields", "created_at", "updated_at"])
            for item in session.scalars(select(LabelSchema).order_by(LabelSchema.id))
        ],
        "label_records": [
            _model_to_dict(
                item,
                [
                    "id",
                    "query_id",
                    "row_identity",
                    "field_key",
                    "value",
                    "created_at",
                    "updated_at",
                ],
            )
            for item in session.scalars(select(LabelRecord).order_by(LabelRecord.id))
        ],
        "global_render_rules": [
            _model_to_dict(
                item,
                [
                    "id",
                    "match_pattern",
                    "match_type",
                    "render_config",
                    "priority",
                    "enabled",
                    "created_at",
                    "updated_at",
                ],
            )
            for item in session.scalars(select(GlobalRenderRule).order_by(GlobalRenderRule.id))
        ],
        "annotations": [
            _model_to_dict(
                item,
                [
                    "id",
                    "query_id",
                    "row_identity",
                    "column_key",
                    "author",
                    "color",
                    "title",
                    "text",
                    "severity",
                    "annotation_set",
                    "sql_fingerprint",
                    "schema_fingerprint",
                    "result_fingerprint",
                    "created_at",
                    "expires_at",
                ],
            )
            for item in session.scalars(select(Annotation).order_by(Annotation.id))
        ],
    }


def _connection_to_dict(
    connection: Any,
    *,
    include_encrypted_secrets: bool,
) -> dict[str, Any]:
    payload = _model_to_dict(
        connection,
        [
            "id",
            "name",
            "db_type",
            "host",
            "port",
            "database",
            "username",
            "extra_params",
            "default_timeout",
            "default_row_limit",
            "last_tested_at",
            "last_test_ok",
            "created_at",
            "updated_at",
        ],
    )
    if include_encrypted_secrets and connection.password_enc is not None:
        payload["password_enc_base64"] = base64.b64encode(connection.password_enc).decode("ascii")
    return payload


def _model_to_dict(model: Any, fields: list[str]) -> dict[str, Any]:
    return {field: _serialize_value(getattr(model, field)) for field in fields}


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        active_value = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return active_value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return value


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)


__all__ = ["cleanup", "export_config", "import_config", "run"]
