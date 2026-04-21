from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FieldRender(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str = Field(min_length=1)
    collapsed: bool | None = None
    format: str | None = None
    language: str | None = None


class TextRender(FieldRender):
    type: str = "text"


class JsonRender(FieldRender):
    type: str = "json"
    collapsed: bool = True


class TimestampRender(FieldRender):
    type: str = "timestamp"
    format: str = "YYYY-MM-DD HH:mm:ss"
