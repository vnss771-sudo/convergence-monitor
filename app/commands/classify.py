from __future__ import annotations

import json
from pathlib import Path

import typer
from pydantic import ValidationError

from app.classification.keyword_matcher import (
    classify_documents,
    load_raw_documents,
    save_classified_documents_jsonl,
)
from app.models import format_validation_error, load_configs
from app.runs.snapshots import write_run_snapshot


router = typer.Typer(add_completion=False, help="Document classification commands.")

@router.command("classify")
def classify(
    scenario: str = typer.Option(..., "--scenario", help="Scenario ID to classify against."),
    config_dir: Path = typer.Option(
        Path("config"),
        "--config-dir",
        help="Directory containing scenarios.yaml and sources.yaml.",
    ),
    raw_dir: Path = typer.Option(
        Path("data/raw"),
        "--raw-dir",
        help="Directory containing raw JSONL records from ingestion.",
    ),
    processed_dir: Path = typer.Option(
        Path("data/processed"),
        "--processed-dir",
        help="Directory where classified JSONL records are written.",
    ),
    runs_dir: Path = typer.Option(
        Path("data/runs"),
        "--runs-dir",
        help="Directory where run snapshots are written.",
    ),
) -> None:
    """Classify raw documents against one configured scenario and save processed JSONL."""
    try:
        bundle = load_configs(config_dir)
        scenario_config = bundle.get_scenario(scenario)
    except KeyError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except ValidationError as exc:
        typer.secho("Config validation failed:", fg=typer.colors.RED, err=True)
        typer.echo(format_validation_error(exc), err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.secho(f"Config loading failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    try:
        documents = load_raw_documents(raw_dir)
        classified = classify_documents(documents, scenario_config)
        output_path = save_classified_documents_jsonl(
            classified,
            scenario_id=scenario_config.id,
            processed_dir=processed_dir,
        )
    except Exception as exc:
        write_run_snapshot(
            runs_dir=runs_dir,
            operation="classify",
            subject=scenario,
            status="error",
            parameters={"scenario": scenario},
            inputs={"raw_dir": str(raw_dir)},
            outputs={},
            counts={},
            config_dir=config_dir,
            error={"type": "classification_error", "message": str(exc)},
        )
        typer.secho(f"Classification failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    counts = {
        "central": sum(1 for item in classified if item.relevance == "central"),
        "incidental": sum(1 for item in classified if item.relevance == "incidental"),
        "excluded": sum(1 for item in classified if item.relevance == "excluded"),
        "irrelevant": sum(1 for item in classified if item.relevance == "irrelevant"),
    }

    run_path = write_run_snapshot(
        runs_dir=runs_dir,
        operation="classify",
        subject=scenario_config.id,
        status="ok",
        parameters={"scenario": scenario_config.id},
        inputs={"raw_dir": str(raw_dir)},
        outputs={"classified_path": str(output_path)},
        counts={"documents_read": len(documents), "classified": len(classified), **counts},
        config_dir=config_dir,
    )

    payload = {
        "status": "ok",
        "scenario_id": scenario_config.id,
        "documents_read": len(documents),
        "classified": len(classified),
        "output_path": str(output_path),
        "counts": counts,
        "run_snapshot_path": str(run_path),
    }
    typer.echo(json.dumps(payload, indent=2))

