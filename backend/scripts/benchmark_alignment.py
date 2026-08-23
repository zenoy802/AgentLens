from __future__ import annotations

import argparse
import json
import platform
import statistics
import time

from app.schemas.trace_contract import CanonicalMessage, CanonicalRunRow, SourceRef
from app.services.alignment import align_runs

_DEFAULT_EVENTS = 200
_DEFAULT_REPEATS = 10


def _run(trace_id: str, event_count: int, *, changed_index: int | None) -> CanonicalRunRow:
    messages = []
    for index in range(event_count):
        content = "repeated deterministic assistant event"
        if index == changed_index:
            content = "changed deterministic assistant event"
        messages.append(
            CanonicalMessage(
                event_index=index,
                role="assistant",
                content=content,
                source_ref=SourceRef(query_id=1, row_identity=f"row-{index}"),
            )
        )
    return CanonicalRunRow(
        task_id="benchmark-task",
        trace_id=trace_id,
        outcome="success",
        messages=messages,
    )


def benchmark(event_count: int, repeats: int) -> dict[str, object]:
    baseline = _run("benchmark-baseline", event_count, changed_index=None)
    candidate = _run("benchmark-candidate", event_count, changed_index=event_count // 2)
    align_runs(baseline, candidate)
    durations_ms: list[float] = []
    qualities: list[str] = []
    for _ in range(repeats):
        started_at = time.perf_counter()
        result = align_runs(baseline, candidate)
        durations_ms.append((time.perf_counter() - started_at) * 1000)
        qualities.append(result.quality)
    ordered = sorted(durations_ms)
    percentile_index = max(0, min(len(ordered) - 1, round(0.95 * len(ordered) + 0.5) - 1))
    return {
        "schema_version": "alignment-benchmark/v1",
        "events_per_side": event_count,
        "repeats": repeats,
        "median_ms": round(statistics.median(durations_ms), 3),
        "p95_ms": round(ordered[percentile_index], 3),
        "min_ms": round(min(durations_ms), 3),
        "max_ms": round(max(durations_ms), 3),
        "exact_runs": sum(quality == "exact" for quality in qualities),
        "degraded_runs": sum(quality == "degraded" for quality in qualities),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor() or "unknown",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark deterministic trajectory alignment.")
    parser.add_argument("--events", type=int, default=_DEFAULT_EVENTS)
    parser.add_argument("--repeats", type=int, default=_DEFAULT_REPEATS)
    args = parser.parse_args()
    if args.events <= 0 or args.repeats <= 0:
        parser.error("--events and --repeats must be positive")
    print(json.dumps(benchmark(args.events, args.repeats), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
