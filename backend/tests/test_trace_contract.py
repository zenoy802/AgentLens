from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.errors import SnapshotRowError, TraceContractError
from app.schemas.trace_contract import OutcomeMapping
from app.services.trace_contract import (
    aggregate_event_rows,
    canonical_json_bytes,
    compile_contract,
    extract_path,
    normalize_run_row,
    normalize_source_rows,
)
from scripts.generate_regression_fixtures import QUICK_SPEC, generate_fixture

_DECIMAL_LATENCY = Decimal("1000.25")
_PARTIAL_PAIRING_COVERAGE = 0.5


def _row_identities(rows: list[dict[str, object]]) -> list[str]:
    return [str(row["row_identity"]) for row in rows]


def _semantic_dump(run: Any) -> dict[str, Any]:
    return run.model_dump(exclude={"messages": {"__all__": {"source_ref"}}})


def test_run_and_event_layouts_normalize_to_equivalent_canonical_runs() -> None:
    fixture = generate_fixture(QUICK_SPEC)
    run_contract = compile_contract(fixture.contracts["run_rows"])
    event_contract = compile_contract(fixture.contracts["event_rows"])

    run_batch = normalize_source_rows(
        fixture.baseline_run_rows,
        run_contract,
        query_id=42,
        row_identities=_row_identities(fixture.baseline_run_rows),
    )
    event_batch = normalize_source_rows(
        fixture.baseline_event_rows,
        event_contract,
        query_id=42,
        row_identities=_row_identities(fixture.baseline_event_rows),
    )

    assert [_semantic_dump(run) for run in run_batch.runs] == [
        _semantic_dump(run) for run in event_batch.runs
    ]
    assert run_batch.valid_run_count == QUICK_SPEC.task_count * QUICK_SPEC.baseline_trials
    assert event_batch.valid_run_count == run_batch.valid_run_count
    assert run_batch.pairing_key_field_coverage == 1.0
    assert event_batch.pairing_key_field_coverage == 1.0


@pytest.mark.parametrize("index_kind", ["one_based", "stable_string"])
def test_event_rows_use_layout_independent_canonical_positions(index_kind: str) -> None:
    fixture = generate_fixture(QUICK_SPEC)
    run_row = fixture.baseline_run_rows[0]
    trace_id = run_row["run_uuid"]
    event_rows = [
        deepcopy(row) for row in fixture.baseline_event_rows if row["run_uuid"] == trace_id
    ]
    for position, row in enumerate(event_rows):
        row["step_index"] = (
            position + 1 if index_kind == "one_based" else f"stable-{position + 1:03d}"
        )

    run = normalize_run_row(
        run_row,
        compile_contract(fixture.contracts["run_rows"]),
        query_id=42,
        row_identity=str(run_row["row_identity"]),
    ).run
    event = aggregate_event_rows(
        event_rows,
        compile_contract(fixture.contracts["event_rows"]),
        query_id=42,
        row_identities=_row_identities(event_rows),
    )[0].run

    assert _semantic_dump(event) == _semantic_dump(run)
    assert [message.event_index for message in event.messages] == list(range(len(event_rows)))


def test_unknown_outcome_is_not_truthy_guessed_and_has_diagnostic() -> None:
    fixture = generate_fixture(QUICK_SPEC)
    row = deepcopy(fixture.baseline_run_rows[0])
    result = row["result"]
    assert isinstance(result, dict)
    result["outcome"] = "yes"

    batch = normalize_source_rows(
        [row],
        compile_contract(fixture.contracts["run_rows"]),
        query_id=7,
        row_identities=[str(row["row_identity"])],
    )

    assert batch.runs[0].outcome == "unknown"
    assert [diagnostic.code for diagnostic in batch.diagnostics] == ["OUTCOME_UNMAPPED"]
    assert batch.diagnostics[0].path == "result.outcome"


def test_explicit_status_mapping_and_unmapped_status_are_diagnostic() -> None:
    fixture = generate_fixture(QUICK_SPEC)
    definition = deepcopy(fixture.contracts["run_rows"])
    definition["status_mapping"] = {
        "ok_values": ["DONE"],
        "error_values": ["FAILED"],
        "cancelled_values": [],
        "case_sensitive": False,
    }
    row = deepcopy(fixture.baseline_run_rows[0])
    payload = row["payload"]
    assert isinstance(payload, dict)
    messages = payload["messages"]
    assert isinstance(messages, list)
    assert isinstance(messages[0], dict) and isinstance(messages[1], dict)
    messages[0]["status"] = "done"
    messages[1]["status"] = "unexpected"

    normalized = normalize_run_row(
        row,
        compile_contract(definition),
        query_id=1,
        row_identity=str(row["row_identity"]),
    )

    assert normalized.run.messages[0].status == "ok"
    assert normalized.run.messages[1].status == "unknown"
    assert "EVENT_STATUS_UNMAPPED" in {diagnostic.code for diagnostic in normalized.diagnostics}


