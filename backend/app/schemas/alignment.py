from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, TypeAlias

from pydantic import Field, JsonValue, field_validator, model_validator

from app.schemas.trace_contract import CanonicalEventStatus, StrictSchema

_MAX_REGEX_LENGTH = 256
_MAX_BOUNDED_QUANTIFIER = 1000

EventKind: TypeAlias = Literal[
    "system",
    "user",
    "assistant",
    "tool_call",
    "tool_result",
    "other",
]
AlignmentOperation: TypeAlias = Literal[
    "match",
    "near_match",
    "change",
    "insert",
    "delete",
]
AlignmentQuality: TypeAlias = Literal["exact", "degraded"]
ScrubberScope: TypeAlias = Literal["all", "assistant", "tool_arguments", "tool_result"]
DivergenceCategory: TypeAlias = Literal[
    "error_or_termination_changed",
    "tool_name_changed",
    "tool_argument_changed",
    "tool_result_changed",
    "assistant_content_near_match",
    "assistant_content_changed",
    "message_inserted",
    "message_deleted",
    "other_changed",
]


def _validate_safe_regex(pattern: str) -> str:
    if len(pattern) > _MAX_REGEX_LENGTH:
        raise ValueError("regex patterns must be at most 256 characters")
    forbidden_fragments = ("(?", "*", "+", "(", ")")
    if any(fragment in pattern for fragment in forbidden_fragments):
        raise ValueError(
            "regex must use the supported RE2-compatible subset without lookaround, "
            "groups, backreferences, or unbounded quantifiers"
        )
    if re.search(r"\\[1-9]", pattern):
        raise ValueError("regex must not contain backreferences")
    if re.search(r"\{\d+,\}", pattern):
        raise ValueError("regex must not contain an unbounded quantifier")
    for match in re.finditer(r"\{(\d+)(?:,(\d+))?\}", pattern):
        upper = int(match.group(2) or match.group(1))
        if upper > _MAX_BOUNDED_QUANTIFIER:
            raise ValueError("bounded regex quantifiers must not exceed 1000")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError("regex pattern is invalid") from exc
    return pattern


class StringScrubberRule(StrictSchema):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    pattern: str
    replacement: str = Field(max_length=128)
    flags: list[Literal["ignore_case", "multiline", "dotall"]] = Field(default_factory=list)
    scope: ScrubberScope = "all"

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, value: str) -> str:
        return _validate_safe_regex(value)

    @field_validator("flags")
    @classmethod
    def unique_flags(
        cls,
        value: list[Literal["ignore_case", "multiline", "dotall"]],
    ) -> list[Literal["ignore_case", "multiline", "dotall"]]:
        if len(value) != len(set(value)):
            raise ValueError("scrubber flags must be unique")
        return value

    @field_validator("replacement")
    @classmethod
    def reject_replacement_backreferences(cls, value: str) -> str:
        if re.search(r"\\(?:[1-9]|g<)", value):
            raise ValueError("scrubber replacements must not contain backreferences")
        return value


