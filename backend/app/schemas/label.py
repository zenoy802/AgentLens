from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


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
