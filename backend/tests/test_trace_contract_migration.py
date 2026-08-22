from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.db.session import get_engine

_PREVIOUS_REVISION = "0003_add_annotations_and_selection_snapshots"
_SHA256_HEX_LENGTH = 64


def _migration_config(database_path: Path) -> Config:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    return config


def _table_names(database_path: Path) -> set[str]:
    engine = sa.create_engine(f"sqlite:///{database_path}")
    try:
        return set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_migration_upgrades_empty_database_and_downgrades_cleanly(tmp_path: Path) -> None:
    database_path = tmp_path / "empty.sqlite3"
    config = _migration_config(database_path)

    command.upgrade(config, "head")
    upgraded_tables = _table_names(database_path)
    assert {"trace_contracts", "run_snapshots"} <= upgraded_tables
    engine = sa.create_engine(f"sqlite:///{database_path}")
    try:
        inspector = sa.inspect(engine)
        snapshot_columns = {
            column["name"]: column["type"] for column in inspector.get_columns("run_snapshots")
        }
        assert isinstance(snapshot_columns["id"], sa.String)
        assert isinstance(snapshot_columns["trace_contract_id"], sa.String)
        assert isinstance(snapshot_columns["connection_id"], sa.Integer)
        assert isinstance(snapshot_columns["named_query_id"], sa.Integer)
        assert isinstance(snapshot_columns["artifact_sha256"], sa.String)
        assert snapshot_columns["artifact_sha256"].length == _SHA256_HEX_LENGTH
        snapshot_indexes = {index["name"] for index in inspector.get_indexes("run_snapshots")}
        assert "ix_run_snapshot_artifact_sha256" in snapshot_indexes
    finally:
        engine.dispose()

    command.downgrade(config, _PREVIOUS_REVISION)
    downgraded_tables = _table_names(database_path)
    assert "trace_contracts" not in downgraded_tables
    assert "run_snapshots" not in downgraded_tables
    assert {"connections", "named_queries", "annotations"} <= downgraded_tables


def test_migration_upgrades_current_head_without_rewriting_legacy_rows(tmp_path: Path) -> None:
    database_path = tmp_path / "existing.sqlite3"
    config = _migration_config(database_path)
    command.upgrade(config, _PREVIOUS_REVISION)
    engine = sa.create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO connections (
                    id, name, db_type, database, default_timeout, default_row_limit
                ) VALUES (1, 'existing', 'mysql', 'evals', 30, 10000)
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO named_queries (
                    id, connection_id, name, sql_text, is_named
                ) VALUES (42, 1, 'existing-query', 'SELECT 1', 1)
                """
            )
        )
    engine.dispose()

    command.upgrade(config, "head")
    upgraded_engine = sa.create_engine(f"sqlite:///{database_path}")
    try:
        with upgraded_engine.connect() as connection:
            name = connection.scalar(sa.text("SELECT name FROM named_queries WHERE id = 42"))
            revision = connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
        assert name == "existing-query"
        assert revision == "0004_add_trace_contracts_and_run_snapshots"
    finally:
        upgraded_engine.dispose()


def test_new_foreign_keys_and_checks_are_enforced(tmp_path: Path) -> None:
    database_path = tmp_path / "constraints.sqlite3"
    config = _migration_config(database_path)
    command.upgrade(config, "head")
    engine = sa.create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        connection.execute(sa.text("PRAGMA foreign_keys=ON"))
        connection.commit()
        with connection.begin():
            connection.execute(
                sa.text(
                    """
                    INSERT INTO connections (
                        id, name, db_type, database, default_timeout, default_row_limit
                    ) VALUES (1, 'constraint-source', 'mysql', 'evals', 30, 10000)
                    """
                )
            )
            connection.execute(
                sa.text(
                    """
                    INSERT INTO named_queries (
                        id, connection_id, name, sql_text, is_named
                    ) VALUES (1, 1, 'constraint-query', 'SELECT 1', 1)
                    """
                )
            )
            connection.execute(
                sa.text(
                    """
                    INSERT INTO trace_contracts (
                        id, name, named_query_id, version, definition, definition_sha256,
                        created_at, updated_at
                    ) VALUES (
                        '00000000-0000-0000-0000-000000000001', 'contract', 1, 1, '{}',
                        :hash, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"hash": "a" * 64},
            )
            connection.execute(
                sa.text(
                    """
                    INSERT INTO run_snapshots (
                        id, name, trace_contract_id, connection_id, named_query_id, status,
                        input_fingerprint, build_policy, created_at
                    ) VALUES (
                        '00000000-0000-0000-0000-000000000002', 'snapshot',
                        '00000000-0000-0000-0000-000000000001', 1, 1, 'building',
                        :hash, '{}', CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"hash": "b" * 64},
            )
        with pytest.raises(IntegrityError), connection.begin():
            connection.execute(
                sa.text(
                    "DELETE FROM trace_contracts WHERE id = '00000000-0000-0000-0000-000000000001'"
                )
            )
        with pytest.raises(IntegrityError), connection.begin():
            connection.execute(
                sa.text(
                    "UPDATE run_snapshots SET artifact_size_bytes = -1 "
                    "WHERE id = '00000000-0000-0000-0000-000000000002'"
                )
            )
    engine.dispose()


def test_application_sqlite_engine_enables_foreign_keys() -> None:
    with get_engine().connect() as connection:
        assert connection.scalar(sa.text("PRAGMA foreign_keys")) == 1
