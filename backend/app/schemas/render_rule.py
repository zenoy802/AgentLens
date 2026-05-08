from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self, TypeAlias

from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_validator

from app.schemas.datetime import ensure_utc
from app.schemas.render import (
    CodeRender,
    JsonRender,
    MarkdownRender,
    TagRender,
    TextRender,
    TimestampRender,
)

MatchType = Literal["exact", "prefix", "suffix", "regex"]
TrajectoryConfigField = Literal[
    "group_by",
    "role_column",
    "content_column",
    "tool_calls_column",
    "order_by",
]


class TrajectoryConfigRule(BaseModel):
    type: Literal["trajectory_config"] = "trajectory_config"
    field: TrajectoryConfigField
    order_direction: Literal["asc", "desc"] | None = None

    @model_validator(mode="after")
    def validate_order_direction(self) -> Self:
        if self.field != "order_by" and self.order_direction is not None:
            raise ValueError("order_direction is only valid when field is order_by.")
        return self


RenderRuleConfig: TypeAlias = Annotated[
    TextRender
    | MarkdownRender
    | JsonRender
    | CodeRender
    | TimestampRender
    | TagRender
    | TrajectoryConfigRule,
    Field(discriminator="type"),
]

render_rule_config_adapter: TypeAdapter[RenderRuleConfig] = TypeAdapter(RenderRuleConfig)


class RenderRuleCreate(BaseModel):
    match_pattern: str = Field(min_length=1, max_length=200)
    match_type: MatchType = "exact"
    render_config: RenderRuleConfig
    priority: int = 0
    enabled: bool = True


class RenderRuleUpdate(BaseModel):
    match_pattern: str | None = Field(default=None, min_length=1, max_length=200)
    match_type: MatchType | None = None
    render_config: RenderRuleConfig | None = None
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
