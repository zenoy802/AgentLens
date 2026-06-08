from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import status
from loguru import logger
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.logging import safe_exception_context
from app.models.named_query import NamedQuery
from app.models.selection_snapshot import SelectionSnapshot
from app.schemas.datetime import ensure_utc
from app.schemas.selection_snapshot import SelectionSnapshotCreate, SelectionSnapshotOut

_SELECTION_SNAPSHOT_TTL_DAYS = 7


class SelectionSnapshotService:
    def __init__(self, session: Session) -> None:
        self.session = session

    async def create(
        self,
        query_id: int,
        payload: SelectionSnapshotCreate,
    ) -> SelectionSnapshot:
        self._get_query_or_raise(query_id)
        now = _utcnow()
        snapshot = SelectionSnapshot(
            id=self._generate_id(now),
            query_id=query_id,
            row_identities_json=json.dumps(
                payload.row_identities,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            source=payload.source,
            created_at=now,
            expires_at=now + timedelta(days=_SELECTION_SNAPSHOT_TTL_DAYS),
        )
        self.session.add(snapshot)
        try:
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            logger.warning(
                "Selection snapshot create failed: query_id={} context={}",
                query_id,
                safe_exception_context(exc),
            )
            raise
        logger.info(
            "Selection snapshot created: query_id={} selection_id={} rows={}",
            query_id,
            snapshot.id,
            len(payload.row_identities),
        )
        return snapshot

    async def get(self, selection_id: str) -> SelectionSnapshot:
        snapshot = self.session.get(SelectionSnapshot, selection_id)
        if snapshot is None:
            logger.warning("Selection snapshot not found: selection_id={}", selection_id)
            raise NotFoundError(
                "selection snapshot not found",
                code="SELECTION_NOT_FOUND",
                detail={"selection_id": selection_id},
            )
        if ensure_utc(snapshot.expires_at) < _utcnow():
            logger.warning("Selection snapshot expired: selection_id={}", selection_id)
            raise NotFoundError(
                "selection snapshot expired",
                code="SELECTION_EXPIRED",
                http_status=status.HTTP_410_GONE,
                detail={"selection_id": selection_id, "expires_at": snapshot.expires_at},
            )
        logger.info("Selection snapshot loaded: selection_id={}", selection_id)
        return snapshot

    async def delete(self, selection_id: str) -> None:
        snapshot = self.session.get(SelectionSnapshot, selection_id)
        if snapshot is None:
            raise NotFoundError(
                "selection snapshot not found",
                code="SELECTION_NOT_FOUND",
                detail={"selection_id": selection_id},
            )
        self.session.delete(snapshot)
        self.session.commit()
        logger.info("Selection snapshot deleted: selection_id={}", selection_id)

    def to_read_model(self, snapshot: SelectionSnapshot) -> SelectionSnapshotOut:
        row_identities = _decode_row_identities(snapshot.row_identities_json)
        return SelectionSnapshotOut(
            id=snapshot.id,
            query_id=snapshot.query_id,
            row_identities=row_identities,
            count=len(row_identities),
            source=snapshot.source,
            created_at=snapshot.created_at,
            expires_at=snapshot.expires_at,
        )

    def _generate_id(self, now: datetime) -> str:
        timestamp = ensure_utc(now).strftime("%Y%m%d_%H%M%S")
        while True:
            candidate = f"sel_{timestamp}_{secrets.token_hex(4)}"
            if self.session.get(SelectionSnapshot, candidate) is None:
                return candidate

    def _get_query_or_raise(self, query_id: int) -> NamedQuery:
        query = self.session.get(NamedQuery, query_id)
        if query is None:
            raise NotFoundError(
                "Named query not found.",
                code="QUERY_NOT_FOUND",
                detail={"query_id": query_id},
            )
        return query


def _decode_row_identities(payload: str) -> list[str]:
    raw = json.loads(payload)
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)]


def _utcnow() -> datetime:
    return datetime.now(UTC)
