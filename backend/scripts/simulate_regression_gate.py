from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from statistics import fmean

DEFAULT_SEED = 20260821
AUTHORITATIVE_NOISE_SAMPLES = 1_000
AUTHORITATIVE_BOOTSTRAP_SAMPLES = 10_000
PRESCAN_NOISE_SAMPLES = 400
PRESCAN_BOOTSTRAP_SAMPLES = 600


@dataclass(frozen=True, slots=True)
class GateSimulationResult:
    method: str
    tasks: int
    baseline_trials: int
    candidate_trials: int
    flaky_rate: float
    harm: float
    noise_split_samples: int
    bootstrap_samples: int
    noise_margin_q95: float
    regressed_probability: float


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def split_half_noise_q95(
    baseline: list[list[int]], *, seed: int, samples: int = AUTHORITATIVE_NOISE_SAMPLES
) -> float:
    randomizer = random.Random(seed)
    effects: list[float] = []
    for _ in range(samples):
        differences: list[float] = []
        for outcomes in baseline:
            shuffled = outcomes.copy()
            randomizer.shuffle(shuffled)
            midpoint = len(shuffled) // 2
            differences.append(fmean(shuffled[:midpoint]) - fmean(shuffled[midpoint:]))
        effects.append(abs(fmean(differences)))
    return percentile(effects, 0.95)


def harm_ci95(
    baseline: list[list[int]],
    candidate: list[list[int]],
    *,
    seed: int,
    samples: int = AUTHORITATIVE_BOOTSTRAP_SAMPLES,
) -> tuple[float, float]:
    task_effects = [
        fmean(baseline[index]) - fmean(candidate[index]) for index in range(len(baseline))
    ]
    randomizer = random.Random(seed)
    bootstraps = [
        fmean(randomizer.choice(task_effects) for _ in task_effects) for _ in range(samples)
    ]
    return percentile(bootstraps, 0.025), percentile(bootstraps, 0.975)


def simulate_scenario(
    *,
    tasks: int,
    baseline_trials: int,
    candidate_trials: int,
    flaky_rate: float,
    harm: float,
    seed: int = DEFAULT_SEED,
    repetitions: int = 60,
    practical_threshold: float = 0.02,
    noise_samples: int = PRESCAN_NOISE_SAMPLES,
    bootstrap_samples: int = PRESCAN_BOOTSTRAP_SAMPLES,
) -> GateSimulationResult:
    randomizer = random.Random(seed)
    margins: list[float] = []
    regressed = 0
    flaky_count = round(tasks * flaky_rate)
    harm_count = round(tasks * harm)
    for repetition in range(repetitions):
        indexes = list(range(tasks))
        randomizer.shuffle(indexes)
        flaky = set(indexes[:flaky_count])
        harmed = set(indexes[flaky_count : flaky_count + harm_count])
        baseline = [
            ([1] * (baseline_trials - 1) + [0]) if index in flaky else [1] * baseline_trials
            for index in range(tasks)
        ]
        candidate = [
            [0] * candidate_trials if index in harmed else [1] * candidate_trials
            for index in range(tasks)
        ]
        run_seed = seed + repetition * 2
        margin = split_half_noise_q95(baseline, seed=run_seed, samples=noise_samples)
        lower, _ = harm_ci95(baseline, candidate, seed=run_seed + 1, samples=bootstrap_samples)
        margins.append(margin)
        if lower > max(practical_threshold, margin):
            regressed += 1
    return GateSimulationResult(
        method="low-cost-prescan/v1",
        tasks=tasks,
        baseline_trials=baseline_trials,
        candidate_trials=candidate_trials,
        flaky_rate=flaky_rate,
        harm=harm,
        noise_split_samples=noise_samples,
        bootstrap_samples=bootstrap_samples,
        noise_margin_q95=fmean(margins),
        regressed_probability=regressed / repetitions,
    )


def scan_scenarios(seed: int = DEFAULT_SEED) -> list[GateSimulationResult]:
    return [
        simulate_scenario(
            tasks=tasks,
            baseline_trials=baseline_trials,
            candidate_trials=candidate_trials,
            flaky_rate=flaky_rate,
            harm=harm,
            seed=seed + index,
        )
        for index, (tasks, baseline_trials, candidate_trials, flaky_rate, harm) in enumerate(
            [
                (40, 4, 3, 0.10, 0.05),
                (120, 6, 4, 0.08, 0.02),
                (120, 6, 4, 0.08, 0.10),
                (120, 6, 4, 0.16, 0.10),
            ]
        )
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a deterministic low-cost pre-scan of regression gate scenarios."
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    print(json.dumps([asdict(result) for result in scan_scenarios(args.seed)], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
