from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.datetime import ensure_utc
from app.schemas.render import FieldRender

MatchType = Literal["exact", "prefix", "suffix", "regex"]


class RenderRuleCreate(BaseModel):
    match_pattern: str = Field(min_length=1, max_length=200)
    match_type: MatchType = "exact"
    render_config: FieldRender
    priority: int = 0
    enabled: bool = True


class RenderRuleUpdate(BaseModel):
    match_pattern: str | None = Field(default=None, min_length=1, max_length=200)
    match_type: MatchType | None = None
    render_config: FieldRender | None = None
    priority: int | None = None
    enabled: bool | None = None


class RenderRuleRead(RenderRuleCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at", mode="after")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        return ensure_utc(value)
