from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.common import Pagination
from app.schemas.datetime import ensure_utc


class QueryHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    connection_id: int
    sql_text: str
    row_count: int | None
    duration_ms: int | None
    status: str
    error_message: str | None
    executed_at: datetime
    query_id: int | None

    @field_validator("executed_at", mode="after")
    @classmethod
    def normalize_executed_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class QueryHistoryListResponse(BaseModel):
    items: list[QueryHistoryRead]
    pagination: Pagination
