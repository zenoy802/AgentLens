# Session 3 Alignment Evidence

This file records measured evidence for the pure canonicalization/alignment session. It does not
upgrade design targets into product claims.

## Corpus status

- Synthetic offline golden corpus: 10 explicitly labelled pairs covering assistant near-match,
  text-before-action divergence, volatile runtime scrubbing, retry insertion/rejoin, repeated tool
  calls, tool choice/argument/result changes, status-only failure, and object/array ordering.
- Synthetic exact coverage and deliberately degraded coverage are asserted separately by
  `backend/tests/test_alignment.py`.
- Synthetic FAD category results: exact path 10/10; deliberately degraded path 1/1; combined
  11/11. Path coverage is exact 10/11 and degraded 1/11. The degraded case is one long,
  identical pair used to prove the fallback path and denominator reporting; it is not broad
  degraded-path accuracy evidence.
- Real Agent gold: **not measured**. The design release gate requires at least 50 real Agent pairs
  within a 100-pair human-labelled corpus. The collection plan remains
  `docs/real-alignment-gold-collection-plan.md`; no synthetic result is reported as real accuracy.

## Reproducible commands

```bash
cd backend
pytest -q tests/test_alignment.py
python scripts/benchmark_alignment.py --events 200 --repeats 10
```

The benchmark JSON records Python/platform data, exact/degraded counts, median, p95, min, and max.
Measured values should be copied into release evidence only from a fresh run on the named machine;
the design target of p95 below 200 ms is not itself a measured result.

## Local measurement (2026-08-22)

- Environment: macOS 15.7.3 arm64, Python 3.12.7.
- Workload: 200 × 200 repeated-signature events, one content change, 10 measured runs after warm-up.
- Result: median 29.118 ms, p95/max 31.971 ms, 10 exact and 0 degraded runs.

This is a development-machine measurement for the deterministic fixture, not a production SLA or
real-Agent accuracy measurement.
