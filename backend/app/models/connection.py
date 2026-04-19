from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.misc import QueryHistory
    from app.models.named_query import NamedQuery


class Connection(Base, TimestampMixin):
    __tablename__ = "connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    db_type: Mapped[str] = mapped_column(String(20), nullable=False)
    host: Mapped[str | None] = mapped_column(String(255))
    port: Mapped[int | None] = mapped_column(Integer)
    database: Mapped[str] = mapped_column(String(200), nullable=False)
    username: Mapped[str | None] = mapped_column(String(200))
    password_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    extra_params: Mapped[str | None] = mapped_column(Text)
    default_timeout: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    default_row_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    last_tested_at: Mapped[datetime | None]
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean)

    named_queries: Mapped[list[NamedQuery]] = relationship(
        back_populates="connection",
        cascade="all, delete-orphan",
    )
    query_history_entries: Mapped[list[QueryHistory]] = relationship(
        back_populates="connection",
        cascade="all, delete-orphan",
    )
