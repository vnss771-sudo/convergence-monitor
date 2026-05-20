from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.alerts.generator import load_score_json
from app.ingestion.failures import load_source_health
from app.models import AlertRecord, ConfigBundle, ScenarioScoreRecord
from app.runs.snapshots import list_run_snapshots
from app.scoring.baselines import baseline_show_payload, compare_score_to_baseline


STATUS_OPERATIONS = ("ingest", "classify", "score", "alert")


def _missing_score_section() -> dict[str, Any]:
    return {
        "exists": False,
        "convergence_score": None,
        "confidence": None,
        "active_source_categories": 0,
        "documents_considered": 0,
    }


def _score_section(score: ScenarioScoreRecord) -> dict[str, Any]:
    return {
        "exists": True,
        "convergence_score": score.convergence_score,
        "confidence": score.confidence,
        "active_source_categories": score.active_source_categories,
        "documents_considered": score.documents_considered,
    }


def load_alert_record(
    *,
    scenario_id: str,
    processed_dir: Path | str = Path("data/processed"),
) -> AlertRecord | None:
    alert_path = Path(processed_dir) / f"{scenario_id}_alert.json"
    if not alert_path.exists():
        return None
    return AlertRecord.model_validate_json(alert_path.read_text(encoding="utf-8"))


def _alert_section(alert: AlertRecord | None) -> dict[str, Any]:
    if alert is None:
        return {
            "exists": False,
            "generated_at": None,
            "evidence_count": 0,
        }

    return {
        "exists": True,
        "generated_at": alert.generated_at,
        "evidence_count": len(alert.evidence),
    }


def _baseline_section(
    *,
    scenario_id: str,
    baselines_dir: Path | str,
    score: ScenarioScoreRecord | None,
) -> dict[str, Any]:
    baseline_payload = baseline_show_payload(
        scenario_id=scenario_id,
        baselines_dir=baselines_dir,
    )

    comparison = "not_available"
    if score is not None:
        comparison = compare_score_to_baseline(
            score=score,
            baselines_dir=baselines_dir,
        ).comparison
    elif baseline_payload["status"] == "baseline_unavailable":
        comparison = "not_enough_history"

    return {
        "status": baseline_payload["status"],
        "observation_count": baseline_payload["baseline_observation_count"],
        "comparison": comparison,
    }


def source_health_summary(
    *,
    bundle: ConfigBundle,
    runs_dir: Path | str = Path("data/runs"),
) -> dict[str, Any]:
    enabled_source_ids = [source.id for source in bundle.enabled_sources]
    health_payload = load_source_health(runs_dir)
    health_sources = health_payload.get("sources", {})

    sources_ok = 0
    sources_error = 0
    sources_unknown = 0

    for source_id in enabled_source_ids:
        status = health_sources.get(source_id, {}).get("status")
        if status == "ok":
            sources_ok += 1
        elif status is None:
            sources_unknown += 1
        else:
            sources_error += 1

    if not enabled_source_ids:
        overall = "unavailable"
    elif sources_error:
        overall = "degraded" if sources_ok or sources_unknown else "error"
    elif sources_unknown:
        overall = "unknown"
    else:
        overall = "ok"

    return {
        "sources_total": len(enabled_source_ids),
        "sources_ok": sources_ok,
        "sources_error": sources_error,
        "sources_unknown": sources_unknown,
        "overall": overall,
    }


def latest_run_statuses(
    *,
    scenario_id: str,
    runs_dir: Path | str = Path("data/runs"),
) -> dict[str, str]:
    latest = {operation: "missing" for operation in STATUS_OPERATIONS}

    for snapshot in list_run_snapshots(runs_dir):
        operation = snapshot.get("operation")
        if operation not in latest:
            continue

        subject = snapshot.get("subject")
        if operation != "ingest" and subject != scenario_id:
            continue

        latest[operation] = str(snapshot.get("status", "unknown"))

    return latest


def build_scenario_status(
    *,
    bundle: ConfigBundle,
    scenario_id: str,
    window_days: int,
    processed_dir: Path | str = Path("data/processed"),
    runs_dir: Path | str = Path("data/runs"),
    baselines_dir: Path | str = Path("data/baselines"),
) -> dict[str, Any]:
    scenario = bundle.get_scenario(scenario_id)
    warnings: list[str] = []

    score_record: ScenarioScoreRecord | None = None
    try:
        score_record = load_score_json(
            scenario_id=scenario_id,
            processed_dir=processed_dir,
        )
    except FileNotFoundError:
        warnings.append("score_json_missing")
    except (ValidationError, ValueError, json.JSONDecodeError):
        warnings.append("score_json_invalid")

    alert_record: AlertRecord | None = None
    try:
        alert_record = load_alert_record(
            scenario_id=scenario_id,
            processed_dir=processed_dir,
        )
    except (ValidationError, ValueError, json.JSONDecodeError):
        warnings.append("alert_json_invalid")

    if alert_record is None:
        alert_path = Path(processed_dir) / f"{scenario_id}_alert.json"
        if not alert_path.exists():
            warnings.append("alert_json_missing")

    baseline = _baseline_section(
        scenario_id=scenario_id,
        baselines_dir=baselines_dir,
        score=score_record,
    )
    if baseline["status"] == "baseline_unavailable":
        warnings.append("baseline_unavailable")

    latest_runs = latest_run_statuses(scenario_id=scenario_id, runs_dir=runs_dir)
    for operation, run_status in latest_runs.items():
        if run_status == "missing":
            warnings.append(f"{operation}_run_missing")
        elif run_status not in {"ok", "degraded"}:
            warnings.append(f"{operation}_run_{run_status}")

    return {
        "status": "ok",
        "scenario_id": scenario.id,
        "scenario_name": scenario.name,
        "window_days": window_days,
        "score": (
            _score_section(score_record)
            if score_record is not None
            else _missing_score_section()
        ),
        "alert": _alert_section(alert_record),
        "baseline": baseline,
        "source_health": source_health_summary(bundle=bundle, runs_dir=runs_dir),
        "latest_runs": latest_runs,
        "warnings": sorted(set(warnings)),
    }
