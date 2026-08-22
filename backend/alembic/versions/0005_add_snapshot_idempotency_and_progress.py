"""Add contract/snapshot idempotency and snapshot progress metadata.

Revision ID: 0005_add_snapshot_idempotency_and_progress
Revises: 0004_add_trace_contracts_and_run_snapshots
Create Date: 2026-08-22 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005_add_snapshot_idempotency_and_progress"
down_revision = "0004_add_trace_contracts_and_run_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trace_contracts", sa.Column("idempotency_key", sa.String(200), nullable=True))
    op.add_column("trace_contracts", sa.Column("request_sha256", sa.String(64), nullable=True))
    op.create_index(
        "uq_trace_contract_idempotency_key",
        "trace_contracts",
        ["idempotency_key"],
        unique=True,
    )

    op.add_column("run_snapshots", sa.Column("idempotency_key", sa.String(200), nullable=True))
    op.add_column("run_snapshots", sa.Column("request_sha256", sa.String(64), nullable=True))
    op.add_column(
        "run_snapshots",
        sa.Column(
            "progress_source_rows",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "run_snapshots",
        sa.Column("progress_runs", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "run_snapshots", sa.Column("pairing_key_field_coverage", sa.Float(), nullable=True)
    )
    op.create_index(
        "uq_run_snapshot_idempotency_key",
        "run_snapshots",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "uq_run_snapshot_building_input_fingerprint",
        "run_snapshots",
        ["input_fingerprint"],
        unique=True,
        sqlite_where=sa.text("status = 'building' AND idempotency_key IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_run_snapshot_building_input_fingerprint",
        table_name="run_snapshots",
    )
    op.drop_index("uq_run_snapshot_idempotency_key", table_name="run_snapshots")
    op.drop_column("run_snapshots", "pairing_key_field_coverage")
    op.drop_column("run_snapshots", "progress_runs")
    op.drop_column("run_snapshots", "progress_source_rows")
    op.drop_column("run_snapshots", "request_sha256")
    op.drop_column("run_snapshots", "idempotency_key")

    op.drop_index("uq_trace_contract_idempotency_key", table_name="trace_contracts")
    op.drop_column("trace_contracts", "request_sha256")
    op.drop_column("trace_contracts", "idempotency_key")
