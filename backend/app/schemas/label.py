from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.schemas.datetime import ensure_utc


class LabelOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    label: str
    color: str | None = None


class SingleSelectField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    type: Literal["single_select"] = "single_select"
    options: list[LabelOption] = Field(default_factory=list)


class MultiSelectField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    type: Literal["multi_select"] = "multi_select"
    options: list[LabelOption] = Field(default_factory=list)


class TextField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    type: Literal["text"] = "text"


LabelField: TypeAlias = Annotated[
    SingleSelectField | MultiSelectField | TextField,
    Field(discriminator="type"),
]

label_fields_adapter: TypeAdapter[list[LabelField]] = TypeAdapter(list[LabelField])


class LabelSchemaPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: list[LabelField] = Field(default_factory=list)


class LabelSchemaRead(BaseModel):
    query_id: int
    fields: list[LabelField]
    updated_at: datetime
    cascade_deleted_records: int = 0

    @model_validator(mode="after")
    def normalize_datetimes(self) -> LabelSchemaRead:
        self.updated_at = ensure_utc(self.updated_at)
        return self


class LabelsByRowResponse(BaseModel):
    labels_by_row: dict[str, dict[str, Any]]


class LabelRowsQuery(BaseModel):
    row_identities: list[str] = Field(default_factory=list)


class LabelRecordUpsert(BaseModel):
    row_identity: str = Field(min_length=1, max_length=512)
    field_key: str = Field(min_length=1, max_length=200)
    value: Any | None


class LabelRecordRead(BaseModel):
    record_id: int
    query_id: int
    row_identity: str
    field_key: str
    value: Any
    updated_at: datetime

    @model_validator(mode="after")
    def normalize_datetimes(self) -> LabelRecordRead:
        self.updated_at = ensure_utc(self.updated_at)
        return self


class LabelBatchUpsert(BaseModel):
    row_identities: list[str] = Field(default_factory=list)
    field_key: str = Field(min_length=1, max_length=200)
    value: Any | None


class LabelBatchError(BaseModel):
    row_identity: str
    code: str
    message: str
    detail: dict[str, Any] | None = None


class LabelBatchResult(BaseModel):
    affected: int
    skipped: int
    errors: list[LabelBatchError] = Field(default_factory=list)
