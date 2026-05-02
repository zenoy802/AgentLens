"""Initial metadata schema.

Revision ID: 0001_initial_metadata
Revises:
Create Date: 2026-04-18 21:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_initial_metadata"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("db_type", sa.String(length=20), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("database", sa.String(length=200), nullable=False),
        sa.Column("username", sa.String(length=200), nullable=True),
        sa.Column("password_enc", sa.LargeBinary(), nullable=True),
        sa.Column("extra_params", sa.Text(), nullable=True),
        sa.Column(
            "default_timeout",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column(
            "default_row_limit",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("10000"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("last_tested_at", sa.DateTime(), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.UniqueConstraint("name"),
    )
    op.create_index("idx_connections_name", "connections", ["name"], unique=False)

    op.create_table(
        "llm_providers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("api_key_enc", sa.LargeBinary(), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("extra_headers", sa.Text(), nullable=True),
        sa.Column(
            "default_temperature",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.7"),
        ),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        "idx_llm_default",
        "llm_providers",
        ["is_default"],
        unique=True,
        sqlite_where=sa.text("is_default = 1"),
    )

    op.create_table(
        "global_render_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_pattern", sa.String(length=200), nullable=False),
        sa.Column(
            "match_type",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'exact'"),
        ),
        sa.Column("render_config", sa.Text(), nullable=False),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "idx_grr_enabled_priority",
        "global_render_rules",
        ["enabled", "priority"],
        unique=False,
    )

    op.create_table(
        "named_queries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sql_text", sa.Text(), nullable=False),
        sa.Column(
            "is_named",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("last_executed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("connection_id", "name"),
    )
    op.create_index("idx_nq_connection", "named_queries", ["connection_id"], unique=False)
    op.create_index(
        "idx_nq_expires",
        "named_queries",
        ["expires_at"],
        unique=False,
        sqlite_where=sa.text("expires_at IS NOT NULL"),
    )
    op.create_index("idx_nq_is_named", "named_queries", ["is_named"], unique=False)

    op.create_table(
        "query_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("query_id", sa.Integer(), nullable=True),
        sa.Column("sql_text", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "executed_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["query_id"], ["named_queries.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_qh_connection", "query_history", ["connection_id"], unique=False)
    op.create_index("idx_qh_executed", "query_history", ["executed_at"], unique=False)

    op.create_table(
        "view_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("query_id", sa.Integer(), nullable=False),
        sa.Column(
            "field_renders",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "table_config",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("trajectory_config", sa.Text(), nullable=True),
        sa.Column("row_identity_column", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["query_id"], ["named_queries.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("query_id"),
    )

    op.create_table(
        "label_schemas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("query_id", sa.Integer(), nullable=False),
        sa.Column(
            "fields",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["query_id"], ["named_queries.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("query_id"),
    )

    op.create_table(
        "label_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("query_id", sa.Integer(), nullable=False),
        sa.Column("row_identity", sa.String(length=512), nullable=False),
        sa.Column("field_key", sa.String(length=200), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["query_id"], ["named_queries.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("query_id", "row_identity", "field_key"),
    )
    op.create_index(
        "idx_lr_query_field",
        "label_records",
        ["query_id", "field_key"],
        unique=False,
    )
    op.create_index(
        "idx_lr_query_row",
        "label_records",
        ["query_id", "row_identity"],
        unique=False,
    )

    op.create_table(
        "llm_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("query_id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=True),
        sa.Column("selection", sa.Text(), nullable=False),
        sa.Column("structure_format", sa.String(length=50), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("structured_input", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.Column("token_usage", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'running'"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["provider_id"], ["llm_providers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["query_id"], ["named_queries.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_la_created", "llm_analyses", ["created_at"], unique=False)
    op.create_index("idx_la_query", "llm_analyses", ["query_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_la_query", table_name="llm_analyses")
    op.drop_index("idx_la_created", table_name="llm_analyses")
    op.drop_table("llm_analyses")
    op.drop_index("idx_lr_query_row", table_name="label_records")
    op.drop_index("idx_lr_query_field", table_name="label_records")
    op.drop_table("label_records")
    op.drop_table("label_schemas")
    op.drop_table("view_configs")
    op.drop_index("idx_qh_executed", table_name="query_history")
    op.drop_index("idx_qh_connection", table_name="query_history")
    op.drop_table("query_history")
    op.drop_index("idx_nq_is_named", table_name="named_queries")
    op.drop_index("idx_nq_expires", table_name="named_queries")
    op.drop_index("idx_nq_connection", table_name="named_queries")
    op.drop_table("named_queries")
    op.drop_index("idx_grr_enabled_priority", table_name="global_render_rules")
    op.drop_table("global_render_rules")
    op.drop_index("idx_llm_default", table_name="llm_providers")
    op.drop_table("llm_providers")
    op.drop_index("idx_connections_name", table_name="connections")
    op.drop_table("connections")
