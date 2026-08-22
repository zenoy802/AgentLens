from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias
from uuid import UUID, uuid5

from app.services.trace_contract import canonical_json_bytes

DEFAULT_SEED = 20260821
GENERATOR_VERSION = "regression-fixture/v1"
GROUND_TRUTH_VERSION = "synthetic-ground-truth/v1"
_NAMESPACE = UUID("5b76f85c-e925-4aba-a2f8-56ff10e179bf")
_INCONCLUSIVE_REGRESSION_TASKS = 2
_PURE_TEXT_TASK = 25
_RETRY_TASK = 26
_STATUS_FAILURE_TASK = 1
_TOOL_CHANGE_TASK_LIMIT = 20
_TEXT_NOISE_PROBABILITY = 0.5
FixtureRow: TypeAlias = dict[str, object]
Variant: TypeAlias = Literal["baseline", "candidate", "candidate_inconclusive"]


@dataclass(frozen=True, slots=True)
class FixtureSpec:
    name: str
    task_count: int
    baseline_trials: int
    candidate_trials: int
    flaky_tasks: int
    regressed_tasks: int
    improved_tasks: int


@dataclass(frozen=True, slots=True)
class RegressionFixture:
    schema_version: str
    seed: int
    spec: FixtureSpec
    contracts: dict[str, FixtureRow]
    baseline_run_rows: list[FixtureRow]
    candidate_run_rows: list[FixtureRow]
    candidate_inconclusive_run_rows: list[FixtureRow]
    baseline_event_rows: list[FixtureRow]
    candidate_event_rows: list[FixtureRow]
    candidate_inconclusive_event_rows: list[FixtureRow]
    ground_truth: list[FixtureRow]


QUICK_SPEC = FixtureSpec(
    name="quick",
    task_count=40,
    baseline_trials=4,
    candidate_trials=3,
    flaky_tasks=3,
    regressed_tasks=4,
    improved_tasks=1,
)
FLAGSHIP_SPEC = FixtureSpec(
    name="flagship",
    task_count=120,
    baseline_trials=6,
    candidate_trials=4,
    flaky_tasks=10,
    regressed_tasks=12,
    improved_tasks=1,
)


def generate_fixture(spec: FixtureSpec, *, seed: int = DEFAULT_SEED) -> RegressionFixture:
    baseline_runs, baseline_truth = _generate_variant(spec, "baseline", seed)
    candidate_runs, candidate_truth = _generate_variant(spec, "candidate", seed)
    inconclusive_runs, inconclusive_truth = _generate_variant(spec, "candidate_inconclusive", seed)
    ground_truth = sorted(
        baseline_truth + candidate_truth + inconclusive_truth,
        key=lambda item: (str(item["task_id"]), str(item["trace_id"])),
    )
    return RegressionFixture(
        schema_version=GENERATOR_VERSION,
        seed=seed,
        spec=spec,
        contracts={"run_rows": run_rows_contract(), "event_rows": event_rows_contract()},
        baseline_run_rows=baseline_runs,
        candidate_run_rows=candidate_runs,
        candidate_inconclusive_run_rows=inconclusive_runs,
        baseline_event_rows=_to_event_rows(baseline_runs),
        candidate_event_rows=_to_event_rows(candidate_runs),
        candidate_inconclusive_event_rows=_to_event_rows(inconclusive_runs),
        ground_truth=ground_truth,
    )


def fixture_bytes(fixture: RegressionFixture, *, include_ground_truth: bool = True) -> bytes:
    payload = {
        "schema_version": fixture.schema_version,
        "seed": fixture.seed,
        "spec": {
            "name": fixture.spec.name,
            "task_count": fixture.spec.task_count,
            "baseline_trials": fixture.spec.baseline_trials,
            "candidate_trials": fixture.spec.candidate_trials,
            "flaky_tasks": fixture.spec.flaky_tasks,
            "regressed_tasks": fixture.spec.regressed_tasks,
            "improved_tasks": fixture.spec.improved_tasks,
        },
        "contracts": fixture.contracts,
        "baseline_run_rows": fixture.baseline_run_rows,
        "candidate_run_rows": fixture.candidate_run_rows,
        "candidate_inconclusive_run_rows": fixture.candidate_inconclusive_run_rows,
        "baseline_event_rows": fixture.baseline_event_rows,
        "candidate_event_rows": fixture.candidate_event_rows,
        "candidate_inconclusive_event_rows": fixture.candidate_inconclusive_event_rows,
    }
    if include_ground_truth:
        payload["ground_truth"] = fixture.ground_truth
    return canonical_json_bytes(payload)


