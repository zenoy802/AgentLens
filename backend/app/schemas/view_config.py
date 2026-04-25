from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.datetime import ensure_utc
from app.schemas.render import FieldRender


class SortConfig(BaseModel):
    column: str = Field(min_length=1)
    direction: Literal["asc", "desc"] = "asc"


class TableConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    column_widths: dict[str, int] = Field(default_factory=dict)
    hidden_columns: list[str] = Field(default_factory=list)
    frozen_columns: list[str] = Field(default_factory=list)
    sort: list[SortConfig] = Field(default_factory=list)


class TrajectoryConfig(BaseModel):
    group_by: str = Field(min_length=1)
    role_column: str = Field(min_length=1)
    content_column: str = Field(min_length=1)
    tool_calls_column: str | None = None
    order_by: str | None = None
    order_direction: Literal["asc", "desc"] = "asc"


class ViewConfigPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_renders: dict[str, FieldRender] = Field(default_factory=dict)
    table_config: TableConfig = Field(default_factory=TableConfig)
    trajectory_config: TrajectoryConfig | None = None
    row_identity_column: str | None = None


class ViewConfigRead(ViewConfigPayload):
    query_id: int
    updated_at: datetime

    @field_validator("updated_at", mode="after")
    @classmethod
    def normalize_updated_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)
