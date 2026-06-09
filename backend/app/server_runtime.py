from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import uvicorn
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import dispose_engine, get_session_factory, initialize_metadata_database
from app.models.annotation import Annotation
from app.models.connection import Connection
from app.models.label import LabelRecord, LabelSchema
from app.models.misc import GlobalRenderRule
from app.models.named_query import NamedQuery
from app.models.view_config import ViewConfig
from app.services.cleanup_service import CleanupService


def run_server(
    host: str | None = None,
    port: int | None = None,
    *,
    reload: bool = False,
    data_dir: Path | None = None,
    emit: Callable[[str], None] | None = None,
) -> None:
    _configure_runtime_settings(host=host, port=port, data_dir=data_dir)

    settings = get_settings()
    resolved_host = host or settings.host
    resolved_port = port or settings.port
    active_emit = emit or print
    active_emit(f"AgentLens running at http://{resolved_host}:{resolved_port}")
    uvicorn.run(
        "app.main:app",
        host=resolved_host,
        port=resolved_port,
        reload=reload,
    )


def cleanup_metadata(dry_run: bool = False) -> dict[str, Any]:
    _initialize_metadata()

    with get_session_factory()() as session:
        service = CleanupService()
        query_report = service.run(session, dry_run=dry_run)
        expired_annotations = service.delete_expired_annotations(session, dry_run=dry_run)
        expired_snapshots = service.delete_expired_selection_snapshots(session, dry_run=dry_run)

    return {
        **query_report.model_dump(),
        "expired_annotations_deleted": expired_annotations,
        "expired_selection_snapshots_deleted": expired_snapshots,
    }


def export_config_payload(include_encrypted_secrets: bool) -> dict[str, Any]:
    _initialize_metadata()

    with get_session_factory()() as session:
        return _build_config_export(
            session,
            include_encrypted_secrets=include_encrypted_secrets,
        )


def write_json_payload(payload: Any, output_file: Path | None) -> str | None:
    output = json_dumps(payload)
    if output_file is None:
        return output
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(output + "\n", encoding="utf-8")
    return None


def import_config_notice() -> str:
    return "import-config is planned for a future release."


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)


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
    if data_dir is not None:
        resolved_data_dir = str(data_dir.expanduser().resolve())
        os.environ["AGENTLENS_DATA_DIR"] = resolved_data_dir
        os.environ["AGENT_LENS_DATA_DIR"] = resolved_data_dir

    get_settings.cache_clear()
    dispose_engine()


def _initialize_metadata() -> None:
    initialize_metadata_database()


def _build_config_export(
    session: Session,
    *,
    include_encrypted_secrets: bool,
) -> dict[str, Any]:
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