def fixture_sha256(fixture: RegressionFixture, *, include_ground_truth: bool = True) -> str:
    return hashlib.sha256(
        fixture_bytes(fixture, include_ground_truth=include_ground_truth)
    ).hexdigest()


def run_rows_contract() -> FixtureRow:
    return {
        "version": "trace-contract/v1",
        "source_layout": "run_rows",
        "task_id": "case_id",
        "trial_id": "attempt",
        "trace_id": "run_uuid",
        "pairing_key": "shared_seed",
        "outcome": "result.outcome",
        "outcome_mapping": {
            "success_values": ["success"],
            "failure_values": ["failure"],
            "abstain_values": ["abstain"],
        },
        "score": "result.score",
        "latency_ms": "metrics.latency_ms",
        "token_usage": "metrics.token_usage",
        "cost_usd": "metrics.cost_usd",
        "error": "result.error",
        "metadata": {"dataset_split": "dataset_split", "model": "model"},
        "messages": "payload.messages",
        "message_mapping": {
            "role": "role",
            "content": "content",
            "name": "name",
            "tool_call_id": "tool_call_id",
            "tool_calls": "tool_calls",
            "status": "status",
            "timestamp": "timestamp",
            "latency_ms": "latency_ms",
            "tokens_in": "tokens_in",
            "tokens_out": "tokens_out",
            "cost_usd": "cost_usd",
        },
    }


def event_rows_contract() -> FixtureRow:
    return {
        "version": "trace-contract/v1",
        "source_layout": "event_rows",
        "task_id": "case_id",
        "trial_id": "attempt",
        "trace_id": "run_uuid",
        "pairing_key": "shared_seed",
        "outcome": "outcome",
        "outcome_mapping": {
            "success_values": ["success"],
            "failure_values": ["failure"],
            "abstain_values": ["abstain"],
        },
        "score": "score",
        "latency_ms": "run_latency_ms",
        "token_usage": "run_token_usage",
        "cost_usd": "run_cost_usd",
        "error": "error",
        "metadata": {"dataset_split": "dataset_split", "model": "model"},
        "event_index": "step_index",
        "event_mapping": {
            "kind": "kind",
            "role": "role",
            "content": "content",
            "name": "name",
            "tool_call_id": "tool_call_id",
            "tool_calls": "tool_calls",
            "status": "status",
            "parent_event_id": "parent_event_id",
            "timestamp": "timestamp",
            "latency_ms": "latency_ms",
            "tokens_in": "tokens_in",
            "tokens_out": "tokens_out",
            "cost_usd": "cost_usd",
        },
    }


