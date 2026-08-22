from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    field_validator,
    model_validator,
)

from app.schemas.common import CursorPagination

JsonScalar: TypeAlias = str | int | float | bool | None
CanonicalOutcome: TypeAlias = Literal["success", "failure", "abstain", "unknown"]
CanonicalEventStatus: TypeAlias = Literal["ok", "error", "cancelled", "unknown"]


def _mapping_key(value: JsonScalar, *, case_sensitive: bool) -> tuple[str, str]:
    normalized = value
    if isinstance(value, str) and not case_sensitive:
        normalized = value.casefold()
    elif isinstance(value, float) and value == 0.0:
        # Runtime matching uses typed Python equality, where -0.0 == 0.0.
        normalized = 0.0
    type_name = type(normalized).__name__
    encoded = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return type_name, encoded


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OutcomeMapping(StrictSchema):
    success_values: list[JsonScalar]
    failure_values: list[JsonScalar]
    abstain_values: list[JsonScalar] = Field(default_factory=list)
    case_sensitive: bool = True

    @field_validator("success_values", "failure_values")
    @classmethod
    def require_non_empty_values(cls, value: list[JsonScalar]) -> list[JsonScalar]:
        if not value:
            raise ValueError("success_values and failure_values must not be empty")
        return value

    @model_validator(mode="after")
    def validate_disjoint_values(self) -> OutcomeMapping:
        groups = {
            "success_values": self.success_values,
            "failure_values": self.failure_values,
            "abstain_values": self.abstain_values,
        }
        owners: dict[tuple[str, str], str] = {}
        for group_name, values in groups.items():
            for value in values:
                key = _mapping_key(value, case_sensitive=self.case_sensitive)
                previous = owners.get(key)
                if previous is not None:
                    raise ValueError(
                        f"outcome mapping values overlap between {previous} and {group_name}"
                    )
                owners[key] = group_name
        return self


class EventStatusMapping(StrictSchema):
    ok_values: list[JsonScalar] = Field(default_factory=list)
    error_values: list[JsonScalar] = Field(default_factory=list)
    cancelled_values: list[JsonScalar] = Field(default_factory=list)
    case_sensitive: bool = True

    @model_validator(mode="after")
    def validate_disjoint_values(self) -> EventStatusMapping:
        groups = {
            "ok_values": self.ok_values,
            "error_values": self.error_values,
            "cancelled_values": self.cancelled_values,
        }
        owners: dict[tuple[str, str], str] = {}
        for group_name, values in groups.items():
            for value in values:
                key = _mapping_key(value, case_sensitive=self.case_sensitive)
                previous = owners.get(key)
                if previous is not None:
                    raise ValueError(
                        f"event status mapping values overlap between {previous} and {group_name}"
                    )
                owners[key] = group_name
        return self


class MessageMapping(StrictSchema):
    role: str = "role"
    content: str = "content"
    name: str | None = "name"
    tool_call_id: str | None = "tool_call_id"
    tool_calls: str | None = "tool_calls"
    status: str | None = None
    timestamp: str | None = None
    latency_ms: str | None = None
    tokens_in: str | None = None
    tokens_out: str | None = None
    cost_usd: str | None = None


class EventMapping(StrictSchema):
    kind: str | None = None
    role: str | None = "role"
    content: str = "content"
    name: str | None = "name"
    tool_call_id: str | None = "tool_call_id"
    tool_calls: str | None = "tool_calls"
    status: str | None = None
    parent_event_id: str | None = None
    timestamp: str | None = None
    latency_ms: str | None = None
    tokens_in: str | None = None
    tokens_out: str | None = None
    cost_usd: str | None = None

    @model_validator(mode="after")
    def require_role_or_kind(self) -> EventMapping:
        if self.role is None and self.kind is None:
            raise ValueError("event_mapping must define role or kind")
        return self