def test_outcome_mapping_rejects_typed_and_case_folded_overlap() -> None:
    with pytest.raises(PydanticValidationError, match="overlap"):
        OutcomeMapping(success_values=["YES"], failure_values=["yes"], case_sensitive=False)

    mapping = OutcomeMapping(success_values=[True], failure_values=[1])
    assert mapping.success_values == [True]
    assert mapping.failure_values == [1]

    with pytest.raises(PydanticValidationError, match="overlap"):
        OutcomeMapping(success_values=[-0.0], failure_values=[0.0])


def test_compile_contract_wraps_schema_errors_without_echoing_payload() -> None:
    with pytest.raises(TraceContractError) as exc_info:
        compile_contract({"source_layout": "run_rows", "password": "do-not-echo"})

    assert exc_info.value.detail == {"reason": "schema_invalid", "errors": 7}
    assert "do-not-echo" not in str(exc_info.value.detail)


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("payload..messages", "path_invalid"),
        ("payload.messages[0]", "path_invalid"),
        ("credentials.api_key", "sensitive_mapping"),
        ("connection.db_password_enc", "sensitive_mapping"),
        ("provider.client_secret", "sensitive_mapping"),
    ],
)
def test_compile_contract_rejects_path_boundaries_and_sensitive_fields(
    path: str, reason: str
) -> None:
    fixture = generate_fixture(QUICK_SPEC)
    definition = deepcopy(fixture.contracts["run_rows"])
    definition["messages"] = path

    with pytest.raises(TraceContractError) as exc_info:
        compile_contract(definition)

    assert exc_info.value.detail == {"field": "messages", "reason": reason}


def test_compile_contract_rejects_sensitive_metadata_output_keys() -> None:
    fixture = generate_fixture(QUICK_SPEC)
    definition = deepcopy(fixture.contracts["run_rows"])
    definition["metadata"] = {"client_secret": "model"}

    with pytest.raises(TraceContractError) as exc_info:
        compile_contract(definition)

    assert exc_info.value.detail == {"field": "metadata", "reason": "sensitive_mapping"}


def test_extract_path_reports_missing_and_non_object_without_values() -> None:
    with pytest.raises(TraceContractError) as missing:
        extract_path({"payload": {}}, "payload.messages")
    assert missing.value.detail == {
        "path": "payload.messages",
        "segment_index": 1,
        "reason": "path_missing",
    }

    with pytest.raises(TraceContractError) as non_object:
        extract_path({"payload": []}, "payload.messages")
    assert non_object.value.detail == {
        "path": "payload.messages",
        "segment_index": 1,
        "reason": "intermediate_not_object",
    }


def test_event_rows_reject_duplicate_index_and_trace_level_inconsistency() -> None:
    fixture = generate_fixture(QUICK_SPEC)
    contract = compile_contract(fixture.contracts["event_rows"])
    trace_id = fixture.baseline_event_rows[0]["run_uuid"]
    rows = [deepcopy(row) for row in fixture.baseline_event_rows if row["run_uuid"] == trace_id]
    rows[1]["step_index"] = rows[0]["step_index"]

    with pytest.raises(SnapshotRowError) as duplicate:
        normalize_source_rows(
            rows,
            contract,
            query_id=1,
            row_identities=_row_identities(rows),
        )
    assert duplicate.value.detail is not None
    assert duplicate.value.detail["reason"] == "duplicate_event_index"

    inconsistent = [
        deepcopy(row) for row in fixture.baseline_event_rows if row["run_uuid"] == trace_id
    ]
    inconsistent[1]["outcome"] = "failure"
    with pytest.raises(SnapshotRowError) as mismatch:
        normalize_source_rows(
            inconsistent,
            contract,
            query_id=1,
            row_identities=_row_identities(inconsistent),
        )
    assert mismatch.value.detail is not None
    assert mismatch.value.detail["reason"] == "trace_level_field_inconsistent"


