from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SelectionSnapshot(Base):
    __tablename__ = "selection_snapshots"
    __table_args__ = (Index("ix_selection_snapshots_query", "query_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    query_id: Mapped[int] = mapped_column(
        ForeignKey("named_queries.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    row_identities_json: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False,
    )
