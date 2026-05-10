from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import WarningRead
from app.schemas.datetime import ensure_utc
from app.schemas.render import FieldRender
from app.schemas.view_config import TrajectoryConfig
from app.services.inferred_type import InferredType


class ExecuteRequest(BaseModel):
    connection_id: int = Field(gt=0)
    sql: str = Field(min_length=1)
    save_as_temporary: bool = True
    timeout: int | None = Field(default=None, ge=1, le=300)
    row_limit: int | None = Field(default=None, ge=1, le=100000)


class QueryExecuteRequest(BaseModel):
    timeout: int | None = Field(default=None, ge=1, le=300)
    row_limit: int | None = Field(default=None, ge=1, le=100000)


class ColumnRead(BaseModel):
    name: str
    sql_type: str
    inferred_type: InferredType


class ExecutionInfo(BaseModel):
    executed_at: datetime
    duration_ms: int
    row_count: int
    truncated: bool

    @field_validator("executed_at", mode="after")
    @classmethod
    def normalize_executed_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class ExecutionResult(BaseModel):
    query_id: int
    is_temporary: bool
    execution: ExecutionInfo
    columns: list[ColumnRead]
    rows: list[dict[str, Any]]
    suggested_field_renders: dict[str, FieldRender]
    suggested_trajectory_config: TrajectoryConfig | None = None
    warnings: list[WarningRead]
