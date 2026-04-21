from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from app.schemas.common import Pagination
from app.schemas.datetime import ensure_utc


class NamedQueryCreate(BaseModel):
    connection_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    sql_text: str = Field(min_length=1)
    expires_at: datetime | None = None


class NamedQueryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | SkipJsonSchema[None] = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    expires_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_null_name(cls, data: Any) -> Any:
        if isinstance(data, dict) and "name" in data and data["name"] is None:
            raise ValueError("name cannot be null.")
        return data


class NamedQueryPromote(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    expires_at: datetime | None = None


class NamedQueryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    connection_id: int
    name: str | None
    description: str | None
    sql_text: str
    is_named: bool
    created_at: datetime
    updated_at: datetime
    last_executed_at: datetime | None
    expires_at: datetime | None

    @model_validator(mode="after")
    def normalize_datetimes(self) -> NamedQueryRead:
        self.created_at = ensure_utc(self.created_at)
        self.updated_at = ensure_utc(self.updated_at)
        if self.last_executed_at is not None:
            self.last_executed_at = ensure_utc(self.last_executed_at)
        if self.expires_at is not None:
            self.expires_at = ensure_utc(self.expires_at)
        return self


class NamedQueryListResponse(BaseModel):
    items: list[NamedQueryRead]
    pagination: Pagination
