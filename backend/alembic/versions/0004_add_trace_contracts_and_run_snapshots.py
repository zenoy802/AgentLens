"""Add trace contracts and run snapshot metadata.

Revision ID: 0004_add_trace_contracts_and_run_snapshots
Revises: 0003_add_annotations_and_selection_snapshots
Create Date: 2026-08-22 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_add_trace_contracts_and_run_snapshots"
down_revision = "0003_add_annotations_and_selection_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trace_contracts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("named_query_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("definition_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("version >= 1", name="ck_trace_contract_version_positive"),
        sa.ForeignKeyConstraint(["named_query_id"], ["named_queries.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "name",
            "named_query_id",
            "version",
            name="uq_trace_contract_name_query_version",
        ),
    )
    op.create_index("ix_trace_contract_definition_sha256", "trace_contracts", ["definition_sha256"])
    op.create_index(
        "ix_trace_contract_query_created", "trace_contracts", ["named_query_id", "created_at"]
    )

    op.create_table(
        "run_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("trace_contract_id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("named_query_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("artifact_path", sa.String(length=1024), nullable=True),
        sa.Column("artifact_size_bytes", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("source_row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("build_policy", sa.JSON(), nullable=False),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('building','ready','failed','corrupted','deleted')",
            name="ck_run_snapshot_status",
        ),
        sa.CheckConstraint(
            "artifact_size_bytes >= 0 AND source_row_count >= 0 AND run_count >= 0",
            name="ck_run_snapshot_non_negative_counts",
        ),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["named_query_id"], ["named_queries.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["trace_contract_id"], ["trace_contracts.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_run_snapshot_status_created", "run_snapshots", ["status", "created_at"])
    op.create_index(
        "ix_run_snapshot_contract_created",
        "run_snapshots",
        ["trace_contract_id", "created_at"],
    )
    op.create_index("ix_run_snapshot_input_fingerprint", "run_snapshots", ["input_fingerprint"])
    op.create_index("ix_run_snapshot_content_sha256", "run_snapshots", ["content_sha256"])
    op.create_index("ix_run_snapshot_artifact_sha256", "run_snapshots", ["artifact_sha256"])


def downgrade() -> None:
    op.drop_index("ix_run_snapshot_artifact_sha256", table_name="run_snapshots")
    op.drop_index("ix_run_snapshot_content_sha256", table_name="run_snapshots")
    op.drop_index("ix_run_snapshot_input_fingerprint", table_name="run_snapshots")
    op.drop_index("ix_run_snapshot_contract_created", table_name="run_snapshots")
    op.drop_index("ix_run_snapshot_status_created", table_name="run_snapshots")
    op.drop_table("run_snapshots")

    op.drop_index("ix_trace_contract_query_created", table_name="trace_contracts")
    op.drop_index("ix_trace_contract_definition_sha256", table_name="trace_contracts")
    op.drop_table("trace_contracts")
