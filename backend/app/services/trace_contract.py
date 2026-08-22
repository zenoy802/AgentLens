from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import NoReturn, TypeAlias, TypeGuard

from pydantic import BaseModel, JsonValue, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from app.core.errors import SnapshotRowError, TraceContractError
from app.schemas.trace_contract import (
    CanonicalEventStatus,
    CanonicalMessage,
    CanonicalOutcome,
    CanonicalRunRow,
    EventRowsContract,
    EventStatusMapping,
    JsonScalar,
    NormalizationBatch,
    NormalizedRun,
    OutcomeMapping,
    RunMetrics,
    RunRowsContract,
    SourceRef,
    TraceContract,
    TraceDiagnostic,
    trace_contract_adapter,
)

CompiledPath: TypeAlias = tuple[str, ...]
_SENSITIVE_SEGMENTS = {
    "accesskey",
    "accesstoken",
    "apikey",
    "authorization",
    "credential",
    "credentials",
    "password",
    "passwd",
    "secret",
    "secretkey",
    "refreshtoken",
}
_MAX_PATH_LENGTH = 512
_MAX_PATH_SEGMENTS = 32
_MAX_ID_LENGTH = 512
_json_value_adapter: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


@dataclass(frozen=True, slots=True)
class CompiledTraceContract:
    definition: TraceContract
    paths: Mapping[str, CompiledPath]
    metadata_paths: Mapping[str, CompiledPath]
    message_paths: Mapping[str, CompiledPath | None]


@dataclass(frozen=True, slots=True)
class _TraceValues:
    task_id: str
    trial_id: str | None
    trace_id: str
    pairing_key: str | None
    outcome_source: JsonScalar
    outcome: CanonicalOutcome
    score: float | None
    latency_ms: float | None
    token_usage: int | None
    cost_usd: float | None
    error: JsonValue
    metadata: dict[str, JsonScalar]
    diagnostics: list[TraceDiagnostic]


