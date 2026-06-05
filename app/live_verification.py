from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.alerts.generator import build_alert_record, save_alert_json
from app.classification.keyword_matcher import classify_documents, save_classified_documents_jsonl
from app.ingestion.failures import ingestion_error_payload, update_source_health
from app.ingestion.rss_base import fetch_rss_documents, save_documents_jsonl
from app.models import ConfigBundle, DocumentRecord
from app.runs.snapshots import make_run_id, utc_now_iso, write_run_snapshot
from app.scoring.baselines import baseline_show_payload, compare_score_to_baseline
from app.scoring.convergence import save_score_json, score_documents


ERROR_STATUSES = {"timeout", "parse_error", "network_error"}


def categorize_source_exception(exc: Exception) -> str:
    """Map messy fetch exceptions to the small PR 12 source-status vocabulary."""

    class_name = exc.__class__.__name__.lower()
    message = str(exc).lower()

    if "timeout" in class_name or "timeout" in message or "timed out" in message:
        return "timeout"
    if "parse" in class_name or "parse" in message or "bozo" in message:
        return "parse_error"
    return "network_error"


def _source_error_payload(source_id: str, status: str, exc: Exception) -> dict[str, str]:
    error_type = {
        "timeout": "source_timeout",
        "parse_error": "source_parse_error",
        "network_error": "source_network_error",
    }.get(status, "source_network_error")
    return ingestion_error_payload(
        source_id=source_id,
        error_type=error_type,
        message=str(exc),
    )


def _source_outcome(
    *,
    source_id: str,
    source_name: str,
    status: str,
    fetched: int = 0,
    saved: int = 0,
    skipped_existing: int = 0,
    raw_path: str | None = None,
    error: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_id": source_id,
        "source_name": source_name,
        "status": status,
        "fetched": fetched,
        "saved": saved,
        "skipped_existing": skipped_existing,
    }
    if raw_path is not None:
        payload["raw_path"] = raw_path
    if error is not None:
        payload["error"] = error
    return payload


def _verification_status(source_outcomes: list[dict[str, Any]], documents_ingested: int) -> str:
    disabled_present = any(outcome["status"] == "disabled" for outcome in source_outcomes)
    enabled_outcomes = [
        outcome for outcome in source_outcomes if outcome["status"] != "disabled"
    ]
    if not enabled_outcomes:
        return "error"

    statuses = {str(outcome["status"]) for outcome in enabled_outcomes}
    if statuses == {"ok"} and not disabled_present:
        return "ok"
    if documents_ingested > 0 or statuses.intersection({"ok", "empty"}):
        return "degraded"
    return "error"


def _source_counts(source_outcomes: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "sources_total": len(source_outcomes),
        "sources_ok": sum(1 for item in source_outcomes if item["status"] == "ok"),
        "sources_empty": sum(1 for item in source_outcomes if item["status"] == "empty"),
        "sources_timeout": sum(1 for item in source_outcomes if item["status"] == "timeout"),
        "sources_parse_error": sum(
            1 for item in source_outcomes if item["status"] == "parse_error"
        ),
        "sources_network_error": sum(
            1 for item in source_outcomes if item["status"] == "network_error"
        ),
        "sources_disabled": sum(
            1 for item in source_outcomes if item["status"] == "disabled"
        ),
    }


def _warnings(source_outcomes: list[dict[str, Any]], documents_ingested: int) -> list[str]:
    warnings: list[str] = []
    for outcome in source_outcomes:
        status = str(outcome["status"])
        source_id = str(outcome["source_id"])
        if status == "empty":
            warnings.append(f"source_empty:{source_id}")
        elif status in ERROR_STATUSES:
            warnings.append(f"source_{status}:{source_id}")
        elif status == "disabled":
            warnings.append(f"source_disabled:{source_id}")

    if documents_ingested == 0:
        warnings.append("no_live_documents_ingested")

    return sorted(set(warnings))


def write_live_verification_artifact(
    *,
    payload: dict[str, Any],
    runs_dir: Path | str = Path("data/runs"),
    timestamp: str | None = None,
) -> Path:
    created_at = timestamp or str(payload.get("generated_at") or utc_now_iso())
    run_id = make_run_id(
        operation="verify_live",
        subject=str(payload["scenario_id"]),
        timestamp=created_at,
        window_days=int(payload["window_days"]),
    )
    output_dir = Path(runs_dir) / "live_verifications"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{run_id}.json"
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output_path


