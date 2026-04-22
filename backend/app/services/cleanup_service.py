from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.label import LabelRecord
from app.models.llm import LLMAnalysis
from app.models.misc import QueryHistory
from app.models.named_query import NamedQuery


class CleanupReport(BaseModel):
    expired_queries_deleted: int
    history_records_deleted: int
    cascade_label_records_deleted: int
    cascade_analyses_deleted: int
    dry_run: bool


class CleanupService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def run(self, db: Session, dry_run: bool = False) -> CleanupReport:
        now = _utcnow()
        expired_query_ids = select(NamedQuery.id).where(
            NamedQuery.expires_at.is_not(None),
            NamedQuery.expires_at < now,
        )

        expired_queries_count = self._count(
            db,
            select(func.count())
            .select_from(NamedQuery)
            .where(
                NamedQuery.expires_at.is_not(None),
                NamedQuery.expires_at < now,
            ),
        )
        label_records_count = self._count(
            db,
            select(func.count())
            .select_from(LabelRecord)
            .where(
                LabelRecord.query_id.in_(expired_query_ids),
            ),
        )
        analyses_count = self._count(
            db,
            select(func.count())
            .select_from(LLMAnalysis)
            .where(
                LLMAnalysis.query_id.in_(expired_query_ids),
            ),
        )

        if not dry_run:
            db.execute(
                delete(NamedQuery).where(
                    NamedQuery.expires_at.is_not(None),
                    NamedQuery.expires_at < now,
                )
            )

        history_cutoff = now - timedelta(days=self._settings.query_history_retention_days)
        history_records_count = self._count(
            db,
            select(func.count())
            .select_from(QueryHistory)
            .where(
                QueryHistory.executed_at < history_cutoff,
            ),
        )

        if not dry_run:
            db.execute(delete(QueryHistory).where(QueryHistory.executed_at < history_cutoff))

        db.commit()
        return CleanupReport(
            expired_queries_deleted=expired_queries_count,
            history_records_deleted=history_records_count,
            cascade_label_records_deleted=label_records_count,
            cascade_analyses_deleted=analyses_count,
            dry_run=dry_run,
        )

    @staticmethod
    def _count(db: Session, stmt: Select[tuple[int]]) -> int:
        return int(db.scalar(stmt) or 0)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
