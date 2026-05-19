"""Add annotations and selection snapshots.

Revision ID: 0003_add_annotations_and_selection_snapshots
Revises: 0002_view_config_trajectory_source
Create Date: 2026-05-18 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_add_annotations_and_selection_snapshots"
down_revision = "0002_view_config_trajectory_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "annotations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("query_id", sa.Integer(), nullable=False),
        sa.Column("row_identity", sa.String(length=256), nullable=False),
        sa.Column("column_key", sa.String(length=128), nullable=True),
        sa.Column("author", sa.String(length=64), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=True),
        sa.Column("annotation_set", sa.String(length=128), nullable=True),
        sa.Column("sql_fingerprint", sa.String(length=80), nullable=True),
        sa.Column("schema_fingerprint", sa.String(length=80), nullable=True),
        sa.Column("result_fingerprint", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "color IN ('red','yellow','green','blue','gray')",
            name="ck_annotations_color",
        ),
        sa.CheckConstraint(
            "severity IS NULL OR severity IN ('info','warning','error')",
            name="ck_annotations_severity",
        ),
        sa.ForeignKeyConstraint(["query_id"], ["named_queries.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_annotations_annotation_set", "annotations", ["annotation_set"])
    op.create_index("ix_annotations_author", "annotations", ["author"])
    op.create_index("ix_annotations_created_at", "annotations", ["created_at"])
    op.create_index("ix_annotations_expires_at", "annotations", ["expires_at"])
    op.create_index("ix_annotations_query_author", "annotations", ["query_id", "author"])
    op.create_index("ix_annotations_query_id", "annotations", ["query_id"])
    op.create_index("ix_annotations_query_row", "annotations", ["query_id", "row_identity"])
    op.create_index("ix_annotations_row_identity", "annotations", ["row_identity"])

    op.create_table(
        "selection_snapshots",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("query_id", sa.Integer(), nullable=False),
        sa.Column("row_identities_json", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["query_id"], ["named_queries.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_selection_snapshots_created_at", "selection_snapshots", ["created_at"])
    op.create_index("ix_selection_snapshots_expires_at", "selection_snapshots", ["expires_at"])
    op.create_index("ix_selection_snapshots_query", "selection_snapshots", ["query_id"])
    op.create_index("ix_selection_snapshots_query_id", "selection_snapshots", ["query_id"])


def downgrade() -> None:
    op.drop_index("ix_selection_snapshots_query_id", table_name="selection_snapshots")
    op.drop_index("ix_selection_snapshots_query", table_name="selection_snapshots")
    op.drop_index("ix_selection_snapshots_expires_at", table_name="selection_snapshots")
    op.drop_index("ix_selection_snapshots_created_at", table_name="selection_snapshots")
    op.drop_table("selection_snapshots")

    op.drop_index("ix_annotations_row_identity", table_name="annotations")
    op.drop_index("ix_annotations_query_row", table_name="annotations")
    op.drop_index("ix_annotations_query_id", table_name="annotations")
    op.drop_index("ix_annotations_query_author", table_name="annotations")
    op.drop_index("ix_annotations_expires_at", table_name="annotations")
    op.drop_index("ix_annotations_created_at", table_name="annotations")
    op.drop_index("ix_annotations_author", table_name="annotations")
    op.drop_index("ix_annotations_annotation_set", table_name="annotations")
    op.drop_table("annotations")
