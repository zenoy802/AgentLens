from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import cast

import pytest

from scripts.generate_regression_fixtures import (
    DEFAULT_SEED,
    FLAGSHIP_SPEC,
    QUICK_SPEC,
    fixture_bytes,
    fixture_sha256,
    generate_fixture,
)
from scripts.generate_regression_fixtures import (
    main as generate_fixture_main,
)
from scripts.simulate_regression_gate import (
    AUTHORITATIVE_BOOTSTRAP_SAMPLES,
    AUTHORITATIVE_NOISE_SAMPLES,
    PRESCAN_BOOTSTRAP_SAMPLES,
    PRESCAN_NOISE_SAMPLES,
    harm_ci95,
    scan_scenarios,
    split_half_noise_q95,
)

_PRACTICAL_THRESHOLD = 0.02
_FLAGSHIP_FLAKY_RATE = 0.08
_FLAGSHIP_HARM = 0.1
_MIN_REGRESSED_PROBABILITY = 0.95
_BROKEN_TOOL_LIMIT = 100
_FIXED_TOOL_LIMIT = 10
_TOOL_CALL_STEP = 3


def _binary_outcomes(rows: list[dict[str, object]]) -> dict[str, list[int]]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        result = cast(dict[str, object], row["result"])
        outcome = result["outcome"]
        if outcome in {"success", "failure"}:
            grouped[str(row["case_id"])].append(1 if outcome == "success" else 0)
    return grouped


def _paired_binary_outcomes(
    baseline_rows: list[dict[str, object]], candidate_rows: list[dict[str, object]]
) -> tuple[list[list[int]], list[list[int]]]:
    baseline = _binary_outcomes(baseline_rows)
    candidate = _binary_outcomes(candidate_rows)
    matched = sorted(baseline.keys() & candidate.keys())
    return [baseline[task] for task in matched], [candidate[task] for task in matched]


def test_fixture_generation_is_byte_and_hash_deterministic() -> None:
    first = generate_fixture(QUICK_SPEC, seed=DEFAULT_SEED)
    second = generate_fixture(QUICK_SPEC, seed=DEFAULT_SEED)

    assert fixture_bytes(first) == fixture_bytes(second)
    assert fixture_sha256(first) == fixture_sha256(second)
    assert fixture_sha256(first) != fixture_sha256(
        generate_fixture(QUICK_SPEC, seed=DEFAULT_SEED + 1)
    )


def test_fixture_sizes_outcomes_and_baseline_flakiness_match_spec() -> None:
    quick = generate_fixture(QUICK_SPEC)
    flagship = generate_fixture(FLAGSHIP_SPEC)

    assert len(quick.baseline_run_rows) == 40 * 4
    assert len(quick.candidate_run_rows) == 40 * 3
    assert len(flagship.baseline_run_rows) == 120 * 6
    assert len(flagship.candidate_run_rows) == 120 * 4
    assert len(flagship.baseline_event_rows) > len(flagship.baseline_run_rows)

    baseline = _binary_outcomes(flagship.baseline_run_rows)
    flaky = sum(0 < sum(outcomes) < len(outcomes) for outcomes in baseline.values())
    assert flaky == FLAGSHIP_SPEC.flaky_tasks
    assert {len(outcomes) for outcomes in baseline.values()} <= {0, 6}
    assert all(
        cast(dict[str, object], row["result"])["outcome"]
        in {"success", "failure", "abstain", "unknown"}
        for row in flagship.baseline_run_rows + flagship.candidate_run_rows
    )


def test_ground_truth_sidecar_is_not_snapshot_input() -> None:
    fixture = generate_fixture(QUICK_SPEC)
    snapshot_input = fixture_bytes(fixture, include_ground_truth=False)

    assert fixture.ground_truth
    assert b"injected_cause" not in snapshot_input
    assert all("injected_cause" not in row for row in fixture.baseline_run_rows)
    assert all("injected_cause" not in row for row in fixture.candidate_event_rows)


