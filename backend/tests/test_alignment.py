from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.schemas.alignment import (
    AlignmentPolicy,
    CanonicalizationPolicy,
    StringScrubberRule,
)
from app.schemas.trace_contract import CanonicalMessage, CanonicalRunRow, SourceRef
from app.services import alignment as alignment_module
from app.services.alignment import align_runs, align_trajectories
from app.services.canonicalization import (
    assistant_events_are_near_match,
    assistant_text_similarity,
    canonicalize_content,
    canonicalize_run,
)

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "alignment_golden.json"
_GOLD_CASES: list[dict[str, Any]] = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
_OVERSIZED_CONTENT_LENGTH = 301
_BANDED_EVENT_COUNT = 600
_NUMERIC_TOLERANCE_COST = 0.25
_EXPECTED_TOKENS_OUT = 7
_TRAILING_DELETE_COUNT = 60
_EXPECTED_VOLATILE_IGNORED_FIELDS = 4
_SAME_KIND_NAME_CHANGE_COST = 0.75


def _message(index: int, payload: dict[str, Any]) -> CanonicalMessage:
    return CanonicalMessage(
        event_index=index,
        source_ref=SourceRef(query_id=1, row_identity=f"row-{index}"),
        **payload,
    )


def _run(trace_id: str, messages: list[dict[str, Any]]) -> CanonicalRunRow:
    return CanonicalRunRow(
        task_id="task-1",
        trace_id=trace_id,
        outcome="success",
        messages=[_message(index, payload) for index, payload in enumerate(messages)],
    )


@pytest.mark.parametrize("case", _GOLD_CASES, ids=[case["name"] for case in _GOLD_CASES])
def test_synthetic_alignment_golden_corpus(case: dict[str, Any]) -> None:
    result = align_runs(_run("baseline", case["baseline"]), _run("candidate", case["candidate"]))

    observed = result.first_observed_divergence
    action = result.first_action_divergence
    assert (observed.category if observed else None) == case["expected_fod"]
    assert (action.category if action else None) == case["expected_fad"]
    assert [step.op for step in result.steps] == case["expected_ops"]
    if case["name"] == "text_then_tool_argument":
        action_step = result.steps[result.first_action_divergence.step_index]  # type: ignore[union-attr]
        assert "$.call_id" not in {diff.path for diff in action_step.field_diffs}
    if case["name"] == "volatile_tool_result":
        assert result.summary.ignored_fields == _EXPECTED_VOLATILE_IGNORED_FIELDS
        assert result.summary.scrubbed_spans > 0
        assert {count.rule_id for count in result.summary.scrubber_counts} >= {
            "localhost_port",
            "process_id",
            "temporary_path",
        }


def test_golden_corpus_reports_exact_and_degraded_coverage_separately() -> None:
    exact_results = [
        align_runs(
            _run(f"b-{case['name']}", case["baseline"]),
            _run(f"c-{case['name']}", case["candidate"]),
        )
        for case in _GOLD_CASES
    ]
    long_messages = [{"role": "assistant", "content": "repeat"}] * 120
    degraded = align_runs(
        _run("long-b", long_messages),
        _run("long-c", long_messages),
        alignment_policy=AlignmentPolicy(degraded_event_limit=100, full_dp_max_events=100),
    )

    exact_coverage = sum(result.quality == "exact" for result in exact_results) / len(exact_results)
    end_to_end = [*exact_results, degraded]
    degraded_coverage = sum(result.quality == "degraded" for result in end_to_end) / len(end_to_end)
    assert exact_coverage == 1.0
    assert degraded.quality == "degraded"
    assert degraded_coverage > 0.0


def test_same_word_reordering_and_short_number_change_are_not_near_matches() -> None:
    reordered = align_runs(
        _run("b", [{"role": "assistant", "content": "alpha beta gamma delta epsilon zeta"}]),
        _run("c", [{"role": "assistant", "content": "zeta epsilon delta gamma beta alpha"}]),
    )
    number = align_runs(
        _run("b2", [{"role": "assistant", "content": "limit 10"}]),
        _run("c2", [{"role": "assistant", "content": "limit 100"}]),
    )

    assert reordered.steps[0].op == "change"
    assert number.steps[0].op == "change"


