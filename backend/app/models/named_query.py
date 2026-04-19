from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.expression import text

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.connection import Connection
    from app.models.label import LabelRecord, LabelSchema
    from app.models.llm import LLMAnalysis
    from app.models.misc import QueryHistory
    from app.models.view_config import ViewConfig


class NamedQuery(Base, TimestampMixin):
    __tablename__ = "named_queries"
    __table_args__ = (
        UniqueConstraint("connection_id", "name"),
        Index("idx_nq_connection", "connection_id"),
        Index("idx_nq_is_named", "is_named"),
        Index(
            "idx_nq_expires",
            "expires_at",
            sqlite_where=text("expires_at IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_named: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_executed_at: Mapped[datetime | None] = mapped_column(DateTime())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime())

    connection: Mapped[Connection] = relationship(back_populates="named_queries")
    view_config: Mapped[ViewConfig | None] = relationship(
        back_populates="named_query",
        uselist=False,
        cascade="all, delete-orphan",
    )
    label_schema: Mapped[LabelSchema | None] = relationship(
        back_populates="named_query",
        uselist=False,
        cascade="all, delete-orphan",
    )
    label_records: Mapped[list[LabelRecord]] = relationship(
        back_populates="named_query",
        cascade="all, delete-orphan",
    )
    llm_analyses: Mapped[list[LLMAnalysis]] = relationship(
        back_populates="named_query",
        cascade="all, delete-orphan",
    )
    query_history_entries: Mapped[list[QueryHistory]] = relationship(
        back_populates="named_query",
    )
