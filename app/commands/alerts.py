from __future__ import annotations

import json
from pathlib import Path

import typer

from app.alerts.generator import build_alert_record, load_score_json, save_alert_json
from app.models import load_configs
from app.runs.snapshots import write_run_snapshot
from app.scoring.convergence import (
    load_classified_documents,
    parse_window_days,
)


router = typer.Typer(add_completion=False, help="Alert generation commands.")

@router.command("alert")
def alert(
    scenario: str = typer.Option(..., "--scenario", help="Scenario ID for alert generation."),
    window: str = typer.Option("30d", "--window", help="Alert window, e.g. 30d."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON alert."),
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
        help="Directory where run snapshots are written.",
    ),
) -> None:
    """Generate the stable JSON alert card from classified evidence and score JSON."""
    if not json_output:
        typer.secho("Only --json output is supported.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    try:
        bundle = load_configs(config_dir)
        window_days = parse_window_days(window)
        score_record = load_score_json(scenario_id=scenario, processed_dir=processed_dir)
        classified = load_classified_documents(
            scenario_id=scenario,
            processed_dir=processed_dir,
        )
        alert_record = build_alert_record(
            bundle=bundle,
            scenario_id=scenario,
            score=score_record,
            classified_documents=classified,
        )
        alert_path = save_alert_json(alert_record, processed_dir=processed_dir)
    except Exception as exc:
        typer.secho(f"Alert generation failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    run_path = write_run_snapshot(
        runs_dir=runs_dir,
        operation="alert",
        subject=scenario,
        status="ok",
        parameters={"scenario": scenario, "window": window, "json": json_output},
        inputs={
            "classified_path": str(Path(processed_dir) / f"{scenario}_classified.jsonl"),
            "score_path": str(Path(processed_dir) / f"{scenario}_score.json"),
        },
        outputs={"alert_path": str(alert_path)},
        counts={
            "document_count": alert_record.document_count,
            "evidence_count": len(alert_record.evidence),
        },
        config_dir=config_dir,
        window_days=window_days,
    )

    payload = alert_record.model_dump(mode="json")
    payload["run_snapshot_path"] = str(run_path)
    typer.echo(json.dumps(payload, indent=2))