def test_oversized_content_uses_full_hash_not_truncated_preview() -> None:
    policy = CanonicalizationPolicy(max_content_chars=128)
    common = "x" * 300
    baseline = _run("b", [{"role": "assistant", "content": f"{common}A"}])
    candidate = _run("c", [{"role": "assistant", "content": f"{common}B"}])

    baseline_event = canonicalize_run(baseline, policy).events[0]
    result = align_runs(baseline, candidate, canonicalization_policy=policy)

    assert baseline_event.oversized is True
    assert (
        baseline_event.content["$oversized"]["length"]  # type: ignore[index]
        == _OVERSIZED_CONTENT_LENGTH
    )
    assert result.steps[0].op == "change"


def test_scrubber_does_not_hide_business_path_number_or_error_code() -> None:
    baseline = _run(
        "b",
        [{"role": "tool", "content": "file=/srv/customer/42 timeout=10 error=E401"}],
    )
    candidate = _run(
        "c",
        [{"role": "tool", "content": "file=/srv/customer/43 timeout=11 error=E500"}],
    )

    result = align_runs(baseline, candidate)

    assert result.steps[0].op == "change"
    assert result.first_action_divergence is not None


def test_misleading_unique_anchor_is_rejected_by_cost_guard() -> None:
    repeated_x = [{"role": "assistant", "content": "repeat x"}] * 5
    repeated_y = [{"role": "assistant", "content": "repeat y"}] * 5
    baseline = _run(
        "b",
        [*repeated_x, {"role": "assistant", "content": "unique pivot"}, *repeated_y],
    )
    candidate = _run(
        "c",
        [*repeated_y, {"role": "assistant", "content": "unique pivot"}, *repeated_x],
    )

    result = align_runs(
        baseline,
        candidate,
        alignment_policy=AlignmentPolicy(max_anchor_segment_cost=0.5),
    )

    assert result.summary.rejected_anchors >= 1
    assert any(warning.code == "ANCHOR_REJECTED" for warning in result.warnings)


def test_custom_scrubber_rejects_unsafe_regex_and_limits_replacements() -> None:
    with pytest.raises(ValueError, match="supported RE2-compatible subset"):
        CanonicalizationPolicy.model_validate(
            {
                "string_scrubbers": {
                    "rules": [{"id": "unsafe", "pattern": "(a+)+", "replacement": "x"}]
                }
            }
        )
    policy = CanonicalizationPolicy.model_validate(
        {
            "string_scrubbers": {
                "preset": "none",
                "max_replacements_per_leaf": 2,
                "rules": [{"id": "digits", "pattern": "[0-9]", "replacement": "#"}],
            }
        }
    )
    trajectory = canonicalize_run(_run("b", [{"role": "assistant", "content": "1 2 3"}]), policy)

    assert trajectory.events[0].content == "# # 3"
    assert "scrubber_replacement_limit_reached" in trajectory.events[0].normalization_notes


