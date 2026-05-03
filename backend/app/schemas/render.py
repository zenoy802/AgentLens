from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class RenderBase(BaseModel):
    model_config = ConfigDict(extra="allow")


class TextRender(RenderBase):
    type: Literal["text"] = "text"


class MarkdownRender(RenderBase):
    type: Literal["markdown"] = "markdown"


class JsonRender(RenderBase):
    type: Literal["json"] = "json"
    collapsed: bool = True


class CodeRender(RenderBase):
    type: Literal["code"] = "code"
    language: str = "plain"


class TimestampRender(RenderBase):
    type: Literal["timestamp"] = "timestamp"
    format: str = "YYYY-MM-DD HH:mm:ss"


class TagRender(RenderBase):
    type: Literal["tag"] = "tag"


FieldRender: TypeAlias = Annotated[
    TextRender | MarkdownRender | JsonRender | CodeRender | TimestampRender | TagRender,
    Field(discriminator="type"),
]

field_render_adapter: TypeAdapter[FieldRender] = TypeAdapter(FieldRender)
