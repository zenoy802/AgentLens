from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.connection import Connection
    from app.models.named_query import NamedQuery


class GlobalRenderRule(Base, TimestampMixin):
    __tablename__ = "global_render_rules"
    __table_args__ = (
        Index("idx_grr_enabled_priority", "enabled", "priority"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_pattern: Mapped[str] = mapped_column(String(200), nullable=False)
    match_type: Mapped[str] = mapped_column(String(20), nullable=False, default="exact")
    render_config: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class QueryHistory(Base):
    __tablename__ = "query_history"
    __table_args__ = (
        Index("idx_qh_connection", "connection_id"),
        Index("idx_qh_executed", "executed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    query_id: Mapped[int | None] = mapped_column(
        ForeignKey("named_queries.id", ondelete="SET NULL"),
    )
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.current_timestamp(),
    )

    connection: Mapped[Connection] = relationship(back_populates="query_history_entries")
    named_query: Mapped[NamedQuery | None] = relationship(back_populates="query_history_entries")