def canonical_json_bytes(value: object) -> bytes:
    """Serialize a JSON-compatible value with stable keys and strict finite numbers."""
    serializable = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(
        serializable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def compile_contract(contract: TraceContract | Mapping[str, object]) -> CompiledTraceContract:
    """Parse and statically validate a versioned trace contract."""
    try:
        definition = (
            contract
            if isinstance(contract, (RunRowsContract, EventRowsContract))
            else trace_contract_adapter.validate_python(contract)
        )
    except PydanticValidationError as exc:
        raise TraceContractError(
            detail={"reason": "schema_invalid", "errors": exc.error_count()}
        ) from exc

    base_names = (
        "task_id",
        "trial_id",
        "trace_id",
        "pairing_key",
        "outcome",
        "score",
        "latency_ms",
        "token_usage",
        "cost_usd",
        "error",
    )
    paths: dict[str, CompiledPath] = {}
    for field_name in base_names:
        raw_path = getattr(definition, field_name)
        if raw_path is not None:
            paths[field_name] = _compile_path(raw_path, field_name=field_name)

    metadata_paths: dict[str, CompiledPath] = {}
    for key, path in definition.metadata.items():
        if _is_sensitive_segment(key):
            raise TraceContractError(detail={"field": "metadata", "reason": "sensitive_mapping"})
        metadata_paths[key] = _compile_path(path, field_name=f"metadata.{key}")
    if isinstance(definition, RunRowsContract):
        paths["messages"] = _compile_path(definition.messages, field_name="messages")
        mapping_values = definition.message_mapping.model_dump()
    else:
        paths["event_index"] = _compile_path(definition.event_index, field_name="event_index")
        mapping_values = definition.event_mapping.model_dump()
    message_paths = {
        key: None if path is None else _compile_path(path, field_name=f"mapping.{key}")
        for key, path in mapping_values.items()
    }
    return CompiledTraceContract(
        definition=definition,
        paths=MappingProxyType(paths),
        metadata_paths=MappingProxyType(metadata_paths),
        message_paths=MappingProxyType(message_paths),
    )


def extract_path(value: object, path: str | CompiledPath) -> object:
    """Extract an object-only dotted path without expressions or array traversal."""
    compiled = _compile_path(path, field_name="path") if isinstance(path, str) else path
    current = value
    for segment_index, segment in enumerate(compiled):
        if not isinstance(current, Mapping):
            raise TraceContractError(
                code="TRACE_CONTRACT_PATH_INVALID",
                detail={
                    "path": ".".join(compiled),
                    "segment_index": segment_index,
                    "reason": "intermediate_not_object",
                },
            )
        if segment not in current:
            raise TraceContractError(
                code="TRACE_CONTRACT_PATH_INVALID",
                detail={
                    "path": ".".join(compiled),
                    "segment_index": segment_index,
                    "reason": "path_missing",
                },
            )
        current = current[segment]
    return current


def project_source_row(
    row: Mapping[str, object], contract: CompiledTraceContract
) -> dict[str, object]:
    """Copy only contract-declared event-row paths into a temporary projection."""
    if not isinstance(contract.definition, EventRowsContract):
        raise TraceContractError(detail={"reason": "source_layout_mismatch"})
    projected: dict[str, object] = {}
    declared_paths = [
        *contract.paths.values(),
        *contract.metadata_paths.values(),
        *(path for path in contract.message_paths.values() if path is not None),
    ]
    for path in declared_paths:
        try:
            value = extract_path(row, path)
        except TraceContractError:
            continue
        _assign_projected_path(projected, path, value)
    return projected


def _assign_projected_path(projected: dict[str, object], path: CompiledPath, value: object) -> None:
    current = projected
    for segment in path[:-1]:
        child = current.get(segment)
        if not isinstance(child, dict):
            child = {}
            current[segment] = child
        current = child
    current[path[-1]] = value


def normalize_run_row(
    row: Mapping[str, object],
    contract: CompiledTraceContract,
    *,
    query_id: int,
    row_identity: str,
    source_row_index: int = 0,
) -> NormalizedRun:
    """Normalize one row-per-run source row into run-row/v1."""
    if not isinstance(contract.definition, RunRowsContract):
        raise TraceContractError(detail={"reason": "source_layout_mismatch"})
    trace_values = _normalize_trace_values(row, contract, source_row_index)
    diagnostics = trace_values.diagnostics
    raw_messages = _required_value(row, contract.paths["messages"], source_row_index)
    if not isinstance(raw_messages, list):
        _row_error(contract.paths["messages"], source_row_index, "messages_not_array")

    messages = [
        _normalize_message(
            message,
            event_index=index,
            contract=contract,
            query_id=query_id,
            row_identity=row_identity,
            json_path=f"{'.'.join(contract.paths['messages'])}[{index}]",
            source_row_index=source_row_index,
            diagnostics=diagnostics,
            require_role=True,
        )
        for index, message in enumerate(raw_messages)
    ]
    run = _build_run(trace_values, messages)
    return NormalizedRun(run=run, diagnostics=diagnostics)


def aggregate_event_rows(
    rows: Sequence[Mapping[str, object]],
    contract: CompiledTraceContract,
    *,
    query_id: int,
    row_identities: Sequence[str],
    source_row_indexes: Sequence[int] | None = None,
) -> list[NormalizedRun]:
    """Group event rows by trace id while enforcing trace-level consistency."""
    if not isinstance(contract.definition, EventRowsContract):
        raise TraceContractError(detail={"reason": "source_layout_mismatch"})
    active_source_indexes = (
        list(range(len(rows))) if source_row_indexes is None else list(source_row_indexes)
    )
    if len(rows) != len(row_identities) or len(rows) != len(active_source_indexes):
        raise TraceContractError(detail={"reason": "row_identity_count_mismatch"})

    grouped: dict[str, list[tuple[int, Mapping[str, object], str]]] = defaultdict(list)
    for source_row_index, row, row_identity in zip(
        active_source_indexes, rows, row_identities, strict=True
    ):
        trace_id = _normalize_identifier(
            _required_value(row, contract.paths["trace_id"], source_row_index),
            contract.paths["trace_id"],
            source_row_index,
            required=True,
        )
        assert trace_id is not None
        grouped[trace_id].append((source_row_index, row, row_identity))

    normalized: list[NormalizedRun] = []
    for trace_id in sorted(grouped):
        group = grouped[trace_id]
        first_index, first_row, _ = group[0]
        trace_values = _normalize_trace_values(first_row, contract, first_index)
        diagnostics: list[TraceDiagnostic] = []
        indexed_messages: list[tuple[int | str, CanonicalMessage]] = []
        seen_indexes: set[int | str] = set()
        index_type: type[int] | type[str] | None = None
        for source_row_index, row, row_identity in group:
            current_values = _normalize_trace_values(row, contract, source_row_index)
            diagnostics.extend(current_values.diagnostics)
            if canonical_json_bytes(_trace_value_payload(current_values)) != canonical_json_bytes(
                _trace_value_payload(trace_values)
            ):
                _row_error(
                    contract.paths["trace_id"],
                    source_row_index,
                    "trace_level_field_inconsistent",
                )
            event_index = _normalize_event_index(
                _required_value(row, contract.paths["event_index"], source_row_index),
                contract.paths["event_index"],
                source_row_index,
            )
            if event_index in seen_indexes:
                _row_error(contract.paths["event_index"], source_row_index, "duplicate_event_index")
            seen_indexes.add(event_index)
            current_type = type(event_index)
            if index_type is None:
                index_type = current_type
            elif current_type is not index_type:
                _row_error(
                    contract.paths["event_index"], source_row_index, "mixed_event_index_types"
                )
            message = _normalize_message(
                row,
                event_index=event_index,
                contract=contract,
                query_id=query_id,
                row_identity=row_identity,
                json_path=None,
                source_row_index=source_row_index,
                diagnostics=diagnostics,
                require_role=False,
            )
            indexed_messages.append((event_index, message))
        indexed_messages.sort(key=lambda item: item[0])
        canonical_messages = [
            message.model_copy(update={"event_index": position})
            for position, (_, message) in enumerate(indexed_messages)
        ]
        normalized.append(
            NormalizedRun(
                run=_build_run(trace_values, canonical_messages),
                diagnostics=diagnostics,
            )
        )
    return normalized


def normalize_source_rows(
    rows: Sequence[Mapping[str, object]],
    contract: CompiledTraceContract,
    *,
    query_id: int,
    row_identities: Sequence[str],
) -> NormalizationBatch:
    """Normalize a source result and validate run-level uniqueness invariants."""
    if len(rows) != len(row_identities):
        raise TraceContractError(detail={"reason": "row_identity_count_mismatch"})
    if isinstance(contract.definition, RunRowsContract):
        normalized = [
            normalize_run_row(
                row,
                contract,
                query_id=query_id,
                row_identity=row_identities[index],
                source_row_index=index,
            )
            for index, row in enumerate(rows)
        ]
    else:
        normalized = aggregate_event_rows(
            rows, contract, query_id=query_id, row_identities=row_identities
        )
    runs = [item.run for item in normalized]
    _validate_run_identities(runs)
    runs.sort(
        key=lambda run: (
            run.task_id,
            run.trial_id is not None,
            run.trial_id or "",
            run.trace_id,
        )
    )
    pairing_count = sum(run.pairing_key is not None for run in runs)
    pairing_coverage = pairing_count / len(runs) if runs else 0.0
    return NormalizationBatch(
        runs=runs,
        diagnostics=[diagnostic for item in normalized for diagnostic in item.diagnostics],
        source_row_count=len(rows),
        valid_run_count=len(runs),
        pairing_key_field_coverage=pairing_coverage,
    )


def _compile_path(path: str, *, field_name: str) -> CompiledPath:
    if not path or path != path.strip() or any(token in path for token in "[]$()*"):
        raise TraceContractError(detail={"field": field_name, "reason": "path_invalid"})
    segments = tuple(path.split("."))
    if any(not segment for segment in segments):
        raise TraceContractError(detail={"field": field_name, "reason": "path_invalid"})
    if len(path) > _MAX_PATH_LENGTH or len(segments) > _MAX_PATH_SEGMENTS:
        raise TraceContractError(detail={"field": field_name, "reason": "path_too_long"})
    if any(_is_sensitive_segment(segment) for segment in segments):
        raise TraceContractError(detail={"field": field_name, "reason": "sensitive_mapping"})
    return segments


def _normalize_segment(segment: str) -> str:
    return "".join(character for character in segment.casefold() if character.isalnum())


def _is_sensitive_segment(segment: str) -> bool:
    normalized = _normalize_segment(segment)
    sensitive_markers = (
        "password",
        "passwd",
        "apikey",
        "apitoken",
        "authtoken",
        "bearertoken",
        "secretkey",
        "privatekey",
        "accesstoken",
        "refreshtoken",
        "credential",
        "authorization",
    )
    return (
        normalized in _SENSITIVE_SEGMENTS
        or normalized.endswith("secret")
        or any(marker in normalized for marker in sensitive_markers)
    )


def _required_value(row: Mapping[str, object], path: CompiledPath, source_row_index: int) -> object:
    try:
        return extract_path(row, path)
    except TraceContractError as exc:
        raise SnapshotRowError(
            detail={
                "path": ".".join(path),
                "source_row_index": source_row_index,
                "reason": exc.detail.get("reason") if exc.detail else "path_invalid",
            }
        ) from exc


def _optional_value(
    row: Mapping[str, object], path: CompiledPath | None, source_row_index: int
) -> object | None:
    if path is None:
        return None
    try:
        return extract_path(row, path)
    except TraceContractError as exc:
        if exc.detail is not None and exc.detail.get("reason") == "path_missing":
            return None
        raise SnapshotRowError(
            detail={
                "path": ".".join(path),
                "source_row_index": source_row_index,
                "reason": exc.detail.get("reason") if exc.detail else "path_invalid",
            }
        ) from exc


def _trace_optional_value(
    row: Mapping[str, object], path: CompiledPath | None, source_row_index: int
) -> object | None:
    if path is None:
        return None
    return _required_value(row, path, source_row_index)


def _normalize_trace_values(
    row: Mapping[str, object], contract: CompiledTraceContract, source_row_index: int
) -> _TraceValues:
    diagnostics: list[TraceDiagnostic] = []
    task_id = _normalize_identifier(
        _required_value(row, contract.paths["task_id"], source_row_index),
        contract.paths["task_id"],
        source_row_index,
        required=True,
    )
    trace_id = _normalize_identifier(
        _required_value(row, contract.paths["trace_id"], source_row_index),
        contract.paths["trace_id"],
        source_row_index,
        required=True,
    )
    trial_id = _identifier_from_optional_path(row, contract.paths.get("trial_id"), source_row_index)
    pairing_key = _identifier_from_optional_path(
        row, contract.paths.get("pairing_key"), source_row_index
    )
    raw_outcome = _required_value(row, contract.paths["outcome"], source_row_index)
    outcome_source = _normalize_json_scalar(
        raw_outcome,
        contract.paths["outcome"],
        source_row_index,
        reason="outcome_type_invalid",
    )
    outcome = _map_outcome(
        outcome_source,
        contract.definition.outcome_mapping,
        path=contract.paths["outcome"],
        source_row_index=source_row_index,
        diagnostics=diagnostics,
    )
    metadata: dict[str, JsonScalar] = {}
    for key, path in contract.metadata_paths.items():
        value = _required_value(row, path, source_row_index)
        metadata[key] = _normalize_json_scalar(
            value, path, source_row_index, reason="metadata_not_scalar"
        )
    assert task_id is not None and trace_id is not None
    return _TraceValues(
        task_id=task_id,
        trial_id=trial_id,
        trace_id=trace_id,
        pairing_key=pairing_key,
        outcome_source=outcome_source,
        outcome=outcome,
        score=_optional_non_negative_number(row, contract.paths.get("score"), source_row_index),
        latency_ms=_optional_non_negative_number(
            row, contract.paths.get("latency_ms"), source_row_index
        ),
        token_usage=_optional_non_negative_integer(
            row, contract.paths.get("token_usage"), source_row_index
        ),
        cost_usd=_optional_non_negative_number(
            row, contract.paths.get("cost_usd"), source_row_index
        ),
        error=_normalize_json_value(
            _trace_optional_value(row, contract.paths.get("error"), source_row_index),
            contract.paths.get("error"),
            source_row_index,
        ),
        metadata=metadata,
        diagnostics=diagnostics,
    )


def _trace_value_payload(trace_values: _TraceValues) -> dict[str, object]:
    return {
        "task_id": trace_values.task_id,
        "trial_id": trace_values.trial_id,
        "trace_id": trace_values.trace_id,
        "pairing_key": trace_values.pairing_key,
        "outcome_source": trace_values.outcome_source,
        "outcome": trace_values.outcome,
        "score": trace_values.score,
        "latency_ms": trace_values.latency_ms,
        "token_usage": trace_values.token_usage,
        "cost_usd": trace_values.cost_usd,
        "error": trace_values.error,
        "metadata": trace_values.metadata,
    }


def _build_run(trace_values: _TraceValues, messages: list[CanonicalMessage]) -> CanonicalRunRow:
    return CanonicalRunRow(
        task_id=trace_values.task_id,
        trial_id=trace_values.trial_id,
        trace_id=trace_values.trace_id,
        pairing_key=trace_values.pairing_key,
        outcome=trace_values.outcome,
        score=trace_values.score,
        metrics=RunMetrics(
            latency_ms=trace_values.latency_ms,
            token_usage=trace_values.token_usage,
            cost_usd=trace_values.cost_usd,
        ),
        messages=messages,
        error=trace_values.error,
        metadata=trace_values.metadata,
    )


def _normalize_message(
    value: object,
    *,
    event_index: int | str,
    contract: CompiledTraceContract,
    query_id: int,
    row_identity: str,
    json_path: str | None,
    source_row_index: int,
    diagnostics: list[TraceDiagnostic],
    require_role: bool,
) -> CanonicalMessage:
    if query_id <= 0:
        _row_error(("query_id",), source_row_index, "query_id_invalid")
    if not row_identity:
        _row_error(("row_identity",), source_row_index, "row_identity_empty")
    if len(row_identity) > _MAX_ID_LENGTH:
        _row_error(("row_identity",), source_row_index, "row_identity_too_long")
    if not isinstance(value, Mapping):
        _row_error(("messages",), source_row_index, "message_not_object")
    content_path = contract.message_paths["content"]
    assert content_path is not None
    content = _normalize_json_value(
        _required_value(value, content_path, source_row_index),
        content_path,
        source_row_index,
    )
    role = _optional_text(
        _optional_value(value, contract.message_paths.get("role"), source_row_index),
        contract.message_paths.get("role"),
        source_row_index,
    )
    kind = _optional_text(
        _optional_value(value, contract.message_paths.get("kind"), source_row_index),
        contract.message_paths.get("kind"),
        source_row_index,
    )
    if require_role and role is None:
        _row_error(contract.message_paths["role"] or ("role",), source_row_index, "role_missing")
    if not require_role and role is None and kind is None:
        _row_error(("event_mapping",), source_row_index, "role_and_kind_missing")
    status_path = contract.message_paths.get("status")
    status = _map_status(
        _optional_value(value, status_path, source_row_index),
        contract.definition.status_mapping,
        path=status_path,
        source_row_index=source_row_index,
        diagnostics=diagnostics,
    )
    parent_event_id = _optional_text_from_mapping(
        value, contract, "parent_event_id", source_row_index
    )
    if parent_event_id is not None:
        diagnostics.append(
            TraceDiagnostic(
                code="HIERARCHY_NOT_RECONSTRUCTED",
                path=".".join(
                    contract.message_paths.get("parent_event_id") or ("parent_event_id",)
                ),
                source_row_index=source_row_index,
            )
        )
    return CanonicalMessage(
        event_index=event_index,
        kind=kind,
        role=role,
        content=content,
        name=_optional_text_from_mapping(value, contract, "name", source_row_index),
        tool_call_id=_optional_text_from_mapping(value, contract, "tool_call_id", source_row_index),
        tool_calls=_normalize_json_value(
            _optional_value(value, contract.message_paths.get("tool_calls"), source_row_index),
            contract.message_paths.get("tool_calls"),
            source_row_index,
        ),
        status=status,
        parent_event_id=parent_event_id,
        timestamp=_optional_timestamp_from_mapping(value, contract, source_row_index),
        latency_ms=_optional_number_from_mapping(value, contract, "latency_ms", source_row_index),
        tokens_in=_optional_integer_from_mapping(value, contract, "tokens_in", source_row_index),
        tokens_out=_optional_integer_from_mapping(value, contract, "tokens_out", source_row_index),
        cost_usd=_optional_number_from_mapping(value, contract, "cost_usd", source_row_index),
        source_ref=SourceRef(
            query_id=query_id,
            row_identity=row_identity,
            json_path=json_path,
        ),
    )


def _normalize_identifier(
    value: object,
    path: CompiledPath,
    source_row_index: int,
    *,
    required: bool,
) -> str | None:
    if value is None:
        if required:
            _row_error(path, source_row_index, "id_missing")
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        _row_error(path, source_row_index, "id_type_invalid")
    if isinstance(value, (float, Decimal)) and not math.isfinite(float(value)):
        _row_error(path, source_row_index, "id_type_invalid")
    normalized = str(value).strip()
    if not normalized:
        _row_error(path, source_row_index, "id_empty")
    if len(normalized) > _MAX_ID_LENGTH:
        _row_error(path, source_row_index, "id_too_long")
    return normalized


def _identifier_from_optional_path(
    row: Mapping[str, object], path: CompiledPath | None, source_row_index: int
) -> str | None:
    if path is None:
        return None
    return _normalize_identifier(
        _required_value(row, path, source_row_index),
        path,
        source_row_index,
        required=False,
    )


def _normalize_event_index(value: object, path: CompiledPath, source_row_index: int) -> int | str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        _row_error(path, source_row_index, "event_index_type_invalid")
    if isinstance(value, str) and not value.strip():
        _row_error(path, source_row_index, "event_index_empty")
    return value


def _map_outcome(
    value: object,
    mapping: OutcomeMapping,
    *,
    path: CompiledPath,
    source_row_index: int,
    diagnostics: list[TraceDiagnostic],
) -> CanonicalOutcome:
    if _mapping_contains(mapping.success_values, value, mapping.case_sensitive):
        return "success"
    if _mapping_contains(mapping.failure_values, value, mapping.case_sensitive):
        return "failure"
    if _mapping_contains(mapping.abstain_values, value, mapping.case_sensitive):
        return "abstain"
    diagnostics.append(
        TraceDiagnostic(
            code="OUTCOME_UNMAPPED",
            path=".".join(path),
            source_row_index=source_row_index,
        )
    )
    return "unknown"


def _map_status(
    value: object | None,
    mapping: EventStatusMapping | None,
    *,
    path: CompiledPath | None,
    source_row_index: int,
    diagnostics: list[TraceDiagnostic],
) -> CanonicalEventStatus:
    if value is None:
        return "unknown"
    status: CanonicalEventStatus | None = None
    if mapping is None and value == "ok":
        status = "ok"
    elif mapping is None and value == "error":
        status = "error"
    elif mapping is None and value == "cancelled":
        status = "cancelled"
    elif mapping is None and value == "unknown":
        status = "unknown"
    if mapping is not None:
        if _mapping_contains(mapping.ok_values, value, mapping.case_sensitive):
            status = "ok"
        elif _mapping_contains(mapping.error_values, value, mapping.case_sensitive):
            status = "error"
        elif _mapping_contains(mapping.cancelled_values, value, mapping.case_sensitive):
            status = "cancelled"
    if status is not None:
        return status
    diagnostics.append(
        TraceDiagnostic(
            code="EVENT_STATUS_UNMAPPED",
            path=".".join(path or ("status",)),
            source_row_index=source_row_index,
        )
    )
    return "unknown"


def _mapping_contains(
    values: Sequence[JsonScalar], candidate: object, case_sensitive: bool
) -> bool:
    if not _is_json_scalar(candidate):
        return False
    comparable_candidate = candidate
    if isinstance(candidate, str) and not case_sensitive:
        comparable_candidate = candidate.casefold()
    for value in values:
        comparable_value = (
            value.casefold() if isinstance(value, str) and not case_sensitive else value
        )
        if (
            type(comparable_value) is type(comparable_candidate)
            and comparable_value == comparable_candidate
        ):
            return True
    return False


def _optional_non_negative_number(
    row: Mapping[str, object],
    path: CompiledPath | None,
    source_row_index: int,
    *,
    allow_missing: bool = False,
) -> float | None:
    value = (
        _optional_value(row, path, source_row_index)
        if allow_missing
        else _trace_optional_value(row, path, source_row_index)
    )
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        _row_error(path or ("metric",), source_row_index, "metric_type_invalid")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        _row_error(path or ("metric",), source_row_index, "metric_value_invalid")
    return normalized


def _optional_non_negative_integer(
    row: Mapping[str, object],
    path: CompiledPath | None,
    source_row_index: int,
    *,
    allow_missing: bool = False,
) -> int | None:
    value = (
        _optional_value(row, path, source_row_index)
        if allow_missing
        else _trace_optional_value(row, path, source_row_index)
    )
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _row_error(path or ("metric",), source_row_index, "metric_integer_invalid")
    return value


def _optional_number_from_mapping(
    value: Mapping[str, object],
    contract: CompiledTraceContract,
    field_name: str,
    source_row_index: int,
) -> float | None:
    path = contract.message_paths.get(field_name)
    return _optional_non_negative_number(value, path, source_row_index, allow_missing=True)


def _optional_integer_from_mapping(
    value: Mapping[str, object],
    contract: CompiledTraceContract,
    field_name: str,
    source_row_index: int,
) -> int | None:
    path = contract.message_paths.get(field_name)
    return _optional_non_negative_integer(value, path, source_row_index, allow_missing=True)


def _optional_text_from_mapping(
    value: Mapping[str, object],
    contract: CompiledTraceContract,
    field_name: str,
    source_row_index: int,
) -> str | None:
    path = contract.message_paths.get(field_name)
    return _optional_text(_optional_value(value, path, source_row_index), path, source_row_index)


def _optional_text(
    value: object | None, path: CompiledPath | None, source_row_index: int
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        _row_error(path or ("text",), source_row_index, "text_type_invalid")
    return value


def _optional_timestamp_from_mapping(
    value: Mapping[str, object],
    contract: CompiledTraceContract,
    source_row_index: int,
) -> str | None:
    path = contract.message_paths.get("timestamp")
    raw = _optional_value(value, path, source_row_index)
    if raw is None:
        return None
    if isinstance(raw, datetime):
        parsed = raw
    elif isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise SnapshotRowError(
                detail={
                    "path": ".".join(path or ("timestamp",)),
                    "source_row_index": source_row_index,
                    "reason": "timestamp_invalid",
                }
            ) from exc
    else:
        _row_error(path or ("timestamp",), source_row_index, "timestamp_type_invalid")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    normalized = parsed.astimezone(UTC).isoformat()
    return normalized.replace("+00:00", "Z")


def _normalize_json_value(
    value: object | None, path: CompiledPath | None, source_row_index: int
) -> JsonValue:
    try:
        normalized = _json_value_adapter.validate_python(value)
        canonical_json_bytes(normalized)
    except (PydanticValidationError, TypeError, ValueError, OverflowError) as exc:
        raise SnapshotRowError(
            detail={
                "path": ".".join(path or ("value",)),
                "source_row_index": source_row_index,
                "reason": "json_value_invalid",
            }
        ) from exc
    return normalized


def _is_json_scalar(value: object) -> TypeGuard[JsonScalar]:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    return isinstance(value, float) and math.isfinite(value)


def _normalize_json_scalar(
    value: object,
    path: CompiledPath,
    source_row_index: int,
    *,
    reason: str,
) -> JsonScalar:
    if isinstance(value, Decimal):
        if not value.is_finite():
            _row_error(path, source_row_index, reason)
        return int(value) if value == value.to_integral_value() else float(value)
    if not _is_json_scalar(value):
        _row_error(path, source_row_index, reason)
    return value


def _validate_run_identities(runs: Sequence[CanonicalRunRow]) -> None:
    trace_ids: set[str] = set()
    task_trials: set[tuple[str, str]] = set()
    tasks_without_trials: set[str] = set()
    pairing_keys: set[tuple[str, str]] = set()
    for source_row_index, run in enumerate(runs):
        if run.trace_id in trace_ids:
            _row_error(("trace_id",), source_row_index, "duplicate_trace_id")
        trace_ids.add(run.trace_id)
        if run.trial_id is None:
            if run.task_id in tasks_without_trials:
                _row_error(("task_id",), source_row_index, "duplicate_task_without_trial")
            tasks_without_trials.add(run.task_id)
        else:
            task_trial = (run.task_id, run.trial_id)
            if task_trial in task_trials:
                _row_error(("trial_id",), source_row_index, "duplicate_task_trial")
            task_trials.add(task_trial)
        if run.pairing_key is not None:
            pairing_key = (run.task_id, run.pairing_key)
            if pairing_key in pairing_keys:
                _row_error(("pairing_key",), source_row_index, "duplicate_pairing_key")
            pairing_keys.add(pairing_key)


def _row_error(path: CompiledPath, source_row_index: int, reason: str) -> NoReturn:
    raise SnapshotRowError(
        detail={
            "path": ".".join(path),
            "source_row_index": source_row_index,
            "reason": reason,
        }
    )
