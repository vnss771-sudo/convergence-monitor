from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError

from app.alerts.generator import build_alert_record, load_score_json, save_alert_json
from app.classification.keyword_matcher import (
    classify_documents,
    load_raw_documents,
    save_classified_documents_jsonl,
)
from app.ingestion.failures import (
    ingestion_error_payload,
    load_source_health,
    update_source_health,
)
from app.ingestion.rss_base import EmptyFeedError, IngestionError, fetch_rss_documents, save_documents_jsonl
from app.live_acceptance import evaluate_live_acceptance, load_live_verification_payload
from app.live_verification import run_live_verification
from app.live_review import build_and_write_live_review_pack
from app.live_history import build_live_history
from app.models import Source, config_summary, format_validation_error, load_configs
from app.runs.snapshots import list_run_snapshots, write_run_snapshot
from app.scoring.baselines import (
    add_baseline_observation,
    baseline_show_payload,
    compare_score_to_baseline,
)
from app.scoring.convergence import (
    load_classified_documents,
    parse_window_days,
    save_score_json,
    score_documents,
)
from app.status import build_scenario_status

app = typer.Typer(
    add_completion=False,
    help="Convergence Monitor command-line interface.",
)
runs_app = typer.Typer(
    add_completion=False,
    help="Inspect run snapshots.",
)
baselines_app = typer.Typer(
    add_completion=False,
    help="Inspect and update scenario baselines.",
)
app.add_typer(runs_app, name="runs")
app.add_typer(baselines_app, name="baselines")


