"""Reset unreliable legacy trajectory config sources.

Revision ID: 0004_reset_legacy_trajectory_config_source
Revises: 0003_backfill_trajectory_config_source
Create Date: 2026-05-08 00:00:02
"""

from __future__ import annotations

from alembic import op

revision = "0004_reset_legacy_trajectory_config_source"
down_revision = "0003_backfill_trajectory_config_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The original 0003 revision guessed source from is_named, which cannot
    # distinguish user edits from auto-saved suggestions. Reset non-null configs
    # to legacy/unknown so the frontend can protect valid configs and replace
    # stale configs based on the current result columns.
    op.execute(
        """
        UPDATE view_configs
        SET trajectory_config_source = NULL
        WHERE trajectory_config IS NOT NULL
          AND trajectory_config_source IN ('manual', 'suggested')
        """
    )


def downgrade() -> None:
    return None