def test_alignment_json_is_stable_across_python_hash_seeds(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline_path.write_text(
        _run("b", _GOLD_CASES[1]["baseline"]).model_dump_json(), encoding="utf-8"
    )
    candidate_path.write_text(
        _run("c", _GOLD_CASES[1]["candidate"]).model_dump_json(), encoding="utf-8"
    )
    script = (
        "from pathlib import Path;"
        "from app.schemas.trace_contract import CanonicalRunRow;"
        "from app.services.alignment import align_runs;"
        f"b=CanonicalRunRow.model_validate_json(Path({str(baseline_path)!r}).read_text());"
        f"c=CanonicalRunRow.model_validate_json(Path({str(candidate_path)!r}).read_text());"
        "print(align_runs(b,c).model_dump_json())"
    )
    outputs = []
    for seed in ("1", "8675309"):
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = seed
        completed = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        outputs.append(completed.stdout)

    assert outputs[0] == outputs[1]


def test_banded_alignment_handles_six_hundred_repeated_events_exactly() -> None:
    baseline_messages = [
        {"role": "assistant", "content": "same repeated event"}
    ] * _BANDED_EVENT_COUNT
    candidate_messages = list(baseline_messages)
    candidate_messages[_BANDED_EVENT_COUNT // 2] = {
        "role": "assistant",
        "content": "changed repeated event",
    }

    result = align_runs(_run("band-b", baseline_messages), _run("band-c", candidate_messages))

    assert result.quality == "exact"
    assert len(result.steps) == _BANDED_EVENT_COUNT
    assert result.summary.changes == 1


def test_degraded_greedy_alignment_handles_insert_and_delete_rejoin() -> None:
    repeated = [{"role": "assistant", "content": "same repeated event"}] * 120
    inserted_tool = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": "retry", "arguments": {"attempt": 1}}}],
    }
    insertion = align_runs(
        _run("greedy-b", repeated),
        _run("greedy-c", [inserted_tool, *repeated]),
        alignment_policy=AlignmentPolicy(degraded_event_limit=100, full_dp_max_events=100),
    )
    deletion = align_runs(
        _run("greedy-b2", [inserted_tool, *repeated]),
        _run("greedy-c2", repeated),
        alignment_policy=AlignmentPolicy(degraded_event_limit=100, full_dp_max_events=100),
    )

    assert insertion.quality == "degraded"
    assert insertion.steps[0].op == "insert"
    assert insertion.steps[1].op == "match"
    assert deletion.quality == "degraded"
    assert deletion.steps[0].op == "delete"
    assert deletion.steps[1].op == "match"


def test_empty_trajectory_alignment_uses_affine_gap_costs() -> None:
    empty = _run("empty", [])
    two_events = _run(
        "two",
        [
            {"role": "assistant", "content": "one"},
            {"role": "assistant", "content": "two"},
        ],
    )

    insertion = align_runs(empty, two_events)
    deletion = align_runs(two_events, empty)

    assert [step.op for step in insertion.steps] == ["insert", "insert"]
    assert [step.cost for step in insertion.steps] == [1.0, 0.25]
    assert [step.op for step in deletion.steps] == ["delete", "delete"]
    assert deletion.first_observed_divergence is not None
    assert deletion.first_observed_divergence.category == "message_deleted"


def test_numeric_tolerance_and_stable_call_ids_are_explicit_policy_semantics() -> None:
    numeric = align_runs(
        _run("numeric-b", [{"role": "tool", "name": "calc", "content": {"value": 1.0}}]),
        _run("numeric-c", [{"role": "tool", "name": "calc", "content": {"value": 1.05}}]),
        canonicalization_policy=CanonicalizationPolicy(numeric_abs_tolerance=0.1),
    )
    baseline_call = _run(
        "call-b",
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-a", "function": {"name": "search", "arguments": {}}}],
            }
        ],
    )
    candidate_call = _run(
        "call-c",
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-b", "function": {"name": "search", "arguments": {}}}],
            }
        ],
    )

    unstable = align_runs(baseline_call, candidate_call)
    stable = align_runs(
        baseline_call,
        candidate_call,
        canonicalization_policy=CanonicalizationPolicy(tool_call_id_stability="stable"),
    )

    assert numeric.steps[0].cost == _NUMERIC_TOLERANCE_COST
    assert unstable.steps[0].op == "match"
    assert stable.steps[0].op == "change"
    assert stable.steps[0].field_diffs[0].path == "$.call_id"

    shared_id_baseline = _run(
        "shared-b",
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "shared", "function": {"name": "search", "arguments": {"limit": 1}}}
                ],
            }
        ],
    )
    shared_id_candidate = _run(
        "shared-c",
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "shared", "function": {"name": "search", "arguments": {"limit": 2}}}
                ],
            }
        ],
    )
    anchored_change = align_runs(
        shared_id_baseline,
        shared_id_candidate,
        canonicalization_policy=CanonicalizationPolicy(tool_call_id_stability="stable"),
    )
    assert anchored_change.steps[0].op == "change"
    assert anchored_change.total_cost == _SAME_KIND_NAME_CHANGE_COST