def _generate_variant(
    spec: FixtureSpec, variant: Variant, seed: int
) -> tuple[list[FixtureRow], list[FixtureRow]]:
    trial_count = spec.baseline_trials if variant == "baseline" else spec.candidate_trials
    rows: list[FixtureRow] = []
    ground_truth: list[FixtureRow] = []
    for task_index in range(spec.task_count):
        for trial_index in range(trial_count):
            task_id = f"local-tool-task-{task_index:03d}"
            trace_id = str(
                uuid5(_NAMESPACE, f"{seed}:{spec.name}:{variant}:{task_id}:{trial_index}")
            )
            outcome = _outcome_for(spec, variant, task_index, trial_index)
            messages, cause, injected_step = _messages_for(
                task_index,
                variant,
                outcome,
                improved_task_index=spec.regressed_tasks,
                seed=seed,
                trial_index=trial_index,
            )
            rows.append(
                {
                    "case_id": task_id,
                    "attempt": str(trial_index),
                    "run_uuid": trace_id,
                    "shared_seed": f"seed-{trial_index:02d}",
                    "result": {
                        "outcome": outcome,
                        "score": _score_for(outcome),
                        "error": "tool timeout" if outcome == "failure" else None,
                    },
                    "metrics": {
                        "latency_ms": 1000.0 + task_index * 3 + trial_index,
                        "token_usage": 300 + task_index + trial_index,
                        "cost_usd": round(0.01 + task_index / 100_000, 6),
                    },
                    "model": "model-a" if variant == "baseline" else "model-b",
                    "dataset_split": "demo",
                    "payload": {"messages": messages},
                    "row_identity": f"{variant}:{trace_id}",
                }
            )
            if cause is not None:
                ground_truth.append(
                    {
                        "schema_version": GROUND_TRUTH_VERSION,
                        "task_id": task_id,
                        "trace_id": trace_id,
                        "injected_cause": cause,
                        "injected_step": injected_step,
                        "seed": seed,
                        "generator_version": GENERATOR_VERSION,
                    }
                )
    return rows, ground_truth


def _outcome_for(spec: FixtureSpec, variant: Variant, task_index: int, trial_index: int) -> str:
    improved_start = spec.regressed_tasks
    flaky_start = improved_start + spec.improved_tasks
    missing_candidate = flaky_start + spec.flaky_tasks
    missing_baseline = missing_candidate + 1
    outcome = "success"
    if (task_index == missing_candidate and variant != "baseline") or (
        task_index == missing_baseline and variant == "baseline"
    ):
        outcome = "unknown"
    elif task_index < spec.regressed_tasks:
        is_regressed = variant == "candidate" or (
            variant == "candidate_inconclusive" and task_index < _INCONCLUSIVE_REGRESSION_TASKS
        )
        outcome = "failure" if is_regressed else "success"
    elif improved_start <= task_index < flaky_start:
        outcome = "failure" if variant == "baseline" else "success"
    elif flaky_start <= task_index < missing_candidate:
        if variant == "baseline":
            outcome = "failure" if trial_index == spec.baseline_trials - 1 else "success"
        else:
            outcome = "failure" if trial_index == spec.candidate_trials - 1 else "success"
    elif task_index % 9 == 0:
        outcome = "failure"
    return outcome


def _score_for(outcome: str) -> float | None:
    if outcome == "success":
        return 1.0
    if outcome == "failure":
        return 0.0
    return None


def _messages_for(
    task_index: int,
    variant: Variant,
    outcome: str,
    *,
    improved_task_index: int,
    seed: int,
    trial_index: int,
) -> tuple[list[FixtureRow], str | None, int | None]:
    randomizer = random.Random(seed + task_index * 100 + trial_index)
    is_candidate = variant != "baseline"
    messages = [
        _message("system", "Use local deterministic tools only.", 0),
        _message("user", f"Solve local fixture task {task_index:03d}.", 1),
        _message("assistant", "I will inspect the local fixture.", 2),
        _tool_call_message(limit=10, index=3),
        _message("tool", {"status": "ok", "items": [1, 2, 3]}, 4, name="search"),
        _message("assistant", "The fixture is complete.", 5),
    ]
    cause: str | None = None
    injected_step: int | None = None
    if variant == "baseline" and task_index == improved_task_index:
        _set_tool_failure(messages, task_index)
    if is_candidate and task_index == _PURE_TEXT_TASK:
        messages[2]["content"] = "First, I will inspect this deterministic local fixture."
        cause, injected_step = "assistant_text_rewrite", 2
    if is_candidate and task_index == _RETRY_TASK:
        messages.insert(5, _message("assistant", "Retrying once.", 5))
        cause, injected_step = "retry_insertion", 5
    if is_candidate and task_index == _STATUS_FAILURE_TASK:
        messages[4]["status"] = "error"
        cause, injected_step = "status_only_failure", 4
    elif is_candidate and outcome == "failure" and task_index < _TOOL_CHANGE_TASK_LIMIT:
        _set_tool_failure(messages, task_index)
        cause, injected_step = "tool_argument_change", 3
    elif is_candidate and outcome == "success" and task_index == improved_task_index:
        cause, injected_step = "tool_argument_fix", 3
    if randomizer.random() < _TEXT_NOISE_PROBABILITY:
        noise_id = randomizer.randrange(1000)
        messages[2]["content"] = f"{messages[2]['content']} Request {noise_id:03d}."
    return messages, cause, injected_step