class TraceContractBase(StrictSchema):
    version: Literal["trace-contract/v1"] = "trace-contract/v1"
    source_layout: Literal["run_rows", "event_rows"]
    task_id: str
    trial_id: str | None = None
    trace_id: str
    pairing_key: str | None = None
    outcome: str
    outcome_mapping: OutcomeMapping
    status_mapping: EventStatusMapping | None = None
    score: str | None = None
    latency_ms: str | None = None
    token_usage: str | None = None
    cost_usd: str | None = None
    error: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class RunRowsContract(TraceContractBase):
    source_layout: Literal["run_rows"] = "run_rows"
    messages: str
    message_mapping: MessageMapping


class EventRowsContract(TraceContractBase):
    source_layout: Literal["event_rows"] = "event_rows"
    event_index: str
    event_mapping: EventMapping


TraceContract: TypeAlias = Annotated[
    RunRowsContract | EventRowsContract,
    Field(discriminator="source_layout"),
]
trace_contract_adapter: TypeAdapter[TraceContract] = TypeAdapter(TraceContract)


class SourceRef(StrictSchema):
    query_id: int = Field(gt=0)
    row_identity: str = Field(min_length=1, max_length=512)
    json_path: str | None = None


class CanonicalMessage(StrictSchema):
    event_index: int | str
    kind: str | None = None
    role: str | None = None
    content: JsonValue
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: JsonValue | None = None
    status: CanonicalEventStatus = "unknown"
    parent_event_id: str | None = None
    timestamp: str | None = None
    latency_ms: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    source_ref: SourceRef


class RunMetrics(StrictSchema):
    latency_ms: float | None = None
    token_usage: int | None = None
    cost_usd: float | None = None


class CanonicalRunRow(StrictSchema):
    schema_version: Literal["run-row/v1"] = "run-row/v1"
    task_id: str = Field(min_length=1, max_length=512)
    trial_id: str | None = Field(default=None, min_length=1, max_length=512)
    trace_id: str = Field(min_length=1, max_length=512)
    pairing_key: str | None = Field(default=None, min_length=1, max_length=512)
    outcome: CanonicalOutcome
    score: float | None = None
    metrics: RunMetrics = Field(default_factory=RunMetrics)
    messages: list[CanonicalMessage]
    error: JsonValue | None = None
    metadata: dict[str, JsonScalar] = Field(default_factory=dict)


class TraceDiagnostic(StrictSchema):
    code: str
    path: str
    source_row_index: int


class NormalizedRun(StrictSchema):
    run: CanonicalRunRow
    diagnostics: list[TraceDiagnostic] = Field(default_factory=list)


class NormalizationBatch(StrictSchema):
    runs: list[CanonicalRunRow]
    diagnostics: list[TraceDiagnostic] = Field(default_factory=list)
    source_row_count: int = Field(ge=0)
    valid_run_count: int = Field(ge=0)
    pairing_key_field_coverage: float = Field(ge=0.0, le=1.0)


class TraceContractCreate(StrictSchema):
    name: str = Field(min_length=1, max_length=200)
    named_query_id: int = Field(gt=0)
    definition: TraceContract


class TraceContractValidateRequest(StrictSchema):
    named_query_id: int = Field(gt=0)
    definition: TraceContract
    sample_limit: int = Field(default=100, ge=1, le=100)


class TraceValidationIssue(StrictSchema):
    code: str
    reason: str
    path: str | None = None
    source_row_index: int | None = None


class TraceContractValidationResult(StrictSchema):
    schema_version: Literal["trace-contract-validation/v1"] = "trace-contract-validation/v1"
    valid: bool
    source_row_count: int = Field(ge=0)
    valid_run_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    errors: list[TraceValidationIssue]
    diagnostics: list[TraceDiagnostic]
    pairing_key_field_coverage: float = Field(ge=0.0, le=1.0)
    canonical_preview: list[CanonicalRunRow]


class TraceContractRead(StrictSchema):
    schema_version: Literal["trace-contract-resource/v1"] = "trace-contract-resource/v1"
    id: str
    name: str
    named_query_id: int
    named_query_name: str | None
    version: int
    definition: TraceContract
    definition_sha256: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class TraceContractListResponse(StrictSchema):
    items: list[TraceContractRead]
    pagination: CursorPagination
