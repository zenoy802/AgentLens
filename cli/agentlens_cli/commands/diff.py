from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click


@click.command("diff", help="Align two local run-row/v1 traces and report FOD/FAD.")
@click.option(
    "--baseline-trace",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    required=True,
    help="Baseline run-row/v1 or canonical-trajectory/v1 JSON file.",
)
@click.option(
    "--candidate-trace",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    required=True,
    help="Candidate run-row/v1 or canonical-trajectory/v1 JSON file.",
)
@click.option(
    "--policy",
    "policy_file",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Optional JSON containing canonicalization_policy/alignment_policy.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(("text", "json")),
    default="text",
    show_default=True,
)
def diff_traces(
    baseline_trace: Path,
    candidate_trace: Path,
    policy_file: Path | None,
    output_format: str,
) -> None:
    """Run the pure alignment implementation without a DB, API, or worker."""
    try:
        from app.schemas.alignment import (  # noqa: PLC0415
            AlignmentPolicy,
            CanonicalizationPolicy,
            CanonicalTrajectory,
        )
        from app.schemas.trace_contract import CanonicalRunRow  # noqa: PLC0415
        from app.services.alignment import align_trajectories  # noqa: PLC0415
        from app.services.canonicalization import canonicalize_run  # noqa: PLC0415

        policy_payload = _read_json_object(policy_file) if policy_file is not None else {}
        unknown_policy_keys = set(policy_payload) - {
            "canonicalization_policy",
            "alignment_policy",
        }
        if unknown_policy_keys:
            names = ", ".join(sorted(unknown_policy_keys))
            raise ValueError(f"policy file contains unsupported fields: {names}")
        canonicalization_policy = CanonicalizationPolicy.model_validate(
            policy_payload.get("canonicalization_policy", {})
        )
        alignment_policy = AlignmentPolicy.model_validate(
            policy_payload.get("alignment_policy", {})
        )
        baseline_payload = _read_json_object(baseline_trace, key="run")
        candidate_payload = _read_json_object(candidate_trace, key="run")
        baseline = (
            CanonicalTrajectory.model_validate(baseline_payload)
            if baseline_payload.get("schema_version") == "canonical-trajectory/v1"
            else canonicalize_run(
                CanonicalRunRow.model_validate(baseline_payload), canonicalization_policy
            )
        )
        candidate = (
            CanonicalTrajectory.model_validate(candidate_payload)
            if candidate_payload.get("schema_version") == "canonical-trajectory/v1"
            else canonicalize_run(
                CanonicalRunRow.model_validate(candidate_payload), canonicalization_policy
            )
        )
        result = align_trajectories(
            baseline,
            candidate,
            canonicalization_policy=canonicalization_policy,
            alignment_policy=alignment_policy,
        )
    except ModuleNotFoundError as exc:
        missing_name = exc.name or "backend algorithm module"
        raise click.ClickException(
            "The local diff command requires the unified AgentLens package; "
            f"missing dependency: {missing_name}."
        ) from exc
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"Unable to diff traces: {exc}") from exc

    if output_format == "json":
        click.echo(result.model_dump_json(indent=2))
        return
    click.echo(f"quality: {result.quality}")
    click.echo(
        "summary: "
        f"matches={result.summary.matches} near_matches={result.summary.near_matches} "
        f"changes={result.summary.changes} insertions={result.summary.insertions} "
        f"deletions={result.summary.deletions}"
    )
    click.echo(f"first observed divergence: {_format_divergence(result.first_observed_divergence)}")
    click.echo(f"first action divergence: {_format_divergence(result.first_action_divergence)}")
    if result.warnings:
        click.echo("warnings:")
        for warning in result.warnings:
            click.echo(f"- {warning.code}: {warning.message}")


def _read_json_object(path: Path, *, key: str | None = None) -> dict[str, Any]:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object")
    if key is not None and key in payload:
        nested = payload[key]
        if not isinstance(nested, dict):
            raise ValueError(f"{path} field '{key}' must contain one JSON object")
        return nested
    return payload


def _format_divergence(value: Any) -> str:
    if value is None:
        return "none"
    return (
        f"step={value.step_index} category={value.category} "
        f"baseline={value.baseline_index} candidate={value.candidate_index}"
    )


__all__ = ["diff_traces"]
