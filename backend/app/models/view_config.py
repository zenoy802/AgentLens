from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.named_query import NamedQuery


class ViewConfig(Base, TimestampMixin):
    __tablename__ = "view_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_id: Mapped[int] = mapped_column(
        ForeignKey("named_queries.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    field_renders: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    table_config: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    trajectory_config: Mapped[str | None] = mapped_column(Text)
    row_identity_column: Mapped[str | None] = mapped_column(String(200))

    named_query: Mapped[NamedQuery] = relationship(back_populates="view_config")
