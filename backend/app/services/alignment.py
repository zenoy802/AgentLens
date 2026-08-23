from __future__ import annotations

import hashlib
import json
import math
import time
from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass
from typing import Literal, TypeAlias

from pydantic import JsonValue

from app.schemas.alignment import (
    AlignmentPolicy,
    AlignmentResult,
    AlignmentStep,
    AlignmentSummary,
    AlignmentWarning,
    CanonicalEvent,
    CanonicalizationPolicy,
    CanonicalTrajectory,
    DivergenceCategory,
    DivergencePoint,
    FieldDiff,
    ScrubberCount,
)
from app.schemas.trace_contract import CanonicalRunRow
from app.services.canonicalization import (
    assistant_events_are_near_match,
    canonical_event_signature,
    canonical_policy_hash,
    canonicalize_run,
)

_State: TypeAlias = Literal["M", "I", "D"]
_STATES: tuple[_State, ...] = ("M", "I", "D")
_INF = math.inf
_EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class _PairEvaluation:
    cost: float
    op: Literal["match", "near_match", "change"]
    similarity: float | None


@dataclass(frozen=True, slots=True)
class _RawStep:
    baseline_index: int | None
    candidate_index: int | None
    cost: float
    similarity: float | None = None


@dataclass(frozen=True, slots=True)
class _SegmentResult:
    steps: list[_RawStep]
    cost: float
    touched_band: bool = False
    degraded: bool = False

    @property
    def gap_ratio(self) -> float:
        if not self.steps:
            return 0.0
        gaps = sum(
            step.baseline_index is None or step.candidate_index is None for step in self.steps
        )
        return gaps / len(self.steps)

    @property
    def unit_cost(self) -> float:
        return self.cost / max(1, len(self.steps))


@dataclass(frozen=True, slots=True)
class _AnchoredResult:
    alignment: _SegmentResult
    segments: list[_SegmentResult]


