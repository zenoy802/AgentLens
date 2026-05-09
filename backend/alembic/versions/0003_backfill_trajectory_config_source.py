"""Preserve legacy trajectory config source metadata.

Revision ID: 0003_backfill_trajectory_config_source
Revises: 0002_view_config_trajectory_source
Create Date: 2026-05-08 00:00:01
"""

from __future__ import annotations

revision = "0003_backfill_trajectory_config_source"
down_revision = "0002_view_config_trajectory_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Legacy rows cannot reliably distinguish manually saved configs from
    # auto-saved suggestions, so keep NULL as an explicit legacy/unknown source.
    return None


def downgrade() -> None:
    return None
