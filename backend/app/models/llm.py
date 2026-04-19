from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.named_query import NamedQuery


class LLMProvider(Base, TimestampMixin):
    __tablename__ = "llm_providers"
    __table_args__ = (
        Index(
            "idx_llm_default",
            "is_default",
            unique=True,
            sqlite_where=text("is_default = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    extra_headers: Mapped[str | None] = mapped_column(Text)
    default_temperature: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    max_tokens: Mapped[int | None] = mapped_column(Integer)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class LLMAnalysis(Base):
    __tablename__ = "llm_analyses"
    __table_args__ = (
        Index("idx_la_query", "query_id"),
        Index("idx_la_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_id: Mapped[int] = mapped_column(
        ForeignKey("named_queries.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_id: Mapped[int | None] = mapped_column(
        ForeignKey("llm_providers.id", ondelete="SET NULL"),
    )
    selection: Mapped[str] = mapped_column(Text, nullable=False)
    structure_format: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    structured_input: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(String(200))
    token_usage: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime())

    named_query: Mapped[NamedQuery] = relationship(back_populates="llm_analyses")
