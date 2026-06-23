from __future__ import annotations

import json
from pathlib import Path

import typer
from pydantic import ValidationError

from app.live_acceptance import evaluate_live_acceptance, load_live_verification_payload
from app.live_verification import run_live_verification
from app.live_review import build_and_write_live_review_pack
from app.live_history import build_live_history
from app.models import format_validation_error, load_configs
from app.scoring.convergence import (
    parse_window_days,
)


router = typer.Typer(add_completion=False, help="Live verification and review commands.")

@router.command("verify-live")
def verify_live(
    scenario: str = typer.Option(..., "--scenario", help="Scenario ID to verify live."),
    window: str = typer.Option("30d", "--window", help="Verification window, e.g. 30d."),
    limit: int = typer.Option(10, "--limit", min=1, help="Maximum records per source."),
    config_dir: Path = typer.Option(
        Path("config"),
        "--config-dir",
        help="Directory containing scenarios.yaml and sources.yaml.",
    ),
    raw_dir: Path = typer.Option(
        Path("data/raw"),
        "--raw-dir",
        help="Directory where live raw JSONL records are written.",
    ),
    processed_dir: Path = typer.Option(
        Path("data/processed"),
        "--processed-dir",
        help="Directory where classified, score, and alert output is written.",
    ),
    runs_dir: Path = typer.Option(
        Path("data/runs"),
        "--runs-dir",
        help="Directory where run snapshots and verification artifacts are written.",
    ),
    baselines_dir: Path = typer.Option(
        Path("data/baselines"),
        "--baselines-dir",
        help="Directory containing scenario baseline JSON.",
    ),
    replace: bool = typer.Option(
        False,
        "--replace",
        help="Replace per-source raw JSONL files during verification.",
    ),
) -> None:
    """Run live source verification and report honest source/pipeline status."""
    try:
        bundle = load_configs(config_dir)
        window_days = parse_window_days(window)
        payload = run_live_verification(
            bundle=bundle,
            scenario_id=scenario,
            window_days=window_days,
            limit=limit,
            raw_dir=raw_dir,
            processed_dir=processed_dir,
            runs_dir=runs_dir,
            baselines_dir=baselines_dir,
            config_dir=config_dir,
            replace=replace,
        )
    except KeyError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except ValidationError as exc:
        typer.secho("Config validation failed:", fg=typer.colors.RED, err=True)
        typer.echo(format_validation_error(exc), err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.secho(f"Live verification failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(json.dumps(payload, indent=2))
    if payload["status"] == "error":
        raise typer.Exit(code=1)


@router.command("accept-live")
def accept_live(
    verification_path: Path = typer.Option(
        ...,
        "--verification",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to a verify-live JSON artifact.",
    ),
    require_baseline: bool = typer.Option(
        False,
        "--require-baseline",
        help="Reject otherwise usable live runs when baseline_available is false.",
    ),
) -> None:
    """Evaluate a verify-live artifact against the live acceptance gate."""
    try:
        verification_payload = load_live_verification_payload(verification_path)
        payload = evaluate_live_acceptance(
            verification_payload,
            verification_path=verification_path,
            require_baseline=require_baseline,
        )
    except Exception as exc:
        typer.secho(f"Live acceptance evaluation failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(json.dumps(payload, indent=2))
    if payload["decision"] == "rejected":
        raise typer.Exit(code=1)


@router.command("review-live")
def review_live(
    verification_path: Path = typer.Option(
        ...,
        "--verification",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to a verify-live JSON artifact.",
    ),
    output_dir: Path = typer.Option(
        Path("data/runs/live_reviews"),
        "--output-dir",
        help="Directory where live review-pack JSON artifacts are written.",
    ),
    require_baseline: bool = typer.Option(
        False,
        "--require-baseline",
        help="Mark the review pack rejected when baseline_available is false.",
    ),
) -> None:
    """Build a deterministic operator review pack from a verify-live artifact."""
    try:
        payload = build_and_write_live_review_pack(
            verification_path=verification_path,
            output_dir=output_dir,
            require_baseline=require_baseline,
        )
    except Exception as exc:
        typer.secho(f"Live review pack generation failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(json.dumps(payload, indent=2))


@router.command("live-history")
def live_history(
    scenario: str | None = typer.Option(
        None,
        "--scenario",
        help="Optional scenario ID to filter live verification history.",
    ),
    runs_dir: Path = typer.Option(
        Path("data/runs"),
        "--runs-dir",
        help="Directory containing live verification and review-pack artifacts.",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        min=1,
        help="Maximum recent live verification artifacts to summarize.",
    ),
    require_baseline: bool = typer.Option(
        False,
        "--require-baseline",
        help="Evaluate live history with the stricter baseline-required gate.",
    ),
) -> None:
    """Summarize recent live verification artifacts and review coverage."""
    try:
        payload = build_live_history(
            scenario_id=scenario,
            runs_dir=runs_dir,
            limit=limit,
            require_baseline=require_baseline,
        )
    except Exception as exc:
        typer.secho(f"Live history summary failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(json.dumps(payload, indent=2))

