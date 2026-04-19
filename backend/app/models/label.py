from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.named_query import NamedQuery


class LabelSchema(Base, TimestampMixin):
    __tablename__ = "label_schemas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_id: Mapped[int] = mapped_column(
        ForeignKey("named_queries.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    fields: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    named_query: Mapped[NamedQuery] = relationship(back_populates="label_schema")


class LabelRecord(Base, TimestampMixin):
    __tablename__ = "label_records"
    __table_args__ = (
        UniqueConstraint("query_id", "row_identity", "field_key"),
        Index("idx_lr_query_row", "query_id", "row_identity"),
        Index("idx_lr_query_field", "query_id", "field_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_id: Mapped[int] = mapped_column(
        ForeignKey("named_queries.id", ondelete="CASCADE"),
        nullable=False,
    )
    row_identity: Mapped[str] = mapped_column(String(512), nullable=False)
    field_key: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    named_query: Mapped[NamedQuery] = relationship(back_populates="label_records")
