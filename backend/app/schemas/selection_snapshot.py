from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.datetime import ensure_utc


class SelectionSnapshotCreate(BaseModel):
    row_identities: list[str] = Field(min_length=1, max_length=10000)
    source: str | None = Field(None, max_length=64)


class SelectionSnapshotOut(BaseModel):
    id: str
    query_id: int
    row_identities: list[str]
    count: int
    source: str | None
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def normalize_datetimes(self) -> SelectionSnapshotOut:
        self.created_at = ensure_utc(self.created_at)
        self.expires_at = ensure_utc(self.expires_at)
        return self
