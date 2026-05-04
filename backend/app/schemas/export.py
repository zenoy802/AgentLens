from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

ExportFormat = Literal["csv", "xlsx"]
JsonSerialization = Literal["string"]


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: ExportFormat
    include_labels: bool = True
    json_serialization: JsonSerialization = "string"