def test_event_rows_reject_mixed_index_types_and_layout_mismatch() -> None:
    fixture = generate_fixture(QUICK_SPEC)
    event_contract = compile_contract(fixture.contracts["event_rows"])
    run_contract = compile_contract(fixture.contracts["run_rows"])
    trace_id = fixture.baseline_event_rows[0]["run_uuid"]
    rows = [deepcopy(row) for row in fixture.baseline_event_rows if row["run_uuid"] == trace_id]
    rows[1]["step_index"] = "1"

    with pytest.raises(SnapshotRowError) as mixed:
        aggregate_event_rows(
            rows,
            event_contract,
            query_id=1,
            row_identities=_row_identities(rows),
        )
    assert mixed.value.detail is not None
    assert mixed.value.detail["reason"] == "mixed_event_index_types"

    with pytest.raises(TraceContractError, match="Trace contract validation failed"):
        aggregate_event_rows([], run_contract, query_id=1, row_identities=[])
    with pytest.raises(TraceContractError, match="Trace contract validation failed"):
        normalize_run_row(
            rows[0], event_contract, query_id=1, row_identity=str(rows[0]["row_identity"])
        )


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("run_uuid", "duplicate_trace_id"),
        ("attempt", "duplicate_task_trial"),
        ("shared_seed", "duplicate_pairing_key"),
    ],
)
def test_run_rows_reject_duplicate_stable_ids_and_keys(field: str, reason: str) -> None:
    fixture = generate_fixture(QUICK_SPEC)
    rows = [deepcopy(fixture.baseline_run_rows[0]), deepcopy(fixture.baseline_run_rows[1])]
    rows[1][field] = rows[0][field]
    if field != "run_uuid":
        rows[1]["run_uuid"] = f"unique-{field}"
    if field == "shared_seed":
        rows[1]["attempt"] = "unique-trial"

    with pytest.raises(SnapshotRowError) as exc_info:
        normalize_source_rows(
            rows,
            compile_contract(fixture.contracts["run_rows"]),
            query_id=1,
            row_identities=_row_identities(rows),
        )
    assert exc_info.value.detail is not None
    assert exc_info.value.detail["reason"] == reason


def test_non_finite_or_negative_metrics_are_rejected_safely() -> None:
    fixture = generate_fixture(QUICK_SPEC)
    row = deepcopy(fixture.baseline_run_rows[0])
    metrics = row["metrics"]
    assert isinstance(metrics, dict)
    metrics["latency_ms"] = -1

    with pytest.raises(SnapshotRowError) as exc_info:
        normalize_source_rows(
            [row],
            compile_contract(fixture.contracts["run_rows"]),
            query_id=1,
            row_identities=_row_identities([row]),
        )
    assert exc_info.value.detail == {
        "path": "metrics.latency_ms",
        "source_row_index": 0,
        "reason": "metric_value_invalid",
    }


def test_decimal_metrics_are_normalized_and_mapped_metric_paths_must_exist() -> None:
    fixture = generate_fixture(QUICK_SPEC)
    row = deepcopy(fixture.baseline_run_rows[0])
    metrics = row["metrics"]
    assert isinstance(metrics, dict)
    metrics["latency_ms"] = _DECIMAL_LATENCY
    normalized = normalize_run_row(
        row,
        compile_contract(fixture.contracts["run_rows"]),
        query_id=1,
        row_identity=str(row["row_identity"]),
    )
    assert normalized.run.metrics.latency_ms == float(_DECIMAL_LATENCY)

    del metrics["latency_ms"]
    with pytest.raises(SnapshotRowError) as missing:
        normalize_run_row(
            row,
            compile_contract(fixture.contracts["run_rows"]),
            query_id=1,
            row_identity=str(row["row_identity"]),
        )
    assert missing.value.detail is not None
    assert missing.value.detail["reason"] == "path_missing"


def test_pairing_key_coverage_allows_explicit_nulls() -> None:
    fixture = generate_fixture(QUICK_SPEC)
    rows = [deepcopy(fixture.baseline_run_rows[0]), deepcopy(fixture.baseline_run_rows[1])]
    rows[1]["shared_seed"] = None

    batch = normalize_source_rows(
        rows,
        compile_contract(fixture.contracts["run_rows"]),
        query_id=1,
        row_identities=_row_identities(rows),
    )
    assert batch.pairing_key_field_coverage == _PARTIAL_PAIRING_COVERAGE


def test_canonical_json_bytes_sorts_keys_and_rejects_nan() -> None:
    assert canonical_json_bytes({"b": 1, "a": "雪"}) == b'{"a":"\xe9\x9b\xaa","b":1}'
    with pytest.raises(ValueError, match="Out of range float values"):
        canonical_json_bytes({"value": float("nan")})
