from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.connection import Connection
    from app.models.named_query import NamedQuery


class TraceContract(Base):
    __tablename__ = "trace_contracts"
    __table_args__ = (
        UniqueConstraint(
            "name", "named_query_id", "version", name="uq_trace_contract_name_query_version"
        ),
        CheckConstraint("version >= 1", name="ck_trace_contract_version_positive"),
        Index("ix_trace_contract_definition_sha256", "definition_sha256"),
        Index("ix_trace_contract_query_created", "named_query_id", "created_at"),
        Index("uq_trace_contract_idempotency_key", "idempotency_key", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    named_query_id: Mapped[int] = mapped_column(
        ForeignKey("named_queries.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    definition_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    request_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    named_query: Mapped[NamedQuery] = relationship()
    snapshots: Mapped[list[RunSnapshot]] = relationship(back_populates="trace_contract")


class RunSnapshot(Base):
    __tablename__ = "run_snapshots"
    __table_args__ = (
        CheckConstraint(
            "status IN ('building','ready','failed','corrupted','deleted')",
            name="ck_run_snapshot_status",
        ),
        CheckConstraint(
            "artifact_size_bytes >= 0 AND source_row_count >= 0 AND run_count >= 0",
            name="ck_run_snapshot_non_negative_counts",
        ),
        Index("ix_run_snapshot_status_created", "status", "created_at"),
        Index("ix_run_snapshot_contract_created", "trace_contract_id", "created_at"),
        Index("ix_run_snapshot_input_fingerprint", "input_fingerprint"),
        Index("ix_run_snapshot_content_sha256", "content_sha256"),
        Index("ix_run_snapshot_artifact_sha256", "artifact_sha256"),
        Index(
            "uq_run_snapshot_building_input_fingerprint",
            "input_fingerprint",
            unique=True,
            sqlite_where=text("status = 'building' AND idempotency_key IS NULL"),
        ),
        Index("uq_run_snapshot_idempotency_key", "idempotency_key", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    trace_contract_id: Mapped[str] = mapped_column(
        ForeignKey("trace_contracts.id", ondelete="RESTRICT"), nullable=False
    )
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("connections.id", ondelete="RESTRICT"), nullable=False
    )
    named_query_id: Mapped[int] = mapped_column(
        ForeignKey("named_queries.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="building", nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    request_sha256: Mapped[str | None] = mapped_column(String(64))
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    artifact_path: Mapped[str | None] = mapped_column(String(1024))
    artifact_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    run_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_source_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pairing_key_field_coverage: Mapped[float | None] = mapped_column(Float)
    build_policy: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    error: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    trace_contract: Mapped[TraceContract] = relationship(back_populates="snapshots")
    connection: Mapped[Connection] = relationship()
    named_query: Mapped[NamedQuery] = relationship()