def _set_tool_failure(messages: list[FixtureRow], task_index: int) -> None:
    tool_calls = messages[3]["tool_calls"]
    assert isinstance(tool_calls, list)
    function = tool_calls[0]["function"]
    assert isinstance(function, dict)
    function["arguments"] = {"limit": 100, "query": f"fixture-{task_index:03d}"}
    messages[4]["content"] = {"status": "timeout", "items": []}
    messages[4]["status"] = "error"


def _message(
    role: str,
    content: object,
    index: int,
    *,
    name: str | None = None,
) -> FixtureRow:
    return {
        "role": role,
        "content": content,
        "name": name,
        "tool_call_id": None,
        "tool_calls": None,
        "status": None,
        "timestamp": f"2026-08-21T00:00:{index:02d}Z",
        "latency_ms": float(20 + index),
        "tokens_in": index * 2,
        "tokens_out": index * 3,
        "cost_usd": round(index / 100_000, 6),
    }


def _tool_call_message(*, limit: int, index: int) -> FixtureRow:
    message = _message("assistant", "", index)
    message["tool_calls"] = [
        {
            "id": f"call-{index}",
            "type": "function",
            "function": {
                "name": "search",
                "arguments": {"query": "fixture", "limit": limit},
            },
        }
    ]
    return message


def _to_event_rows(run_rows: list[FixtureRow]) -> list[FixtureRow]:
    event_rows: list[FixtureRow] = []
    for run_row in run_rows:
        result = run_row["result"]
        metrics = run_row["metrics"]
        payload = run_row["payload"]
        assert isinstance(result, dict) and isinstance(metrics, dict) and isinstance(payload, dict)
        messages = payload["messages"]
        assert isinstance(messages, list)
        for event_index, message in enumerate(messages):
            assert isinstance(message, dict)
            event_rows.append(
                {
                    "case_id": run_row["case_id"],
                    "attempt": run_row["attempt"],
                    "run_uuid": run_row["run_uuid"],
                    "shared_seed": run_row["shared_seed"],
                    "outcome": result["outcome"],
                    "score": result["score"],
                    "error": result["error"],
                    "run_latency_ms": metrics["latency_ms"],
                    "run_token_usage": metrics["token_usage"],
                    "run_cost_usd": metrics["cost_usd"],
                    "model": run_row["model"],
                    "dataset_split": run_row["dataset_split"],
                    "step_index": event_index,
                    "kind": None,
                    "parent_event_id": None,
                    **message,
                    "row_identity": f"{run_row['row_identity']}:{event_index}",
                }
            )
    return event_rows


def write_fixture(output_dir: Path, fixture: RegressionFixture) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "fixture.json": fixture_bytes(fixture, include_ground_truth=False),
        "synthetic-ground-truth.json": canonical_json_bytes(
            {
                "schema_version": GROUND_TRUTH_VERSION,
                "seed": fixture.seed,
                "items": fixture.ground_truth,
            }
        ),
    }
    for filename, payload in payloads.items():
        (output_dir / filename).write_bytes(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic regression fixtures.")
    parser.add_argument("--size", choices=("quick", "flagship"), default="quick")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = QUICK_SPEC if args.size == "quick" else FLAGSHIP_SPEC
    fixture = generate_fixture(spec, seed=args.seed)
    write_fixture(args.output, fixture)
    print(
        json.dumps(
            {
                "fixture_sha256": fixture_sha256(fixture, include_ground_truth=False),
                "output": str(args.output),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