def alignment_policy_hash(policy: AlignmentPolicy) -> str:
    payload = json.dumps(
        policy.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def align_runs(
    baseline: CanonicalRunRow,
    candidate: CanonicalRunRow,
    *,
    canonicalization_policy: CanonicalizationPolicy | None = None,
    alignment_policy: AlignmentPolicy | None = None,
) -> AlignmentResult:
    """Canonicalize and align two run-row/v1 values using deterministic pure algorithms."""
    canonical_policy = canonicalization_policy or CanonicalizationPolicy()
    active_alignment_policy = alignment_policy or AlignmentPolicy()
    return align_trajectories(
        canonicalize_run(baseline, canonical_policy),
        canonicalize_run(candidate, canonical_policy),
        canonicalization_policy=canonical_policy,
        alignment_policy=active_alignment_policy,
    )


def align_trajectories(
    baseline: CanonicalTrajectory,
    candidate: CanonicalTrajectory,
    *,
    canonicalization_policy: CanonicalizationPolicy,
    alignment_policy: AlignmentPolicy,
) -> AlignmentResult:
    _validate_trajectory_inputs(baseline, candidate, canonicalization_policy)
    started_at = time.monotonic()
    deadline = started_at + alignment_policy.cpu_budget_seconds
    anchors = _provisional_anchors(baseline.events, candidate.events, canonicalization_policy)
    warnings: list[AlignmentWarning] = []
    anchored = _align_with_anchors(
        baseline.events,
        candidate.events,
        anchors,
        canonicalization_policy,
        alignment_policy,
        deadline,
    )
    while anchors and time.monotonic() < deadline:
        suspicious = _suspicious_anchor_indices(anchored.segments, alignment_policy)
        if not suspicious:
            break
        rejected = False
        for anchor_position in sorted(suspicious, reverse=True):
            reduced = anchors[:anchor_position] + anchors[anchor_position + 1 :]
            candidate_result = _align_with_anchors(
                baseline.events,
                candidate.events,
                reduced,
                canonicalization_policy,
                alignment_policy,
                deadline,
            )
            old_gaps = _gap_count(anchored.alignment.steps)
            new_gaps = _gap_count(candidate_result.alignment.steps)
            cost_improved = candidate_result.alignment.cost < anchored.alignment.cost - _EPSILON
            gaps_improved = new_gaps < old_gaps
            if candidate_result.alignment.cost <= anchored.alignment.cost + _EPSILON and (
                gaps_improved or cost_improved
            ):
                baseline_index, candidate_index = anchors[anchor_position]
                warnings.append(
                    AlignmentWarning(
                        code="ANCHOR_REJECTED",
                        message="A provisional unique anchor was rejected by the gap/cost guard.",
                        detail={
                            "baseline_index": baseline_index,
                            "candidate_index": candidate_index,
                            "previous_cost": anchored.alignment.cost,
                            "replacement_cost": candidate_result.alignment.cost,
                            "previous_gap_ops": old_gaps,
                            "replacement_gap_ops": new_gaps,
                            **suspicious[anchor_position],
                        },
                    )
                )
                anchors = reduced
                anchored = candidate_result
                rejected = True
                break
        if not rejected:
            break
    if time.monotonic() >= deadline and not anchored.alignment.degraded:
        anchored = _AnchoredResult(
            alignment=_greedy_alignment(
                baseline.events,
                candidate.events,
                0,
                0,
                canonicalization_policy,
                alignment_policy,
            ),
            segments=[],
        )
        warnings.append(
            AlignmentWarning(
                code="ALIGNMENT_BUDGET_EXCEEDED",
                message="The CPU budget was exceeded; a deterministic degraded alignment was used.",
            )
        )
    elif anchored.alignment.degraded:
        warnings.append(
            AlignmentWarning(
                code="ALIGNMENT_DEGRADED",
                message="A long or wide segment required deterministic degraded alignment.",
            )
        )

    steps = _materialize_steps(
        anchored.alignment.steps,
        baseline.events,
        candidate.events,
        canonicalization_policy,
        alignment_policy,
    )
    first_observed = _first_observed_divergence(steps, baseline.events, candidate.events)
    first_action = _first_action_divergence(steps, baseline.events, candidate.events)
    summary_counts = Counter(step.op for step in steps)
    scrubber_counts: Counter[str] = Counter()
    for event in (*baseline.events, *candidate.events):
        for count in event.scrubber_counts:
            scrubber_counts[count.rule_id] += count.count
    scrubbed_spans = sum(scrubber_counts.values())
    summary = AlignmentSummary(
        matches=summary_counts["match"],
        near_matches=summary_counts["near_match"],
        changes=summary_counts["change"],
        insertions=summary_counts["insert"],
        deletions=summary_counts["delete"],
        scrubbed_spans=scrubbed_spans,
        ignored_fields=(
            baseline.ignored_difference_candidates + candidate.ignored_difference_candidates
        ),
        scrubber_counts=[
            ScrubberCount(rule_id=rule_id, count=count)
            for rule_id, count in sorted(scrubber_counts.items())
        ],
        rejected_anchors=sum(warning.code == "ANCHOR_REJECTED" for warning in warnings),
    )
    return AlignmentResult(
        baseline_trace_id=baseline.trace_id,
        candidate_trace_id=candidate.trace_id,
        canonicalization_policy_hash=baseline.policy_hash,
        policy_hash=alignment_policy_hash(alignment_policy),
        quality="degraded" if anchored.alignment.degraded else "exact",
        summary=summary,
        steps=steps,
        first_observed_divergence=first_observed,
        first_action_divergence=first_action,
        warnings=warnings,
        total_cost=anchored.alignment.cost,
    )


def _validate_trajectory_inputs(
    baseline: CanonicalTrajectory,
    candidate: CanonicalTrajectory,
    canonicalization_policy: CanonicalizationPolicy,
) -> None:
    if baseline.policy_hash != candidate.policy_hash:
        raise ValueError("baseline and candidate must use the same canonicalization policy")
    if baseline.policy_hash != canonical_policy_hash(canonicalization_policy):
        raise ValueError("canonical trajectory policy hash does not match the supplied policy")
    for trajectory in (baseline, candidate):
        if any(
            event.signature != canonical_event_signature(event, canonicalization_policy)
            for event in trajectory.events
        ):
            raise ValueError("canonical trajectory contains an invalid event signature")


def _provisional_anchors(
    baseline: list[CanonicalEvent],
    candidate: list[CanonicalEvent],
    policy: CanonicalizationPolicy,
) -> list[tuple[int, int]]:
    baseline_keys = [_anchor_keys(event, policy) for event in baseline]
    candidate_keys = [_anchor_keys(event, policy) for event in candidate]
    baseline_counts = Counter(key for keys in baseline_keys for key in keys)
    candidate_counts = Counter(key for keys in candidate_keys for key in keys)
    candidate_positions: dict[str, int] = {}
    for index, keys in enumerate(candidate_keys):
        for key in keys:
            if candidate_counts[key] == 1:
                candidate_positions[key] = index
    candidates: set[tuple[int, int]] = set()
    for baseline_index, keys in enumerate(baseline_keys):
        for key in keys:
            if baseline_counts[key] == 1 and candidate_counts[key] == 1:
                candidates.add((baseline_index, candidate_positions[key]))
    ordered = sorted(candidates)
    return _longest_increasing_pairs(ordered)


def _anchor_keys(event: CanonicalEvent, policy: CanonicalizationPolicy) -> tuple[str, ...]:
    keys = [f"signature:{event.signature}"]
    if (
        policy.tool_call_id_stability == "stable"
        and event.kind in {"tool_call", "tool_result"}
        and event.call_id
    ):
        keys.append(f"call:{event.kind}:{event.call_id}")
    if event.kind in {"tool_call", "tool_result"}:
        content_hash = hashlib.sha256(_canonical_json(event.content)).hexdigest()
        keys.append(f"tool:{event.kind}:{event.name}:{event.status}:{content_hash}")
    return tuple(keys)


def _longest_increasing_pairs(pairs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not pairs:
        return []
    tails: list[int] = []
    tail_pair_indices: list[int] = []
    predecessors = [-1] * len(pairs)
    for pair_index, (_, candidate_index) in enumerate(pairs):
        position = bisect_left(tails, candidate_index)
        if position == len(tails):
            tails.append(candidate_index)
            tail_pair_indices.append(pair_index)
        elif candidate_index < tails[position]:
            tails[position] = candidate_index
            tail_pair_indices[position] = pair_index
        if position:
            predecessors[pair_index] = tail_pair_indices[position - 1]
    selected: list[tuple[int, int]] = []
    current = tail_pair_indices[-1]
    while current >= 0:
        selected.append(pairs[current])
        current = predecessors[current]
    selected.reverse()
    return selected


def _align_with_anchors(
    baseline: list[CanonicalEvent],
    candidate: list[CanonicalEvent],
    anchors: list[tuple[int, int]],
    canonical_policy: CanonicalizationPolicy,
    alignment_policy: AlignmentPolicy,
    deadline: float,
) -> _AnchoredResult:
    all_steps: list[_RawStep] = []
    segments: list[_SegmentResult] = []
    total_cost = 0.0
    degraded = False
    baseline_start = 0
    candidate_start = 0
    for baseline_anchor, candidate_anchor in [*anchors, (len(baseline), len(candidate))]:
        segment = _align_segment(
            baseline,
            candidate,
            baseline_start,
            baseline_anchor,
            candidate_start,
            candidate_anchor,
            canonical_policy,
            alignment_policy,
            deadline,
        )
        segments.append(segment)
        all_steps.extend(segment.steps)
        total_cost += segment.cost
        degraded = degraded or segment.degraded
        if baseline_anchor < len(baseline) and candidate_anchor < len(candidate):
            anchor_evaluation = _evaluate_pair(
                baseline[baseline_anchor],
                candidate[candidate_anchor],
                canonical_policy,
                alignment_policy,
            )
            all_steps.append(
                _RawStep(
                    baseline_anchor,
                    candidate_anchor,
                    anchor_evaluation.cost,
                    anchor_evaluation.similarity,
                )
            )
            total_cost += anchor_evaluation.cost
        baseline_start = baseline_anchor + 1
        candidate_start = candidate_anchor + 1
    return _AnchoredResult(
        alignment=_SegmentResult(all_steps, total_cost, degraded=degraded),
        segments=segments,
    )


def _suspicious_anchor_indices(
    segments: list[_SegmentResult], policy: AlignmentPolicy
) -> dict[int, dict[str, JsonValue]]:
    suspicious: dict[int, dict[str, JsonValue]] = {}
    anchor_count = max(0, len(segments) - 1)
    for segment_index, segment in enumerate(segments):
        reasons: list[JsonValue] = []
        if segment.gap_ratio > policy.max_anchor_forced_gap_ratio:
            reasons.append("forced_gap_ratio")
        if segment.unit_cost > policy.max_anchor_segment_cost:
            reasons.append("segment_unit_cost")
        if not reasons:
            continue
        detail: dict[str, JsonValue] = {
            "guard_reasons": reasons,
            "adjacent_segment_index": segment_index,
            "adjacent_segment_gap_ratio": segment.gap_ratio,
            "adjacent_segment_unit_cost": segment.unit_cost,
            "max_anchor_forced_gap_ratio": policy.max_anchor_forced_gap_ratio,
            "max_anchor_segment_cost": policy.max_anchor_segment_cost,
        }
        if segment_index < anchor_count:
            suspicious[segment_index] = detail
        if segment_index > 0:
            suspicious[segment_index - 1] = detail
    return suspicious


def _align_segment(  # noqa: PLR0911
    baseline: list[CanonicalEvent],
    candidate: list[CanonicalEvent],
    baseline_start: int,
    baseline_end: int,
    candidate_start: int,
    candidate_end: int,
    canonical_policy: CanonicalizationPolicy,
    alignment_policy: AlignmentPolicy,
    deadline: float,
) -> _SegmentResult:
    baseline_size = baseline_end - baseline_start
    candidate_size = candidate_end - candidate_start
    if not baseline_size:
        return _SegmentResult(
            [
                _RawStep(
                    None,
                    candidate_start + index,
                    alignment_policy.gap_open if index == 0 else alignment_policy.gap_extend,
                )
                for index in range(candidate_size)
            ],
            _gap_run_cost(candidate_size, alignment_policy),
        )
    if not candidate_size:
        return _SegmentResult(
            [
                _RawStep(
                    baseline_start + index,
                    None,
                    alignment_policy.gap_open if index == 0 else alignment_policy.gap_extend,
                )
                for index in range(baseline_size)
            ],
            _gap_run_cost(baseline_size, alignment_policy),
        )
    if (
        max(baseline_size, candidate_size) > alignment_policy.degraded_event_limit
        or time.monotonic() >= deadline
    ):
        return _greedy_alignment(
            baseline,
            candidate,
            baseline_start,
            candidate_start,
            canonical_policy,
            alignment_policy,
            baseline_end=baseline_end,
            candidate_end=candidate_end,
        )
    if (
        baseline_size <= alignment_policy.full_dp_max_events
        and candidate_size <= alignment_policy.full_dp_max_events
    ):
        return _affine_dp_full(
            baseline[baseline_start:baseline_end],
            candidate[candidate_start:candidate_end],
            baseline_start,
            candidate_start,
            canonical_policy,
            alignment_policy,
        )
    first = _affine_dp_banded(
        baseline[baseline_start:baseline_end],
        candidate[candidate_start:candidate_end],
        baseline_start,
        candidate_start,
        canonical_policy,
        alignment_policy,
        alignment_policy.initial_band_width,
    )
    if first is not None and not first.touched_band:
        return first
    expanded = _affine_dp_banded(
        baseline[baseline_start:baseline_end],
        candidate[candidate_start:candidate_end],
        baseline_start,
        candidate_start,
        canonical_policy,
        alignment_policy,
        alignment_policy.expanded_band_width,
    )
    if expanded is not None and not expanded.touched_band:
        return expanded
    return _greedy_alignment(
        baseline,
        candidate,
        baseline_start,
        candidate_start,
        canonical_policy,
        alignment_policy,
        baseline_end=baseline_end,
        candidate_end=candidate_end,
    )


def _affine_dp_full(
    baseline: list[CanonicalEvent],
    candidate: list[CanonicalEvent],
    baseline_offset: int,
    candidate_offset: int,
    canonical_policy: CanonicalizationPolicy,
    policy: AlignmentPolicy,
) -> _SegmentResult:
    n = len(baseline)
    m = len(candidate)
    match = [[_INF] * (m + 1) for _ in range(n + 1)]
    insert = [[_INF] * (m + 1) for _ in range(n + 1)]
    delete = [[_INF] * (m + 1) for _ in range(n + 1)]
    match[0][0] = 0.0
    for index in range(1, n + 1):
        delete[index][0] = _gap_run_cost(index, policy)
    for index in range(1, m + 1):
        insert[0][index] = _gap_run_cost(index, policy)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            evaluation = _evaluate_pair(baseline[i - 1], candidate[j - 1], canonical_policy, policy)
            match[i][j] = (
                min(match[i - 1][j - 1], insert[i - 1][j - 1], delete[i - 1][j - 1])
                + evaluation.cost
            )
            delete[i][j] = min(
                match[i - 1][j] + policy.gap_open,
                insert[i - 1][j] + policy.gap_open,
                delete[i - 1][j] + policy.gap_extend,
            )
            insert[i][j] = min(
                match[i][j - 1] + policy.gap_open,
                delete[i][j - 1] + policy.gap_open,
                insert[i][j - 1] + policy.gap_extend,
            )
    state = _best_state(match[n][m], insert[n][m], delete[n][m])
    total_cost = _state_value(state, match[n][m], insert[n][m], delete[n][m])
    steps: list[_RawStep] = []
    i, j = n, m
    while i or j:
        if state == "M":
            evaluation = _evaluate_pair(baseline[i - 1], candidate[j - 1], canonical_policy, policy)
            steps.append(
                _RawStep(
                    baseline_offset + i - 1,
                    candidate_offset + j - 1,
                    evaluation.cost,
                    evaluation.similarity,
                )
            )
            previous_cost = match[i][j] - evaluation.cost
            state = _matching_previous_state(
                previous_cost,
                match[i - 1][j - 1],
                insert[i - 1][j - 1],
                delete[i - 1][j - 1],
            )
            i -= 1
            j -= 1
        elif state == "I":
            previous_state = _gap_previous_state(
                insert[i][j],
                match[i][j - 1],
                delete[i][j - 1],
                insert[i][j - 1],
                policy,
                extension_state="I",
            )
            steps.append(
                _RawStep(
                    None,
                    candidate_offset + j - 1,
                    policy.gap_extend if previous_state == "I" else policy.gap_open,
                )
            )
            state = previous_state
            j -= 1
        else:
            previous_state = _gap_previous_state(
                delete[i][j],
                match[i - 1][j],
                insert[i - 1][j],
                delete[i - 1][j],
                policy,
                extension_state="D",
            )
            steps.append(
                _RawStep(
                    baseline_offset + i - 1,
                    None,
                    policy.gap_extend if previous_state == "D" else policy.gap_open,
                )
            )
            state = previous_state
            i -= 1
    steps.reverse()
    return _SegmentResult(steps, total_cost)


def _affine_dp_banded(  # noqa: PLR0912, PLR0915
    baseline: list[CanonicalEvent],
    candidate: list[CanonicalEvent],
    baseline_offset: int,
    candidate_offset: int,
    canonical_policy: CanonicalizationPolicy,
    policy: AlignmentPolicy,
    band: int,
) -> _SegmentResult | None:
    n = len(baseline)
    m = len(candidate)
    costs: dict[tuple[int, int, _State], float] = {(0, 0, "M"): 0.0}
    previous: dict[tuple[int, int, _State], _State] = {}
    for i in range(n + 1):
        center = round(i * m / n) if n else 0
        low = max(0, center - band)
        high = min(m, center + band)
        for j in range(low, high + 1):
            if i and j:
                evaluation = _evaluate_pair(
                    baseline[i - 1], candidate[j - 1], canonical_policy, policy
                )
                candidates: list[tuple[float, _State]] = [
                    (costs.get((i - 1, j - 1, state), _INF), state) for state in _STATES
                ]
                best_cost, best_previous = min(
                    candidates, key=lambda item: (item[0], _state_priority(item[1]))
                )
                if math.isfinite(best_cost):
                    costs[(i, j, "M")] = best_cost + evaluation.cost
                    previous[(i, j, "M")] = best_previous
            if i:
                gap_candidates: list[tuple[float, _State]] = [
                    (costs.get((i - 1, j, "M"), _INF) + policy.gap_open, "M"),
                    (costs.get((i - 1, j, "I"), _INF) + policy.gap_open, "I"),
                    (costs.get((i - 1, j, "D"), _INF) + policy.gap_extend, "D"),
                ]
                best_cost, best_previous = min(
                    gap_candidates, key=lambda item: (item[0], _state_priority(item[1]))
                )
                if math.isfinite(best_cost):
                    costs[(i, j, "D")] = best_cost
                    previous[(i, j, "D")] = best_previous
            if j:
                gap_candidates = [
                    (costs.get((i, j - 1, "M"), _INF) + policy.gap_open, "M"),
                    (costs.get((i, j - 1, "D"), _INF) + policy.gap_open, "D"),
                    (costs.get((i, j - 1, "I"), _INF) + policy.gap_extend, "I"),
                ]
                best_cost, best_previous = min(
                    gap_candidates, key=lambda item: (item[0], _state_priority(item[1]))
                )
                if math.isfinite(best_cost):
                    costs[(i, j, "I")] = best_cost
                    previous[(i, j, "I")] = best_previous
    terminal: list[tuple[float, _State]] = [
        (costs.get((n, m, state), _INF), state) for state in _STATES
    ]
    total_cost, state = min(terminal, key=lambda item: (item[0], _state_priority(item[1])))
    if not math.isfinite(total_cost):
        return None
    steps: list[_RawStep] = []
    touched = False
    i, j = n, m
    while i or j:
        center = round(i * m / n) if n else 0
        if 0 < i < n and abs(j - center) >= max(1, band - 1):
            touched = True
        previous_state = previous.get((i, j, state))
        if state == "M":
            evaluation = _evaluate_pair(baseline[i - 1], candidate[j - 1], canonical_policy, policy)
            steps.append(
                _RawStep(
                    baseline_offset + i - 1,
                    candidate_offset + j - 1,
                    evaluation.cost,
                    evaluation.similarity,
                )
            )
            i -= 1
            j -= 1
        elif state == "I":
            steps.append(
                _RawStep(
                    None,
                    candidate_offset + j - 1,
                    policy.gap_extend if previous_state == "I" else policy.gap_open,
                )
            )
            j -= 1
        else:
            steps.append(
                _RawStep(
                    baseline_offset + i - 1,
                    None,
                    policy.gap_extend if previous_state == "D" else policy.gap_open,
                )
            )
            i -= 1
        if previous_state is None and (i or j):
            return None
        state = previous_state or "M"
    steps.reverse()
    return _SegmentResult(steps, total_cost, touched_band=touched)


def _greedy_alignment(
    baseline: list[CanonicalEvent],
    candidate: list[CanonicalEvent],
    baseline_start: int,
    candidate_start: int,
    canonical_policy: CanonicalizationPolicy,
    policy: AlignmentPolicy,
    *,
    baseline_end: int | None = None,
    candidate_end: int | None = None,
) -> _SegmentResult:
    baseline_stop = len(baseline) if baseline_end is None else baseline_end
    candidate_stop = len(candidate) if candidate_end is None else candidate_end
    i, j = baseline_start, candidate_start
    steps: list[_RawStep] = []
    total_cost = 0.0
    lookahead = 32
    while i < baseline_stop and j < candidate_stop:
        evaluation = _evaluate_pair(baseline[i], candidate[j], canonical_policy, policy)
        if evaluation.cost <= policy.same_kind_name_change_cost:
            steps.append(_RawStep(i, j, evaluation.cost, evaluation.similarity))
            total_cost += evaluation.cost
            i += 1
            j += 1
            continue
        next_candidate = next(
            (
                offset
                for offset in range(1, min(lookahead, candidate_stop - j) + 1)
                if baseline[i].signature == candidate[j + offset].signature
            ),
            None,
        )
        next_baseline = next(
            (
                offset
                for offset in range(1, min(lookahead, baseline_stop - i) + 1)
                if baseline[i + offset].signature == candidate[j].signature
            ),
            None,
        )
        if next_candidate is not None and (
            next_baseline is None or next_candidate <= next_baseline
        ):
            for gap_index in range(next_candidate):
                gap_cost = policy.gap_open if gap_index == 0 else policy.gap_extend
                steps.append(_RawStep(None, j, gap_cost))
                total_cost += gap_cost
                j += 1
        elif next_baseline is not None:
            for gap_index in range(next_baseline):
                gap_cost = policy.gap_open if gap_index == 0 else policy.gap_extend
                steps.append(_RawStep(i, None, gap_cost))
                total_cost += gap_cost
                i += 1
        else:
            steps.append(_RawStep(i, j, evaluation.cost, evaluation.similarity))
            total_cost += evaluation.cost
            i += 1
            j += 1
    trailing_gap_index = 0
    while i < baseline_stop:
        gap_cost = policy.gap_open if trailing_gap_index == 0 else policy.gap_extend
        steps.append(_RawStep(i, None, gap_cost))
        total_cost += gap_cost
        i += 1
        trailing_gap_index += 1
    trailing_gap_index = 0
    while j < candidate_stop:
        gap_cost = policy.gap_open if trailing_gap_index == 0 else policy.gap_extend
        steps.append(_RawStep(None, j, gap_cost))
        total_cost += gap_cost
        j += 1
        trailing_gap_index += 1
    return _SegmentResult(steps, total_cost, degraded=True)


def _evaluate_pair(  # noqa: PLR0911
    baseline: CanonicalEvent,
    candidate: CanonicalEvent,
    canonical_policy: CanonicalizationPolicy,
    alignment_policy: AlignmentPolicy,
) -> _PairEvaluation:
    if baseline.signature == candidate.signature:
        return _PairEvaluation(0.0, "match", 1.0)
    if baseline.status != candidate.status:
        return _PairEvaluation(alignment_policy.status_change_cost, "change", None)
    near_match, similarity = assistant_events_are_near_match(baseline, candidate, canonical_policy)
    if near_match:
        return _PairEvaluation(
            alignment_policy.assistant_near_match_cost,
            "near_match",
            similarity,
        )
    if baseline.kind == candidate.kind and baseline.name == candidate.name:
        if _values_equal_with_tolerance(
            baseline.content,
            candidate.content,
            canonical_policy.numeric_abs_tolerance,
            canonical_policy.numeric_rel_tolerance,
        ):
            return _PairEvaluation(alignment_policy.numeric_tolerance_cost, "change", None)
        return _PairEvaluation(alignment_policy.same_kind_name_change_cost, "change", similarity)
    if baseline.kind == candidate.kind:
        return _PairEvaluation(alignment_policy.same_kind_change_cost, "change", None)
    return _PairEvaluation(alignment_policy.different_kind_cost, "change", None)


def _materialize_steps(
    raw_steps: list[_RawStep],
    baseline: list[CanonicalEvent],
    candidate: list[CanonicalEvent],
    canonical_policy: CanonicalizationPolicy,
    alignment_policy: AlignmentPolicy,
) -> list[AlignmentStep]:
    result: list[AlignmentStep] = []
    for raw in raw_steps:
        if raw.baseline_index is None:
            if raw.candidate_index is None:
                raise AssertionError("alignment step cannot contain two gaps")
            event = candidate[raw.candidate_index]
            result.append(
                AlignmentStep(
                    op="insert",
                    candidate_index=raw.candidate_index,
                    kind=event.kind,
                    cost=raw.cost,
                    field_diffs=_field_diffs(
                        None,
                        event,
                        include_call_id=canonical_policy.tool_call_id_stability == "stable",
                    ),
                )
            )
            continue
        if raw.candidate_index is None:
            event = baseline[raw.baseline_index]
            result.append(
                AlignmentStep(
                    op="delete",
                    baseline_index=raw.baseline_index,
                    kind=event.kind,
                    cost=raw.cost,
                    field_diffs=_field_diffs(
                        event,
                        None,
                        include_call_id=canonical_policy.tool_call_id_stability == "stable",
                    ),
                )
            )
            continue
        baseline_event = baseline[raw.baseline_index]
        candidate_event = candidate[raw.candidate_index]
        evaluation = _evaluate_pair(
            baseline_event, candidate_event, canonical_policy, alignment_policy
        )
        result.append(
            AlignmentStep(
                op=evaluation.op,
                baseline_index=raw.baseline_index,
                candidate_index=raw.candidate_index,
                kind=candidate_event.kind,
                cost=evaluation.cost,
                similarity=evaluation.similarity,
                field_diffs=[]
                if evaluation.op == "match"
                else _field_diffs(
                    baseline_event,
                    candidate_event,
                    include_call_id=canonical_policy.tool_call_id_stability == "stable",
                ),
            )
        )
    return result


def _field_diffs(
    baseline: CanonicalEvent | None,
    candidate: CanonicalEvent | None,
    *,
    include_call_id: bool,
) -> list[FieldDiff]:
    before = _event_view(baseline, include_call_id=include_call_id) if baseline else None
    after = _event_view(candidate, include_call_id=include_call_id) if candidate else None
    diffs: list[FieldDiff] = []
    _diff_values(before, after, "$", diffs)
    return diffs


def _event_view(event: CanonicalEvent, *, include_call_id: bool) -> dict[str, JsonValue]:
    view: dict[str, JsonValue] = {
        "actor": event.actor,
        "kind": event.kind,
        "name": event.name,
        "status": event.status,
    }
    if include_call_id:
        view["call_id"] = event.call_id
    content_key = (
        "arguments"
        if event.kind == "tool_call"
        else "result"
        if event.kind == "tool_result"
        else "content"
    )
    view[content_key] = event.content
    return view


def _diff_values(
    before: JsonValue | None,
    after: JsonValue | None,
    path: str,
    result: list[FieldDiff],
) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys()):
            child_path = f"{path}.{key}"
            if key not in before:
                result.append(FieldDiff(path=child_path, after=after[key], category="added"))
            elif key not in after:
                result.append(FieldDiff(path=child_path, before=before[key], category="removed"))
            else:
                _diff_values(before[key], after[key], child_path, result)
        return
    if isinstance(before, list) and isinstance(after, list):
        for index in range(max(len(before), len(after))):
            child_path = f"{path}[{index}]"
            if index >= len(before):
                result.append(FieldDiff(path=child_path, after=after[index], category="added"))
            elif index >= len(after):
                result.append(FieldDiff(path=child_path, before=before[index], category="removed"))
            else:
                _diff_values(before[index], after[index], child_path, result)
        return
    if before == after and type(before) is type(after):
        return
    category: Literal["type_changed", "value_changed"] = (
        "type_changed" if type(before) is not type(after) else "value_changed"
    )
    result.append(FieldDiff(path=path, before=before, after=after, category=category))


def _first_observed_divergence(
    steps: list[AlignmentStep],
    baseline: list[CanonicalEvent],
    candidate: list[CanonicalEvent],
) -> DivergencePoint | None:
    for step_index, step in enumerate(steps):
        if step.op == "match":
            continue
        return _divergence_point(step_index, step, baseline, candidate)
    return None


def _first_action_divergence(
    steps: list[AlignmentStep],
    baseline: list[CanonicalEvent],
    candidate: list[CanonicalEvent],
) -> DivergencePoint | None:
    for step_index, step in enumerate(steps):
        if step.op == "match":
            continue
        baseline_event = baseline[step.baseline_index] if step.baseline_index is not None else None
        candidate_event = (
            candidate[step.candidate_index] if step.candidate_index is not None else None
        )
        if _is_action_difference(step, baseline_event, candidate_event):
            return _divergence_point(step_index, step, baseline, candidate)
    return None


def _is_action_difference(
    step: AlignmentStep,
    baseline: CanonicalEvent | None,
    candidate: CanonicalEvent | None,
) -> bool:
    events = [event for event in (baseline, candidate) if event is not None]
    if any(event.kind in {"tool_call", "tool_result"} for event in events):
        return True
    if any(event.status in {"error", "cancelled"} for event in events):
        return True
    return any(diff.path == "$.status" for diff in step.field_diffs)


def _divergence_point(
    step_index: int,
    step: AlignmentStep,
    baseline: list[CanonicalEvent],
    candidate: list[CanonicalEvent],
) -> DivergencePoint:
    baseline_event = baseline[step.baseline_index] if step.baseline_index is not None else None
    candidate_event = candidate[step.candidate_index] if step.candidate_index is not None else None
    category = _divergence_category(step, baseline_event, candidate_event)
    return DivergencePoint(
        step_index=step_index,
        category=category,
        baseline_index=step.baseline_index,
        candidate_index=step.candidate_index,
        evidence_paths=[diff.path for diff in step.field_diffs],
    )


def _divergence_category(  # noqa: PLR0911
    step: AlignmentStep,
    baseline: CanonicalEvent | None,
    candidate: CanonicalEvent | None,
) -> DivergenceCategory:
    events = [event for event in (baseline, candidate) if event is not None]
    status_changed = any(diff.path == "$.status" for diff in step.field_diffs)
    has_termination_status = any(event.status in {"error", "cancelled"} for event in events)
    if has_termination_status and (status_changed or step.op in {"insert", "delete"}):
        return "error_or_termination_changed"
    if step.op == "insert":
        return "message_inserted"
    if step.op == "delete":
        return "message_deleted"
    if any(event.kind == "tool_call" for event in events):
        if any(diff.path == "$.name" for diff in step.field_diffs):
            return "tool_name_changed"
        return "tool_argument_changed"
    if any(event.kind == "tool_result" for event in events):
        return "tool_result_changed"
    if any(event.kind == "assistant" for event in events):
        return (
            "assistant_content_near_match"
            if step.op == "near_match"
            else "assistant_content_changed"
        )
    return "other_changed"


def _values_equal_with_tolerance(
    left: JsonValue,
    right: JsonValue,
    absolute: float,
    relative: float,
) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right and type(left) is type(right)
    if isinstance(left, int | float) and isinstance(right, int | float):
        return math.isclose(float(left), float(right), rel_tol=relative, abs_tol=absolute)
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _values_equal_with_tolerance(left[key], right[key], absolute, relative) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _values_equal_with_tolerance(a, b, absolute, relative)
            for a, b in zip(left, right, strict=True)
        )
    return left == right and type(left) is type(right)