class StringScrubberPolicy(StrictSchema):
    preset: Literal["volatile-runtime/v1", "none"] = "volatile-runtime/v1"
    rules: list[StringScrubberRule] = Field(default_factory=list, max_length=32)
    max_replacements_per_leaf: int = Field(default=100, ge=1, le=1000)

    @model_validator(mode="after")
    def require_unique_rule_ids(self) -> StringScrubberPolicy:
        rule_ids = [rule.id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("scrubber rule ids must be unique")
        return self


class CanonicalizationPolicy(StrictSchema):
    version: Literal["canonicalization/v1"] = "canonicalization/v1"
    ignored_json_paths: list[str] = Field(
        default_factory=lambda: ["$.timestamp", "$.request_id", "$.trace_id"],
        max_length=64,
    )
    ignored_key_patterns: list[str] = Field(
        default_factory=lambda: [r"(?i).*nonce$"],
        max_length=32,
    )
    normalize_whitespace: bool = True
    normalize_line_endings: bool = True
    sort_object_keys: bool = True
    string_scrubbers: StringScrubberPolicy = Field(default_factory=StringScrubberPolicy)
    numeric_abs_tolerance: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    numeric_rel_tolerance: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    max_content_chars: int = Field(default=200_000, ge=128, le=10_000_000)
    assistant_text_similarity: Literal["token_bigram_or_char4_jaccard"] = (
        "token_bigram_or_char4_jaccard"
    )
    assistant_near_match_threshold: float = Field(default=0.85, ge=0.0, le=1.0, allow_inf_nan=False)
    assistant_near_match_min_length_ratio: float = Field(
        default=0.80, gt=0.0, le=1.0, allow_inf_nan=False
    )
    assistant_short_text_exact_chars: int = Field(default=24, ge=1, le=1000)
    tool_call_id_stability: Literal["unstable", "stable"] = "unstable"

    @field_validator("ignored_json_paths")
    @classmethod
    def validate_ignored_paths(cls, value: list[str]) -> list[str]:
        for path in value:
            if not path.startswith("$.") or not path[2:]:
                raise ValueError("ignored_json_paths must be simple paths beginning with '$.'")
            if any(segment in path for segment in ("*", "[", "]")):
                raise ValueError("ignored_json_paths do not support wildcards or array selectors")
        if len(value) != len(set(value)):
            raise ValueError("ignored_json_paths must be unique")
        return value

    @field_validator("ignored_key_patterns")
    @classmethod
    def validate_key_patterns(cls, value: list[str]) -> list[str]:
        # The built-in nonce expression is intentionally translated to a safe compiled regex by
        # the service. User-supplied entries otherwise use the same bounded subset as scrubbers.
        for pattern in value:
            if pattern != r"(?i).*nonce$":
                _validate_safe_regex(pattern)
        return value


class AlignmentPolicy(StrictSchema):
    version: Literal["alignment/v1"] = "alignment/v1"
    max_anchor_forced_gap_ratio: float = Field(default=0.40, ge=0.0, le=1.0, allow_inf_nan=False)
    max_anchor_segment_cost: float = Field(default=1.00, ge=0.0, allow_inf_nan=False)
    gap_open: float = Field(default=1.00, gt=0.0, allow_inf_nan=False)
    gap_extend: float = Field(default=0.25, ge=0.0, allow_inf_nan=False)
    status_change_cost: float = Field(default=1.50, gt=0.0, allow_inf_nan=False)
    assistant_near_match_cost: float = Field(default=0.20, ge=0.0, allow_inf_nan=False)
    numeric_tolerance_cost: float = Field(default=0.25, ge=0.0, allow_inf_nan=False)
    same_kind_name_change_cost: float = Field(default=0.75, ge=0.0, allow_inf_nan=False)
    same_kind_change_cost: float = Field(default=1.25, ge=0.0, allow_inf_nan=False)
    different_kind_cost: float = Field(default=2.00, ge=0.0, allow_inf_nan=False)
    full_dp_max_events: int = Field(default=500, ge=10, le=5000)
    initial_band_width: int = Field(default=100, ge=10, le=1000)
    expanded_band_width: int = Field(default=200, ge=10, le=2000)
    degraded_event_limit: int = Field(default=5000, ge=100, le=100_000)
    cpu_budget_seconds: float = Field(default=2.0, gt=0.0, le=60.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_bands(self) -> AlignmentPolicy:
        if self.expanded_band_width < self.initial_band_width:
            raise ValueError("expanded_band_width must be >= initial_band_width")
        if self.degraded_event_limit < self.full_dp_max_events:
            raise ValueError("degraded_event_limit must be >= full_dp_max_events")
        return self


class EventMetrics(StrictSchema):
    timestamp: datetime | None = None
    latency_ms: float | None = Field(default=None, ge=0.0)
    tokens_in: int | None = Field(default=None, ge=0)
    tokens_out: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0)


class ScrubberCount(StrictSchema):
    rule_id: str
    count: int = Field(ge=1)


class CanonicalContentResult(StrictSchema):
    content: JsonValue
    normalization_notes: list[str] = Field(default_factory=list)
    scrubber_counts: list[ScrubberCount] = Field(default_factory=list)
    ignored_fields: int = Field(default=0, ge=0)
    oversized: bool = False


class CanonicalEvent(StrictSchema):
    index: int = Field(ge=0)
    kind: EventKind
    actor: str | None = Field(default=None, max_length=512)
    call_id: str | None = Field(default=None, max_length=512)
    parent_ref: str | None = Field(default=None, max_length=2048)
    name: str | None = Field(default=None, max_length=512)
    status: CanonicalEventStatus
    content: JsonValue
    metrics: EventMetrics = Field(default_factory=EventMetrics)
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_ref: str = Field(min_length=1, max_length=4096)
    normalization_notes: list[str] = Field(default_factory=list)
    scrubber_counts: list[ScrubberCount] = Field(default_factory=list)
    oversized: bool = False


class CanonicalTrajectory(StrictSchema):
    schema_version: Literal["canonical-trajectory/v1"] = "canonical-trajectory/v1"
    trace_id: str
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    events: list[CanonicalEvent]
    ignored_difference_candidates: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def require_sequential_event_indices(self) -> CanonicalTrajectory:
        if [event.index for event in self.events] != list(range(len(self.events))):
            raise ValueError("canonical event indices must be sequential from zero")
        return self


class FieldDiff(StrictSchema):
    path: str
    before: JsonValue | None = None
    after: JsonValue | None = None
    category: Literal["value_changed", "type_changed", "added", "removed"]


class AlignmentStep(StrictSchema):
    op: AlignmentOperation
    baseline_index: int | None = Field(default=None, ge=0)
    candidate_index: int | None = Field(default=None, ge=0)
    kind: EventKind
    cost: float = Field(ge=0.0)
    similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    field_diffs: list[FieldDiff] = Field(default_factory=list)


class DivergencePoint(StrictSchema):
    step_index: int = Field(ge=0)
    category: DivergenceCategory
    baseline_index: int | None = Field(default=None, ge=0)
    candidate_index: int | None = Field(default=None, ge=0)
    evidence_paths: list[str] = Field(default_factory=list)


class AlignmentSummary(StrictSchema):
    matches: int = Field(ge=0)
    near_matches: int = Field(ge=0)
    changes: int = Field(ge=0)
    insertions: int = Field(ge=0)
    deletions: int = Field(ge=0)
    scrubbed_spans: int = Field(ge=0)
    ignored_fields: int = Field(ge=0)
    scrubber_counts: list[ScrubberCount] = Field(default_factory=list)
    rejected_anchors: int = Field(ge=0)


class AlignmentWarning(StrictSchema):
    code: str
    message: str
    detail: dict[str, JsonValue] = Field(default_factory=dict)


class AlignmentResult(StrictSchema):
    schema_version: Literal["trajectory-alignment/v1"] = "trajectory-alignment/v1"
    baseline_trace_id: str
    candidate_trace_id: str
    canonicalization_policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    quality: AlignmentQuality
    summary: AlignmentSummary
    steps: list[AlignmentStep]
    first_observed_divergence: DivergencePoint | None = None
    first_action_divergence: DivergencePoint | None = None
    warnings: list[AlignmentWarning] = Field(default_factory=list)
    total_cost: float = Field(ge=0.0)
