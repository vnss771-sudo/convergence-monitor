from __future__ import annotations

import json
from pathlib import Path

import typer

from app.ingestion.failures import (
    load_source_health,
    summarize_source_health_payload,
)
from app.runs.snapshots import list_run_snapshots


router = typer.Typer(add_completion=False, help="Run snapshot inspection commands.")

@router.command("list")
def list_runs(
    runs_dir: Path = typer.Option(
        Path("data/runs"),
        "--runs-dir",
        help="Directory containing run snapshots.",
    )
) -> None:
    """List run snapshots as stable JSON."""
    snapshots = list_run_snapshots(runs_dir)
    payload = {
        "status": "ok",
        "run_count": len(snapshots),
        "runs": snapshots,
    }
    typer.echo(json.dumps(payload, indent=2))


@router.command("health")
def source_health(
    runs_dir: Path = typer.Option(
        Path("data/runs"),
        "--runs-dir",
        help="Directory containing source health records.",
    )
) -> None:
    """Return latest source-health status as stable JSON."""
    payload = load_source_health(runs_dir)
    summary = summarize_source_health_payload(payload)
    typer.echo(json.dumps({"status": "ok", **payload, "summary": summary}, indent=2))

