from __future__ import annotations

import json
from pathlib import Path

import typer
from pydantic import ValidationError

from app.models import format_validation_error, load_configs
from app.scoring.baselines import (
    add_baseline_observation,
    baseline_show_payload,
    compare_score_to_baseline,
)
from app.scoring.convergence import (
    load_classified_documents,
    parse_window_days,
    score_documents,
)


router = typer.Typer(add_completion=False, help="Scenario baseline commands.")

@router.command("show")
def show_baseline(
    scenario: str = typer.Option(..., "--scenario", help="Scenario ID to inspect."),
    config_dir: Path = typer.Option(
        Path("config"),
        "--config-dir",
        help="Directory containing scenarios.yaml and sources.yaml.",
    ),
    baselines_dir: Path = typer.Option(
        Path("data/baselines"),
        "--baselines-dir",
        help="Directory containing scenario baseline JSON.",
    ),
) -> None:
    """Show stored baseline observations, or explicit baseline_unavailable status."""
    try:
        bundle = load_configs(config_dir)
        bundle.get_scenario(scenario)
        payload = baseline_show_payload(
            scenario_id=scenario,
            baselines_dir=baselines_dir,
        )
    except KeyError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.secho(f"Baseline inspection failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(json.dumps(payload, indent=2))


@router.command("update")
def update_baseline(
    scenario: str = typer.Option(..., "--scenario", help="Scenario ID to update."),
    window: str = typer.Option("30d", "--window", help="Scoring window, e.g. 30d."),
    config_dir: Path = typer.Option(
        Path("config"),
        "--config-dir",
        help="Directory containing scenarios.yaml and sources.yaml.",
    ),
    processed_dir: Path = typer.Option(
        Path("data/processed"),
        "--processed-dir",
        help="Directory containing classified JSONL.",
    ),
    baselines_dir: Path = typer.Option(
        Path("data/baselines"),
        "--baselines-dir",
        help="Directory containing scenario baseline JSON.",
    ),
) -> None:
    """Score current classified records and store one deduplicated baseline observation."""
    try:
        bundle = load_configs(config_dir)
        window_days = parse_window_days(window)
        classified = load_classified_documents(
            scenario_id=scenario,
            processed_dir=processed_dir,
        )
        score_record = score_documents(
            classified,
            bundle=bundle,
            scenario_id=scenario,
            window_days=window_days,
        )
        score_record.baseline_comparison = compare_score_to_baseline(
            score=score_record,
            baselines_dir=baselines_dir,
        )
        store, record, created, baseline_file = add_baseline_observation(
            score=score_record,
            baselines_dir=baselines_dir,
        )
    except KeyError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except ValidationError as exc:
        typer.secho("Config validation failed:", fg=typer.colors.RED, err=True)
        typer.echo(format_validation_error(exc), err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.secho(f"Baseline update failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    payload = {
        "status": "ok",
        "operation": "baseline_update",
        "scenario_id": scenario,
        "window_days": window_days,
        "baseline_path": str(baseline_file),
        "observation_id": record.observation_id,
        "observation_created": created,
        "duplicate_suppressed": not created,
        "baseline_observation_count": len(store.observations),
        "score": score_record.model_dump(mode="json"),
    }
    typer.echo(json.dumps(payload, indent=2))