@app.command("validate-config")
def validate_config(
    config_dir: Path = typer.Option(
        Path("config"),
        "--config-dir",
        help="Directory containing scenarios.yaml and sources.yaml.",
    )
) -> None:
    """Validate scenario and source configuration files."""
    try:
        bundle = load_configs(config_dir)
    except FileNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except ValidationError as exc:
        typer.secho("Config validation failed:", fg=typer.colors.RED, err=True)
        typer.echo(format_validation_error(exc), err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.secho(f"Config validation failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(json.dumps({"status": "ok", **config_summary(bundle)}, indent=2))


def _raw_path(raw_dir: Path | str, source_id: str) -> str:
    return str(Path(raw_dir) / f"{source_id}.jsonl")


def _ingest_one_source(
    *,
    source_config: Source,
    limit: int,
    raw_dir: Path,
    runs_dir: Path,
    config_dir: Path,
    replace: bool,
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    """Ingest one source and return a structured success or failure payload."""

    parameters = {
        "source": source_config.id,
        "limit": limit,
        "replace": replace,
        "timeout_seconds": timeout_seconds,
    }
    inputs = {"source_url": str(source_config.url)}
    raw_path = _raw_path(raw_dir, source_config.id)

    try:
        documents = fetch_rss_documents(
            source_config,
            limit=limit,
            timeout_seconds=timeout_seconds,
        )
        fetched_entries = int(getattr(documents, "fetched_entries", len(documents)))
        skipped_invalid_entries = int(getattr(documents, "skipped_invalid_entries", 0))
        save_result = save_documents_jsonl(
            documents,
            source_id=source_config.id,
            raw_dir=raw_dir,
            replace=replace,
        )
    except IngestionError as exc:
        error = ingestion_error_payload(source_id=source_config.id, message=str(exc))
        run_path = write_run_snapshot(
            runs_dir=runs_dir,
            operation="ingest",
            subject=source_config.id,
            status="error",
            parameters=parameters,
            inputs=inputs,
            outputs={"raw_path": raw_path},
            counts={
                "fetched": 0,
                "saved": 0,
                "skipped_existing": 0,
            "skipped_invalid_entries": 0,
                "sources_attempted": 1,
                "sources_succeeded": 0,
                "sources_failed": 1,
            },
            config_dir=config_dir,
            error=error,
        )
        update_source_health(
            runs_dir=runs_dir,
            source_id=source_config.id,
            status="error",
            counts={"fetched": 0, "saved": 0, "skipped_existing": 0},
            error=error,
        )
        return {
            "status": "error",
            "operation": "ingest",
            "source_id": source_config.id,
            "source_name": source_config.name,
            "error": error,
            "fetched": 0,
            "saved": 0,
            "skipped_existing": 0,
            "skipped_invalid_entries": 0,
            "raw_path": raw_path,
            "empty_feed": isinstance(exc, EmptyFeedError),
            "run_snapshot_path": str(run_path),
        }
    except Exception as exc:
        error = ingestion_error_payload(
            source_id=source_config.id,
            error_type="unexpected_ingestion_error",
            message=str(exc),
        )
        run_path = write_run_snapshot(
            runs_dir=runs_dir,
            operation="ingest",
            subject=source_config.id,
            status="error",
            parameters=parameters,
            inputs=inputs,
            outputs={"raw_path": raw_path},
            counts={
                "fetched": 0,
                "saved": 0,
                "skipped_existing": 0,
            "skipped_invalid_entries": 0,
                "sources_attempted": 1,
                "sources_succeeded": 0,
                "sources_failed": 1,
            },
            config_dir=config_dir,
            error=error,
        )
        update_source_health(
            runs_dir=runs_dir,
            source_id=source_config.id,
            status="error",
            counts={"fetched": 0, "saved": 0, "skipped_existing": 0},
            error=error,
        )
        return {
            "status": "error",
            "operation": "ingest",
            "source_id": source_config.id,
            "source_name": source_config.name,
            "error": error,
            "fetched": 0,
            "saved": 0,
            "skipped_existing": 0,
            "skipped_invalid_entries": 0,
            "raw_path": raw_path,
            "run_snapshot_path": str(run_path),
        }

    run_path = write_run_snapshot(
        runs_dir=runs_dir,
        operation="ingest",
        subject=source_config.id,
        status="ok",
        parameters=parameters,
        inputs=inputs,
        outputs={"raw_path": save_result.raw_path},
        counts={
            "fetched": save_result.fetched,
            "saved": save_result.saved,
            "skipped_existing": save_result.skipped_existing,
            "fetched_entries": fetched_entries,
            "skipped_invalid_entries": skipped_invalid_entries,
            "sources_attempted": 1,
            "sources_succeeded": 1,
            "sources_failed": 0,
        },
        config_dir=config_dir,
    )
    update_source_health(
        runs_dir=runs_dir,
        source_id=source_config.id,
        status="ok",
        counts={
            "fetched": save_result.fetched,
            "saved": save_result.saved,
            "skipped_existing": save_result.skipped_existing,
            "fetched_entries": fetched_entries,
            "skipped_invalid_entries": skipped_invalid_entries,
        },
    )

    return {
        "status": "ok",
        "operation": "ingest",
        "source_id": source_config.id,
        "source_name": source_config.name,
        "fetched": save_result.fetched,
        "saved": save_result.saved,
        "skipped_existing": save_result.skipped_existing,
            "fetched_entries": fetched_entries,
            "skipped_invalid_entries": skipped_invalid_entries,
        "raw_path": save_result.raw_path,
        "run_snapshot_path": str(run_path),
    }


@app.command("ingest")
def ingest(
    source: str = typer.Option(..., "--source", help="Source ID to ingest, or 'all'."),
    limit: int = typer.Option(10, "--limit", min=1, help="Maximum records to fetch."),
    timeout_seconds: float = typer.Option(
        20.0,
        "--timeout-seconds",
        min=1.0,
        help="Per-source RSS fetch timeout in seconds.",
    ),
    config_dir: Path = typer.Option(
        Path("config"),
        "--config-dir",
        help="Directory containing scenarios.yaml and sources.yaml.",
    ),
    raw_dir: Path = typer.Option(
        Path("data/raw"),
        "--raw-dir",
        help="Directory where raw JSONL records are written.",
    ),
    runs_dir: Path = typer.Option(
        Path("data/runs"),
        "--runs-dir",
        help="Directory where run snapshots are written.",
    ),
    replace: bool = typer.Option(
        False,
        "--replace",
        help="Replace the source JSONL file instead of append/dedupe writing.",
    ),
) -> None:
    """Fetch RSS items and append/dedupe raw records.

    PR 7 supports one source at a time plus ``--source all`` for degraded
    multi-source runs. Failures are returned as structured JSON and written to
    run snapshots; they do not corrupt existing raw files.
    """

    try:
        bundle = load_configs(config_dir)
    except ValidationError as exc:
        typer.secho("Config validation failed:", fg=typer.colors.RED, err=True)
        typer.echo(format_validation_error(exc), err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.secho(f"Config loading failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if source == "all":
        results = [
            _ingest_one_source(
                source_config=source_config,
                limit=limit,
                raw_dir=raw_dir,
                runs_dir=runs_dir,
                config_dir=config_dir,
                replace=replace,
                timeout_seconds=timeout_seconds,
            )
            for source_config in bundle.enabled_sources
        ]
        failures = [result for result in results if result["status"] == "error"]
        successes = [result for result in results if result["status"] == "ok"]

        if not failures:
            status = "ok"
        elif successes:
            status = "degraded"
        else:
            status = "error"

        global_run_path = write_run_snapshot(
            runs_dir=runs_dir,
            operation="ingest",
            subject="all",
            status=status,
            parameters={
            "source": "all",
            "limit": limit,
            "replace": replace,
            "timeout_seconds": timeout_seconds,
        },
            inputs={"source_ids": [item.id for item in bundle.enabled_sources]},
            outputs={
                "raw_paths": [
                    result["raw_path"] for result in results if result.get("raw_path")
                ]
            },
            counts={
                "sources_attempted": len(results),
                "sources_succeeded": len(successes),
                "sources_failed": len(failures),
                "fetched": sum(int(result.get("fetched", 0)) for result in results),
                "saved": sum(int(result.get("saved", 0)) for result in results),
                "skipped_existing": sum(
                    int(result.get("skipped_existing", 0)) for result in results
                ),
                "skipped_invalid_entries": sum(
                    int(result.get("skipped_invalid_entries", 0)) for result in results
                ),
            },
            config_dir=config_dir,
            error={
                "type": "degraded_ingestion",
                "message": "One or more sources failed during ingestion.",
                "failed_sources": [failure["source_id"] for failure in failures],
            }
            if failures
            else None,
        )

        payload = {
            "status": status,
            "operation": "ingest",
            "sources_attempted": len(results),
            "sources_succeeded": len(successes),
            "sources_failed": len(failures),
            "fetched": sum(int(result.get("fetched", 0)) for result in results),
            "saved": sum(int(result.get("saved", 0)) for result in results),
            "skipped_existing": sum(
                int(result.get("skipped_existing", 0)) for result in results
            ),
            "skipped_invalid_entries": sum(
                int(result.get("skipped_invalid_entries", 0)) for result in results
            ),
            "results": results,
            "failures": failures,
            "run_snapshot_path": str(global_run_path),
        }
        typer.echo(json.dumps(payload, indent=2))
        if status == "error":
            raise typer.Exit(code=1)
        return

    try:
        source_config = bundle.get_source(source)
    except KeyError as exc:
        error = ingestion_error_payload(
            source_id=source,
            error_type="unknown_source",
            message=str(exc),
        )
        run_path = write_run_snapshot(
            runs_dir=runs_dir,
            operation="ingest",
            subject=source,
            status="error",
            parameters={
            "source": source,
            "limit": limit,
            "replace": replace,
            "timeout_seconds": timeout_seconds,
        },
            inputs={},
            outputs={"raw_path": _raw_path(raw_dir, source)},
            counts={
                "fetched": 0,
                "saved": 0,
                "skipped_existing": 0,
            "skipped_invalid_entries": 0,
                "sources_attempted": 1,
                "sources_succeeded": 0,
                "sources_failed": 1,
            },
            config_dir=config_dir,
            error=error,
        )
        update_source_health(
            runs_dir=runs_dir,
            source_id=source,
            status="error",
            counts={"fetched": 0, "saved": 0, "skipped_existing": 0},
            error=error,
        )
        payload = {
            "status": "error",
            "operation": "ingest",
            "source_id": source,
            "error": error,
            "fetched": 0,
            "saved": 0,
            "skipped_existing": 0,
            "skipped_invalid_entries": 0,
            "raw_path": _raw_path(raw_dir, source),
            "run_snapshot_path": str(run_path),
        }
        typer.echo(json.dumps(payload, indent=2))
        raise typer.Exit(code=1) from exc

    if not source_config.enabled:
        error = ingestion_error_payload(
            source_id=source,
            error_type="source_disabled",
            message=f"Source is disabled: {source}",
        )
        raw_path = _raw_path(raw_dir, source)
        run_path = write_run_snapshot(
            runs_dir=runs_dir,
            operation="ingest",
            subject=source,
            status="error",
            parameters={
            "source": source,
            "limit": limit,
            "replace": replace,
            "timeout_seconds": timeout_seconds,
        },
            inputs={"source_url": str(source_config.url)},
            outputs={"raw_path": raw_path},
            counts={
                "fetched": 0,
                "saved": 0,
                "skipped_existing": 0,
            "skipped_invalid_entries": 0,
                "sources_attempted": 1,
                "sources_succeeded": 0,
                "sources_failed": 1,
            },
            config_dir=config_dir,
            error=error,
        )
        update_source_health(
            runs_dir=runs_dir,
            source_id=source,
            status="error",
            counts={"fetched": 0, "saved": 0, "skipped_existing": 0},
            error=error,
        )
        payload = {
            "status": "error",
            "operation": "ingest",
            "source_id": source,
            "error": error,
            "fetched": 0,
            "saved": 0,
            "skipped_existing": 0,
            "skipped_invalid_entries": 0,
            "raw_path": raw_path,
            "run_snapshot_path": str(run_path),
        }
        typer.echo(json.dumps(payload, indent=2))
        raise typer.Exit(code=1)

    payload = _ingest_one_source(
        source_config=source_config,
        limit=limit,
        raw_dir=raw_dir,
        runs_dir=runs_dir,
        config_dir=config_dir,
        replace=replace,
        timeout_seconds=timeout_seconds,
    )
    typer.echo(json.dumps(payload, indent=2))
    if payload["status"] == "error":
        raise typer.Exit(code=1)


@app.command("classify")
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


@app.command("score")
def score(
    scenario: str = typer.Option(..., "--scenario", help="Scenario ID to score."),
    window: str = typer.Option("30d", "--window", help="Scoring window, e.g. 30d."),
    config_dir: Path = typer.Option(
        Path("config"),
        "--config-dir",
        help="Directory containing scenarios.yaml and sources.yaml.",
    ),
    processed_dir: Path = typer.Option(
        Path("data/processed"),
        "--processed-dir",
        help="Directory containing classified JSONL and score output.",
    ),
    runs_dir: Path = typer.Option(
        Path("data/runs"),
        "--runs-dir",
        help="Directory where run snapshots are written.",
    ),
    baselines_dir: Path = typer.Option(
        Path("data/baselines"),
        "--baselines-dir",
        help="Directory containing scenario baseline JSON.",
    ),
    update_baseline: bool = typer.Option(
        False,
        "--update-baseline",
        help="Store this score as a baseline observation after comparison.",
    ),
) -> None:
    """Score classified documents for one scenario and save deterministic JSON."""
    baseline_update: dict[str, Any] | None = None
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
        ).model_dump(mode="json")
        score_path = save_score_json(score_record, processed_dir=processed_dir)

        if update_baseline:
            store, record, created, baseline_file = add_baseline_observation(
                score=score_record,
                baselines_dir=baselines_dir,
            )
            baseline_update = {
                "baseline_path": str(baseline_file),
                "observation_id": record.observation_id,
                "observation_created": created,
                "duplicate_suppressed": not created,
                "baseline_observation_count": len(store.observations),
            }
    except KeyError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except ValidationError as exc:
        typer.secho("Config validation failed:", fg=typer.colors.RED, err=True)
        typer.echo(format_validation_error(exc), err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.secho(f"Scoring failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    outputs = {"score_path": str(score_path)}
    if baseline_update is not None:
        outputs["baseline_path"] = baseline_update["baseline_path"]

    counts = {
        "documents_considered": score_record.documents_considered,
        "central_documents": score_record.central_documents,
        "incidental_documents": score_record.incidental_documents,
        "excluded_documents": score_record.excluded_documents,
        "irrelevant_documents": score_record.irrelevant_documents,
    }
    if baseline_update is not None:
        counts["baseline_observation_created"] = baseline_update["observation_created"]
        counts["baseline_observation_count"] = baseline_update["baseline_observation_count"]

    run_path = write_run_snapshot(
        runs_dir=runs_dir,
        operation="score",
        subject=scenario,
        status="ok",
        parameters={
            "scenario": scenario,
            "window": window,
            "update_baseline": update_baseline,
        },
        inputs={
            "classified_path": str(
                Path(processed_dir) / f"{scenario}_classified.jsonl"
            )
        },
        outputs=outputs,
        counts=counts,
        config_dir=config_dir,
        window_days=window_days,
    )

    payload = score_record.model_dump(mode="json")
    if baseline_update is not None:
        payload["baseline_update"] = baseline_update
    payload["run_snapshot_path"] = str(run_path)
    typer.echo(json.dumps(payload, indent=2))


@baselines_app.command("show")
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


@baselines_app.command("update")
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
        ).model_dump(mode="json")
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




@app.command("verify-live")
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


@app.command("accept-live")
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


@app.command("review-live")
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



@app.command("live-history")
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



@app.command("status")
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

@app.command("alert")
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


@runs_app.command("list")
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


@runs_app.command("health")
def source_health(
    runs_dir: Path = typer.Option(
        Path("data/runs"),
        "--runs-dir",
        help="Directory containing source health records.",
    )
) -> None:
    """Return latest source-health status as stable JSON."""
    payload = load_source_health(runs_dir)
    typer.echo(json.dumps({"status": "ok", **payload}, indent=2))


if __name__ == "__main__":
    app()