def run_live_verification(
    *,
    bundle: ConfigBundle,
    scenario_id: str,
    window_days: int,
    limit: int = 10,
    raw_dir: Path | str = Path("data/raw"),
    processed_dir: Path | str = Path("data/processed"),
    runs_dir: Path | str = Path("data/runs"),
    baselines_dir: Path | str = Path("data/baselines"),
    config_dir: Path | str = Path("config"),
    replace: bool = False,
) -> dict[str, Any]:
    """Run a live source verification pass and summarize the operator-relevant state.

    The verification artifact is intentionally runtime-oriented and separate from
    stable score and alert JSON. Source failures degrade the verification status
    but do not change scoring rules or invent evidence.
    """

    if limit < 1:
        raise ValueError("limit must be at least 1")

    scenario = bundle.get_scenario(scenario_id)
    generated_at = utc_now_iso()
    source_outcomes: list[dict[str, Any]] = []
    live_documents: list[DocumentRecord] = []

    for source in bundle.sources.sources:
        raw_path = str(Path(raw_dir) / f"{source.id}.jsonl")

        if not source.enabled:
            error = ingestion_error_payload(
                source_id=source.id,
                error_type="source_disabled",
                message=f"Source is disabled: {source.id}",
            )
            source_outcomes.append(
                _source_outcome(
                    source_id=source.id,
                    source_name=source.name,
                    status="disabled",
                    raw_path=raw_path,
                    error=error,
                )
            )
            update_source_health(
                runs_dir=runs_dir,
                source_id=source.id,
                status="error",
                counts={"fetched": 0, "saved": 0, "skipped_existing": 0},
                error=error,
                timestamp=generated_at,
            )
            continue

        try:
            documents = fetch_rss_documents(source, limit=limit)
            if not documents:
                error = ingestion_error_payload(
                    source_id=source.id,
                    error_type="source_empty",
                    message=f"Source returned no usable documents: {source.id}",
                )
                source_outcomes.append(
                    _source_outcome(
                        source_id=source.id,
                        source_name=source.name,
                        status="empty",
                        fetched=0,
                        saved=0,
                        skipped_existing=0,
                        raw_path=raw_path,
                        error=error,
                    )
                )
                update_source_health(
                    runs_dir=runs_dir,
                    source_id=source.id,
                    status="error",
                    counts={"fetched": 0, "saved": 0, "skipped_existing": 0},
                    error=error,
                    timestamp=generated_at,
                )
                continue

            save_result = save_documents_jsonl(
                documents,
                source_id=source.id,
                raw_dir=raw_dir,
                replace=replace,
            )
            live_documents.extend(documents)
            source_outcomes.append(
                _source_outcome(
                    source_id=source.id,
                    source_name=source.name,
                    status="ok",
                    fetched=save_result.fetched,
                    saved=save_result.saved,
                    skipped_existing=save_result.skipped_existing,
                    raw_path=save_result.raw_path,
                )
            )
            update_source_health(
                runs_dir=runs_dir,
                source_id=source.id,
                status="ok",
                counts={
                    "fetched": save_result.fetched,
                    "saved": save_result.saved,
                    "skipped_existing": save_result.skipped_existing,
                },
                timestamp=generated_at,
            )
        except Exception as exc:
            status = categorize_source_exception(exc)
            error = _source_error_payload(source.id, status, exc)
            source_outcomes.append(
                _source_outcome(
                    source_id=source.id,
                    source_name=source.name,
                    status=status,
                    raw_path=raw_path,
                    error=error,
                )
            )
            update_source_health(
                runs_dir=runs_dir,
                source_id=source.id,
                status="error",
                counts={"fetched": 0, "saved": 0, "skipped_existing": 0},
                error=error,
                timestamp=generated_at,
            )

    documents_ingested = len(live_documents)
    documents_classified = 0
    score_generated = False
    alert_generated = False
    score_path: str | None = None
    alert_path: str | None = None
    classified_path: str | None = None
    confidence: str | None = None
    baseline_payload = baseline_show_payload(
        scenario_id=scenario_id,
        baselines_dir=baselines_dir,
    )
    baseline_available = baseline_payload["status"] != "baseline_unavailable"

    if live_documents:
        classified = classify_documents(live_documents, scenario)
        documents_classified = len(classified)
        classified_path = str(
            save_classified_documents_jsonl(
                classified,
                scenario_id=scenario_id,
                processed_dir=processed_dir,
            )
        )
        write_run_snapshot(
            runs_dir=runs_dir,
            operation="classify",
            subject=scenario_id,
            status="ok",
            parameters={"scenario": scenario_id, "source": "verify-live"},
            inputs={"live_verification_documents": documents_ingested},
            outputs={"classified_path": classified_path},
            counts={"documents_read": documents_ingested, "classified": documents_classified},
            config_dir=config_dir,
            timestamp=generated_at,
        )

        score_record = score_documents(
            classified,
            bundle=bundle,
            scenario_id=scenario_id,
            window_days=window_days,
        )
        score_record.baseline_comparison = compare_score_to_baseline(
            score=score_record,
            baselines_dir=baselines_dir,
        )
        score_path = str(save_score_json(score_record, processed_dir=processed_dir))
        confidence = score_record.confidence
        score_generated = True
        write_run_snapshot(
            runs_dir=runs_dir,
            operation="score",
            subject=scenario_id,
            status="ok",
            parameters={"scenario": scenario_id, "window": f"{window_days}d"},
            inputs={"classified_path": classified_path},
            outputs={"score_path": score_path},
            counts={
                "documents_considered": score_record.documents_considered,
                "central_documents": score_record.central_documents,
                "incidental_documents": score_record.incidental_documents,
                "excluded_documents": score_record.excluded_documents,
                "irrelevant_documents": score_record.irrelevant_documents,
            },
            config_dir=config_dir,
            timestamp=generated_at,
            window_days=window_days,
        )

        alert_record = build_alert_record(
            bundle=bundle,
            scenario_id=scenario_id,
            score=score_record,
            classified_documents=classified,
        )
        alert_path = str(save_alert_json(alert_record, processed_dir=processed_dir))
        alert_generated = True
        write_run_snapshot(
            runs_dir=runs_dir,
            operation="alert",
            subject=scenario_id,
            status="ok",
            parameters={"scenario": scenario_id, "window": f"{window_days}d", "json": True},
            inputs={"classified_path": classified_path, "score_path": score_path},
            outputs={"alert_path": alert_path},
            counts={
                "document_count": alert_record.document_count,
                "evidence_count": len(alert_record.evidence),
            },
            config_dir=config_dir,
            timestamp=generated_at,
            window_days=window_days,
        )

    status = _verification_status(source_outcomes, documents_ingested)
    source_counts = _source_counts(source_outcomes)
    warnings = _warnings(source_outcomes, documents_ingested)

    payload: dict[str, Any] = {
        "status": status,
        "operation": "verify_live",
        "scenario_id": scenario.id,
        "scenario_name": scenario.name,
        "generated_at": generated_at,
        "window_days": window_days,
        "limit": limit,
        **source_counts,
        "documents_ingested": documents_ingested,
        "documents_saved": sum(int(item.get("saved", 0)) for item in source_outcomes),
        "documents_classified": documents_classified,
        "score_generated": score_generated,
        "alert_generated": alert_generated,
        "baseline_available": baseline_available,
        "confidence": confidence,
        "source_outcomes": source_outcomes,
        "warnings": warnings,
    }

    outputs: dict[str, Any] = {}
    if classified_path is not None:
        outputs["classified_path"] = classified_path
    if score_path is not None:
        outputs["score_path"] = score_path
    if alert_path is not None:
        outputs["alert_path"] = alert_path

    verification_path = write_live_verification_artifact(
        payload=payload,
        runs_dir=runs_dir,
        timestamp=generated_at,
    )
    payload["verification_path"] = str(verification_path)

    run_path = write_run_snapshot(
        runs_dir=runs_dir,
        operation="verify_live",
        subject=scenario_id,
        status=status,
        parameters={
            "scenario": scenario_id,
            "window": f"{window_days}d",
            "limit": limit,
            "replace": replace,
        },
        inputs={"source_ids": [source.id for source in bundle.sources.sources]},
        outputs={"verification_path": str(verification_path), **outputs},
        counts={
            **source_counts,
            "documents_ingested": documents_ingested,
            "documents_classified": documents_classified,
            "score_generated": score_generated,
            "alert_generated": alert_generated,
        },
        config_dir=config_dir,
        timestamp=generated_at,
        window_days=window_days,
        error={
            "type": "live_verification_not_ok",
            "message": "One or more sources were empty, disabled, or failed.",
            "warnings": warnings,
        }
        if status != "ok"
        else None,
    )
    payload["run_snapshot_path"] = str(run_path)

    # Re-write the artifact with paths included in the operator payload.
    verification_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return payload
