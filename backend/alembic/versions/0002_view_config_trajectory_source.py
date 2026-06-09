"""Add trajectory config source metadata.

Revision ID: 0002_view_config_trajectory_source
Revises: 0001_initial_metadata
Create Date: 2026-05-08 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_view_config_trajectory_source"
down_revision = "0001_initial_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "view_configs",
        sa.Column("trajectory_config_source", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("view_configs", "trajectory_config_source")
