from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.live_acceptance import evaluate_live_acceptance, load_live_verification_payload
from app.persistence import write_json_atomic
from app.runs.snapshots import make_run_id


SOURCE_STATUSES = (
    "ok",
    "empty",
    "timeout",
    "parse_error",
    "network_error",
    "disabled",
)


def _as_int(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def _as_bool(payload: dict[str, Any], field: str) -> bool:
    return payload.get(field) is True


def _load_run_snapshot(path_value: object) -> dict[str, Any] | None:
    if not isinstance(path_value, str) or not path_value:
        return None

    path = Path(path_value)
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    return payload if isinstance(payload, dict) else None


def _group_source_outcomes(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    outcomes = payload.get("source_outcomes", [])
    groups: dict[str, list[dict[str, Any]]] = {status: [] for status in SOURCE_STATUSES}
    if not isinstance(outcomes, list):
        return groups

    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        status = str(outcome.get("status", ""))
        if status in groups:
            groups[status].append(outcome)

    return groups


def _artifact_paths(
    *,
    verification_payload: dict[str, Any],
    verification_path: Path | str,
) -> dict[str, Any]:
    source_outcomes = verification_payload.get("source_outcomes", [])
    raw_paths: dict[str, str] = {}
    if isinstance(source_outcomes, list):
        for outcome in source_outcomes:
            if not isinstance(outcome, dict):
                continue
            source_id = outcome.get("source_id")
            raw_path = outcome.get("raw_path")
            if isinstance(source_id, str) and isinstance(raw_path, str):
                raw_paths[source_id] = raw_path

    run_snapshot = _load_run_snapshot(verification_payload.get("run_snapshot_path"))
    run_outputs = {}
    if run_snapshot is not None and isinstance(run_snapshot.get("outputs"), dict):
        run_outputs = dict(run_snapshot["outputs"])

    return {
        "verification_path": str(verification_path),
        "run_snapshot_path": verification_payload.get("run_snapshot_path"),
        "raw_paths": raw_paths,
        "classified_path": run_outputs.get("classified_path"),
        "score_path": run_outputs.get("score_path"),
        "alert_path": run_outputs.get("alert_path"),
    }


def _operator_questions(decision: str, payload: dict[str, Any]) -> list[str]:
    questions = [
        "Does the accepted evidence directly support the scenario, not just keyword overlap?",
        "Are source failures isolated and explained rather than hidden?",
        "Does the alert remain conservative relative to the evidence count and confidence?",
    ]

    if decision == "accepted_degraded":
        questions.append("Is there a written reason for accepting this degraded run?")
    if decision == "rejected":
        questions.append("Has an incident note been opened before any go-live decision?")
    if not _as_bool(payload, "baseline_available"):
        questions.append("Is baseline_unavailable acceptable for this review context?")

    return questions


def _archive_recommendation(decision: str) -> dict[str, str]:
    if decision == "accepted":
        return {
            "action": "archive_as_accepted",
            "message": "Archive this review pack as accepted live-verification evidence.",
        }
    if decision == "accepted_degraded":
        return {
            "action": "archive_with_operator_note",
            "message": "Archive only with an operator note explaining degraded acceptance.",
        }
    return {
        "action": "archive_as_rejected_incident",
        "message": "Do not use this run for go-live acceptance; attach the pack to an incident note.",
    }


def build_live_review_pack(
    verification_payload: dict[str, Any],
    *,
    verification_path: Path | str,
    require_baseline: bool = False,
) -> dict[str, Any]:
    """Build a deterministic operator review pack for one verify-live artifact.

    The review pack is read-only. It evaluates the same gate as accept-live, groups
    source outcomes, and records the artifact paths an operator should inspect.
    It does not fetch sources, generate scores, write alerts, or update baselines.
    """

    acceptance = evaluate_live_acceptance(
        verification_payload,
        verification_path=verification_path,
        require_baseline=require_baseline,
    )
    decision = str(acceptance["decision"])
    source_groups = _group_source_outcomes(verification_payload)

    summary = {
        "verification_status": verification_payload.get("status"),
        "scenario_id": verification_payload.get("scenario_id"),
        "scenario_name": verification_payload.get("scenario_name"),
        "window_days": verification_payload.get("window_days"),
        "generated_at": verification_payload.get("generated_at"),
        "documents_ingested": _as_int(verification_payload, "documents_ingested"),
        "documents_classified": _as_int(verification_payload, "documents_classified"),
        "score_generated": _as_bool(verification_payload, "score_generated"),
        "alert_generated": _as_bool(verification_payload, "alert_generated"),
        "baseline_available": _as_bool(verification_payload, "baseline_available"),
        "confidence": verification_payload.get("confidence"),
    }

    source_summary = {
        "sources_total": _as_int(verification_payload, "sources_total"),
        "sources_ok": _as_int(verification_payload, "sources_ok"),
        "sources_empty": _as_int(verification_payload, "sources_empty"),
        "sources_timeout": _as_int(verification_payload, "sources_timeout"),
        "sources_parse_error": _as_int(verification_payload, "sources_parse_error"),
        "sources_network_error": _as_int(verification_payload, "sources_network_error"),
        "sources_disabled": _as_int(verification_payload, "sources_disabled"),
        "groups": source_groups,
    }

    warnings = verification_payload.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = ["warnings_field_invalid"]

    return {
        "status": "ok" if decision != "rejected" else "error",
        "operation": "live_review_pack",
        "decision": decision,
        "generated_at": verification_payload.get("generated_at"),
        "require_baseline": require_baseline,
        "summary": summary,
        "source_summary": source_summary,
        "acceptance": acceptance,
        "artifact_paths": _artifact_paths(
            verification_payload=verification_payload,
            verification_path=verification_path,
        ),
        "warnings": sorted(str(warning) for warning in warnings),
        "operator_questions": _operator_questions(decision, verification_payload),
        "archive_recommendation": _archive_recommendation(decision),
    }


def write_live_review_pack(
    review_pack: dict[str, Any],
    *,
    output_dir: Path | str = Path("data/runs/live_reviews"),
) -> Path:
    """Write one deterministic review-pack artifact."""

    summary = review_pack.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    scenario_id = str(summary.get("scenario_id") or "unknown_scenario")
    window_days = int(summary.get("window_days") or 0)
    generated_at = str(review_pack.get("generated_at") or "1970-01-01T00:00:00Z")
    run_id = make_run_id(
        operation="live_review",
        subject=scenario_id,
        timestamp=generated_at,
        window_days=window_days if window_days > 0 else None,
    )

    output_path = Path(output_dir) / f"{run_id}.json"
    write_json_atomic(output_path, review_pack)
    return output_path


def build_and_write_live_review_pack(
    *,
    verification_path: Path | str,
    output_dir: Path | str = Path("data/runs/live_reviews"),
    require_baseline: bool = False,
) -> dict[str, Any]:
    """Load, evaluate, write, and return a live review pack."""

    verification_payload = load_live_verification_payload(verification_path)
    review_pack = build_live_review_pack(
        verification_payload,
        verification_path=verification_path,
        require_baseline=require_baseline,
    )
    review_pack_path = write_live_review_pack(review_pack, output_dir=output_dir)
    review_pack["review_pack_path"] = str(review_pack_path)

    # Re-write with its own path included so the printed payload and artifact match.
    write_json_atomic(review_pack_path, review_pack)
    return review_pack
