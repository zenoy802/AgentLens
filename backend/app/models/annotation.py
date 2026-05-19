from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Annotation(Base):
    __tablename__ = "annotations"
    __table_args__ = (
        Index("ix_annotations_query_row", "query_id", "row_identity"),
        Index("ix_annotations_query_author", "query_id", "author"),
        CheckConstraint(
            "color IN ('red','yellow','green','blue','gray')",
            name="ck_annotations_color",
        ),
        CheckConstraint(
            "severity IS NULL OR severity IN ('info','warning','error')",
            name="ck_annotations_severity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_id: Mapped[int] = mapped_column(
        ForeignKey("named_queries.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    row_identity: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    column_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    author: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    color: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    annotation_set: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    sql_fingerprint: Mapped[str | None] = mapped_column(String(80), nullable=True)
    schema_fingerprint: Mapped[str | None] = mapped_column(String(80), nullable=True)
    result_fingerprint: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
