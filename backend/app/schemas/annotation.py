from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.datetime import ensure_utc


class AnnotationColor(StrEnum):
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"
    GRAY = "gray"


class AnnotationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class AnnotationCreate(BaseModel):
    row_identity: str = Field(min_length=1, max_length=256)
    column_key: str | None = Field(None, max_length=128)
    author: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_:.-]+$")
    color: AnnotationColor
    title: str | None = Field(None, max_length=256)
    text: str | None = Field(None, max_length=2000)
    severity: AnnotationSeverity | None = None
    annotation_set: str | None = Field(None, max_length=128)

    sql_fingerprint: str | None = Field(None, max_length=80)
    schema_fingerprint: str | None = Field(None, max_length=80)
    result_fingerprint: str | None = Field(None, max_length=80)


class AnnotationOut(BaseModel):
    id: int
    query_id: int
    row_identity: str
    column_key: str | None
    author: str
    color: AnnotationColor
    title: str | None
    text: str | None
    severity: AnnotationSeverity | None
    annotation_set: str | None
    sql_fingerprint: str | None
    schema_fingerprint: str | None
    result_fingerprint: str | None
    created_at: datetime
    expires_at: datetime | None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def normalize_datetimes(self) -> AnnotationOut:
        self.created_at = ensure_utc(self.created_at)
        if self.expires_at is not None:
            self.expires_at = ensure_utc(self.expires_at)
        return self


class AnnotationBatchCreate(BaseModel):
    annotations: list[AnnotationCreate] = Field(min_length=1, max_length=200)


class AnnotationDeleteResponse(BaseModel):
    deleted_count: int