def test_flatten_preserves_metrics_parent_ref_and_multiple_tool_call_order() -> None:
    run = _run(
        "flatten",
        [
            {
                "role": "assistant",
                "content": "planning text",
                "parent_event_id": "parent-1",
                "timestamp": "2026-08-22T12:00:00Z",
                "latency_ms": 12.5,
                "tokens_in": 4,
                "tokens_out": 7,
                "cost_usd": 0.01,
                "tool_calls": [
                    {"function": {"name": "first", "arguments": '{"x":1}'}},
                    {"function": {"name": "second", "arguments": {"y": 2}}},
                ],
            }
        ],
    )

    trajectory = canonicalize_run(run)

    assert [event.kind for event in trajectory.events] == ["assistant", "tool_call", "tool_call"]
    assert [event.name for event in trajectory.events] == [None, "first", "second"]
    assert trajectory.events[0].parent_ref == "parent-1"
    assert trajectory.events[0].metrics.tokens_out == _EXPECTED_TOKENS_OUT
    assert trajectory.events[0].metrics.timestamp is not None
    assert trajectory.events[1].content == {"x": 1}


def test_other_event_difference_is_observed_but_not_action_divergence() -> None:
    result = align_runs(
        _run("other-b", [{"kind": "custom", "role": "unknown", "content": "before"}]),
        _run("other-c", [{"kind": "custom", "role": "unknown", "content": "after"}]),
    )

    assert result.first_observed_divergence is not None
    assert result.first_observed_divergence.category == "other_changed"
    assert result.first_action_divergence is None


def test_policy_validation_rejects_duplicate_and_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="must be unique"):
        CanonicalizationPolicy(ignored_json_paths=["$.id", "$.id"])
    with pytest.raises(ValueError, match="do not support wildcards"):
        CanonicalizationPolicy(ignored_json_paths=["$.items[*]"])
    with pytest.raises(ValueError, match="must be unique"):
        CanonicalizationPolicy.model_validate(
            {
                "string_scrubbers": {
                    "rules": [
                        {"id": "same", "pattern": "[0-9]", "replacement": "x"},
                        {"id": "same", "pattern": "[a-z]", "replacement": "x"},
                    ]
                }
            }
        )
    with pytest.raises(ValueError, match="expanded_band_width"):
        AlignmentPolicy(initial_band_width=200, expanded_band_width=100)
    with pytest.raises(ValueError, match="degraded_event_limit"):
        AlignmentPolicy(full_dp_max_events=500, degraded_event_limit=100)
    with pytest.raises(ValueError, match="finite number"):
        AlignmentPolicy(gap_open=float("inf"))


