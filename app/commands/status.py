from __future__ import annotations

import json
from pathlib import Path

import typer
from pydantic import ValidationError

from app.models import format_validation_error, load_configs
from app.scoring.convergence import (
    parse_window_days,
)
from app.status import build_scenario_status


router = typer.Typer(add_completion=False, help="Scenario status commands.")

@router.command("status")
def scenario_status(
    scenario: str = typer.Option(..., "--scenario", help="Scenario ID to summarize."),
    window: str = typer.Option("30d", "--window", help="Status window, e.g. 30d."),
    config_dir: Path = typer.Option(
        Path("config"),
        "--config-dir",
        help="Directory containing scenarios.yaml and sources.yaml.",
    ),
    processed_dir: Path = typer.Option(
        Path("data/processed"),
        "--processed-dir",
        help="Directory containing classified, score, and alert output.",
    ),
    runs_dir: Path = typer.Option(
        Path("data/runs"),
        "--runs-dir",
        help="Directory containing run snapshots and source health records.",
    ),
    baselines_dir: Path = typer.Option(
        Path("data/baselines"),
        "--baselines-dir",
        help="Directory containing scenario baseline JSON.",
    ),
) -> None:
    """Summarize scenario score, alert, baseline, source health, and latest runs."""
    try:
        bundle = load_configs(config_dir)
        window_days = parse_window_days(window)
        payload = build_scenario_status(
            bundle=bundle,
            scenario_id=scenario,
            window_days=window_days,
            processed_dir=processed_dir,
            runs_dir=runs_dir,
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
        typer.secho(f"Status summary failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(json.dumps(payload, indent=2))