def test_improvement_ground_truth_has_observable_tool_argument_fix() -> None:
    fixture = generate_fixture(FLAGSHIP_SPEC)
    task_id = f"local-tool-task-{FLAGSHIP_SPEC.regressed_tasks:03d}"
    baseline = next(
        row
        for row in fixture.baseline_run_rows
        if row["case_id"] == task_id and row["attempt"] == "0"
    )
    candidate = next(
        row
        for row in fixture.candidate_run_rows
        if row["case_id"] == task_id and row["attempt"] == "0"
    )

    assert _tool_limit(baseline) == _BROKEN_TOOL_LIMIT
    assert _tool_limit(candidate) == _FIXED_TOOL_LIMIT
    truth = next(item for item in fixture.ground_truth if item["trace_id"] == candidate["run_uuid"])
    assert truth["injected_cause"] == "tool_argument_fix"
    assert truth["injected_step"] == _TOOL_CALL_STEP


def _tool_limit(row: dict[str, object]) -> object:
    payload = cast(dict[str, object], row["payload"])
    messages = cast(list[dict[str, object]], payload["messages"])
    tool_calls = cast(list[dict[str, object]], messages[3]["tool_calls"])
    function = cast(dict[str, object], tool_calls[0]["function"])
    arguments = cast(dict[str, object], function["arguments"])
    return arguments["limit"]


def test_cli_hash_matches_written_fixture_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["generate_regression_fixtures.py", "--size", "quick", "--output", str(tmp_path)],
    )
    assert generate_fixture_main() == 0
    output = json.loads(capsys.readouterr().out)

    fixture_path = tmp_path / "fixture.json"
    assert hashlib.sha256(fixture_path.read_bytes()).hexdigest() == output["fixture_sha256"]
    assert b"injected_cause" not in fixture_path.read_bytes()


def test_flagship_has_regressed_margin_and_boundary_fixture_is_inconclusive() -> None:
    fixture = generate_fixture(FLAGSHIP_SPEC)
    baseline, candidate = _paired_binary_outcomes(
        fixture.baseline_run_rows, fixture.candidate_run_rows
    )
    _, inconclusive = _paired_binary_outcomes(
        fixture.baseline_run_rows, fixture.candidate_inconclusive_run_rows
    )
    noise = split_half_noise_q95(baseline, seed=DEFAULT_SEED, samples=AUTHORITATIVE_NOISE_SAMPLES)
    regressed_ci = harm_ci95(
        baseline, candidate, seed=DEFAULT_SEED, samples=AUTHORITATIVE_BOOTSTRAP_SAMPLES
    )
    inconclusive_ci = harm_ci95(
        baseline, inconclusive, seed=DEFAULT_SEED, samples=AUTHORITATIVE_BOOTSTRAP_SAMPLES
    )

    assert noise < _PRACTICAL_THRESHOLD
    assert regressed_ci[0] > max(_PRACTICAL_THRESHOLD, noise)
    assert inconclusive_ci[0] <= max(_PRACTICAL_THRESHOLD, noise)
    assert inconclusive_ci[1] >= _PRACTICAL_THRESHOLD


def test_noise_gate_scan_is_deterministic_and_scans_requested_dimensions() -> None:
    first = scan_scenarios()
    second = scan_scenarios()

    assert first == second
    assert {result.method for result in first} == {"low-cost-prescan/v1"}
    assert {result.noise_split_samples for result in first} == {PRESCAN_NOISE_SAMPLES}
    assert {result.bootstrap_samples for result in first} == {PRESCAN_BOOTSTRAP_SAMPLES}
    assert {result.baseline_trials for result in first} == {4, 6}
    assert {result.flaky_rate for result in first} == {0.08, 0.1, 0.16}
    assert {result.harm for result in first} == {0.02, 0.05, 0.1}
    flagship = next(
        result
        for result in first
        if result.tasks == FLAGSHIP_SPEC.task_count
        and result.flaky_rate == _FLAGSHIP_FLAKY_RATE
        and result.harm == _FLAGSHIP_HARM
    )
    assert flagship.noise_margin_q95 < _PRACTICAL_THRESHOLD
    assert flagship.regressed_probability >= _MIN_REGRESSED_PROBABILITY