def _matching_previous_state(
    target: float,
    match: float,
    insert: float,
    delete: float,
) -> _State:
    candidates: tuple[tuple[float, _State], ...] = (
        (match, "M"),
        (insert, "I"),
        (delete, "D"),
    )
    for value, state in candidates:
        if math.isclose(target, value, abs_tol=_EPSILON):
            return state
    return _best_state(match, insert, delete)


def _gap_previous_state(
    target: float,
    match: float,
    other_gap: float,
    same_gap: float,
    policy: AlignmentPolicy,
    *,
    extension_state: _State,
) -> _State:
    candidates: list[tuple[float, _State]] = [
        (match + policy.gap_open, "M"),
        (other_gap + policy.gap_open, "D" if extension_state == "I" else "I"),
        (same_gap + policy.gap_extend, extension_state),
    ]
    eligible = [item for item in candidates if math.isclose(target, item[0], abs_tol=_EPSILON)]
    return min(eligible or candidates, key=lambda item: (item[0], _state_priority(item[1])))[1]


def _best_state(match: float, insert: float, delete: float) -> _State:
    candidates: tuple[tuple[float, _State], ...] = (
        (match, "M"),
        (insert, "I"),
        (delete, "D"),
    )
    return min(
        candidates,
        key=lambda item: (item[0], _state_priority(item[1])),
    )[1]


def _state_value(state: _State, match: float, insert: float, delete: float) -> float:
    return {"M": match, "I": insert, "D": delete}[state]


def _state_priority(state: _State) -> int:
    return {"M": 0, "I": 1, "D": 2}[state]


def _gap_run_cost(length: int, policy: AlignmentPolicy) -> float:
    if length <= 0:
        return 0.0
    return policy.gap_open + (length - 1) * policy.gap_extend


def _gap_count(steps: list[_RawStep]) -> int:
    return sum(step.baseline_index is None or step.candidate_index is None for step in steps)


def _canonical_json(value: JsonValue) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