@pytest.mark.parametrize(
    ("pattern", "message"),
    [
        ("x" * 257, "at most 256"),
        (r"a{2,}", "unbounded quantifier"),
        (r"a{1,1001}", "must not exceed"),
        (r"item\\4", "backreferences"),
        ("[", "invalid"),
    ],
)
def test_scrubber_regex_validation_boundaries(pattern: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        StringScrubberRule(id="rule", pattern=pattern, replacement="x")
    with pytest.raises(ValueError, match="flags must be unique"):
        StringScrubberRule(
            id="flags",
            pattern="[a-z]",
            replacement="x",
            flags=["ignore_case", "ignore_case"],
        )
    with pytest.raises(ValueError, match="replacements must not contain backreferences"):
        StringScrubberRule(
            id="replacement",
            pattern="[a-z]",
            replacement=r"\1",
        )


def test_canonicalization_handles_json_text_whitespace_scopes_and_invalid_timestamp() -> None:
    policy = CanonicalizationPolicy.model_validate(
        {
            "ignored_key_patterns": ["secret[0-9]"],
            "string_scrubbers": {
                "preset": "none",
                "rules": [
                    {
                        "id": "assistant-only",
                        "pattern": "TOKEN",
                        "replacement": "hidden",
                        "flags": ["ignore_case", "multiline", "dotall"],
                        "scope": "assistant",
                    }
                ],
            },
        }
    )
    run = _run(
        "canonical",
        [
            {
                "role": "assistant",
                "content": '{"secret1":"x","text":"ToKeN"}',
                "timestamp": "not-a-timestamp",
            },
            {"role": "tool", "content": "TOKEN"},
            {"kind": "tool_call", "role": "unknown", "content": {"x": 1}},
            {"kind": "system", "role": "unknown", "content": "line  one\r\n```a   b```"},
        ],
    )

    trajectory = canonicalize_run(run, policy)

    assert trajectory.events[0].content == {"text": "hidden"}
    assert "invalid_timestamp" in trajectory.events[0].normalization_notes
    assert trajectory.events[1].content == "TOKEN"
    assert trajectory.events[2].kind == "tool_call"
    assert trajectory.events[3].kind == "system"
    assert trajectory.events[3].content == "line one\n```a   b```"

    null_content = canonicalize_run(_run("json-null", [{"role": "assistant", "content": "null"}]))
    assert null_content.events[0].content is None


def test_binary_adapter_content_keeps_only_type_size_and_hash() -> None:
    raw = b"sensitive-binary-payload"

    result = canonicalize_content(raw)

    assert result.content == {
        "$binary": {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size": len(raw),
            "type": "bytes",
        }
    }
    assert raw.decode() not in result.model_dump_json()
    assert result.normalization_notes == ["binary_metadata:$"]


def test_assistant_similarity_char_ngrams_exact_and_length_guard() -> None:
    left = canonicalize_run(_run("left", [{"role": "assistant", "content": "中文甲乙"}])).events[0]
    right = canonicalize_run(_run("right", [{"role": "assistant", "content": "中文甲丙"}])).events[
        0
    ]
    empty = canonicalize_run(_run("empty-text", [{"role": "assistant", "content": ""}])).events[0]

    assert 0.0 <= assistant_text_similarity(left, right) < 1.0
    assert assistant_text_similarity(empty, empty) == 1.0
    assert assistant_events_are_near_match(empty, empty, CanonicalizationPolicy()) == (True, 1.0)
    long = canonicalize_run(_run("long", [{"role": "assistant", "content": "word " * 20}])).events[
        0
    ]
    assert assistant_events_are_near_match(left, long, CanonicalizationPolicy()) == (False, 0.0)


def test_mismatched_canonicalization_policy_hash_is_rejected() -> None:
    run = _run("same", [{"role": "assistant", "content": "same"}])
    baseline = canonicalize_run(run, CanonicalizationPolicy())
    candidate = canonicalize_run(run, CanonicalizationPolicy(normalize_whitespace=False))

    with pytest.raises(ValueError, match="same canonicalization policy"):
        align_trajectories(
            baseline,
            candidate,
            canonicalization_policy=CanonicalizationPolicy(),
            alignment_policy=AlignmentPolicy(),
        )
    same_non_default = canonicalize_run(run, CanonicalizationPolicy(normalize_whitespace=False))
    with pytest.raises(ValueError, match="does not match the supplied policy"):
        align_trajectories(
            same_non_default,
            same_non_default,
            canonicalization_policy=CanonicalizationPolicy(),
            alignment_policy=AlignmentPolicy(),
        )
    tampered_payload = baseline.model_dump(mode="json")
    tampered_payload["events"][0]["signature"] = "0" * 64  # type: ignore[index]
    tampered = type(baseline).model_validate(tampered_payload)
    with pytest.raises(ValueError, match="invalid event signature"):
        align_trajectories(
            tampered,
            baseline,
            canonicalization_policy=CanonicalizationPolicy(),
            alignment_policy=AlignmentPolicy(),
        )
    invalid_indices = baseline.model_dump(mode="json")
    invalid_indices["events"][0]["index"] = 2  # type: ignore[index]
    with pytest.raises(ValueError, match="indices must be sequential"):
        type(baseline).model_validate(invalid_indices)


def test_banded_alignment_handles_affine_insert_and_delete_paths() -> None:
    repeated = [{"role": "assistant", "content": "band repeated"}] * _BANDED_EVENT_COUNT
    inserted = {"role": "tool", "name": "retry", "content": "temporary"}

    insertion = align_runs(_run("band-i-b", repeated), _run("band-i-c", [inserted, *repeated]))
    deletion = align_runs(_run("band-d-b", [inserted, *repeated]), _run("band-d-c", repeated))

    assert insertion.quality == "exact"
    assert insertion.steps[0].op == "insert"
    assert deletion.quality == "exact"
    assert deletion.steps[0].op == "delete"


def test_narrow_band_degrades_and_greedy_consumes_trailing_events() -> None:
    baseline = [{"role": "assistant", "content": "tail repeated"}] * 160
    inserted = [{"role": "tool", "name": "retry", "content": index} for index in range(30)]
    narrowed = align_runs(
        _run("narrow-b", baseline),
        _run("narrow-c", [*inserted, *baseline]),
        alignment_policy=AlignmentPolicy(
            full_dp_max_events=100,
            initial_band_width=10,
            expanded_band_width=10,
        ),
    )
    trailing = align_runs(
        _run("tail-b", baseline),
        _run("tail-c", baseline[:100]),
        alignment_policy=AlignmentPolicy(degraded_event_limit=100, full_dp_max_events=100),
    )

    assert narrowed.quality == "degraded"
    assert any(warning.code == "ALIGNMENT_DEGRADED" for warning in narrowed.warnings)
    assert trailing.quality == "degraded"
    assert trailing.summary.deletions == _TRAILING_DELETE_COUNT


def test_cpu_budget_expiry_returns_explicit_degraded_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock_values = iter((0.0, 0.0, 10.0))
    monkeypatch.setattr(alignment_module.time, "monotonic", lambda: next(clock_values))
    repeated = [
        {"role": "assistant", "content": "same budget event"},
        {"role": "assistant", "content": "same budget event"},
    ]

    result = align_runs(
        _run("budget-b", repeated),
        _run("budget-c", repeated),
        alignment_policy=AlignmentPolicy(cpu_budget_seconds=0.1),
    )

    assert result.quality == "degraded"
    assert [warning.code for warning in result.warnings] == ["ALIGNMENT_BUDGET_EXCEEDED"]


def test_field_diff_reports_added_and_removed_object_and_array_members() -> None:
    object_result = align_runs(
        _run("object-b", [{"role": "tool", "content": {"remove": 1, "same": 2}}]),
        _run("object-c", [{"role": "tool", "content": {"add": 3, "same": 2}}]),
    )
    array_result = align_runs(
        _run("array-b", [{"role": "tool", "content": [1, 2]}]),
        _run("array-c", [{"role": "tool", "content": [1, 2, 3]}]),
    )

    object_categories = {diff.category for diff in object_result.steps[0].field_diffs}
    assert object_categories == {"added", "removed"}
    assert array_result.steps[0].field_diffs[0].category == "added"


def test_unknown_to_ok_status_is_action_change_without_error_taxonomy() -> None:
    result = align_runs(
        _run("status-b", [{"role": "tool", "name": "search", "content": "same"}]),
        _run(
            "status-c",
            [{"role": "tool", "name": "search", "content": "same", "status": "ok"}],
        ),
    )

    assert result.first_action_divergence is not None
    assert result.first_action_divergence.category == "tool_result_changed"
