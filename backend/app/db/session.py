from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache
from pathlib import Path
from typing import Any

from alembic.config import Config
from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import Settings, get_settings


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _set_sqlite_pragma(dbapi_connection: Any, _: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    engine = create_engine(
        settings.db_url,
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _set_sqlite_pragma)
    return engine


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def get_db_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def get_alembic_config(settings: Settings | None = None) -> Config:
    active_settings = settings or get_settings()
    config = Config(str(_project_root() / "alembic.ini"))
    config.set_main_option("script_location", str(_project_root() / "alembic"))
    config.set_main_option("sqlalchemy.url", active_settings.db_url)
    return config


def initialize_metadata_database() -> None:
    get_settings().ensure_directories()
    command.upgrade(get_alembic_config(), "head")


def metadata_database_is_ready() -> bool:
    engine = get_engine()
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    inspector = inspect(engine)
    return inspector.has_table("alembic_version") and inspector.has_table("connections")


def dispose_engine() -> None:
    if get_engine.cache_info().currsize > 0:
        get_engine().dispose()
    get_session_factory.cache_clear()
    get_engine.cache_clear()
