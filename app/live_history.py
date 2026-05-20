from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.live_acceptance import evaluate_live_acceptance


SOURCE_ERROR_FIELDS = (
    "sources_empty",
    "sources_timeout",
    "sources_parse_error",
    "sources_network_error",
    "sources_disabled",
)

DECISION_VALUES = ("accepted", "accepted_degraded", "rejected")
VERIFICATION_STATUS_VALUES = ("ok", "degraded", "error")


def _as_int(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def _as_bool(payload: dict[str, Any], field: str) -> bool:
    return payload.get(field) is True


def _load_json_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    return payload if isinstance(payload, dict) else None


def _iter_json_files(path: Path) -> list[Path]:
    if not path.exists() or not path.is_dir():
        return []
    return sorted(item for item in path.glob("*.json") if item.is_file())


def _scenario_matches(payload: dict[str, Any], scenario_id: str | None) -> bool:
    if scenario_id is None:
        return True
    return payload.get("scenario_id") == scenario_id


def _source_failure_count(payload: dict[str, Any]) -> int:
    return sum(_as_int(payload, field) for field in SOURCE_ERROR_FIELDS)


def _verification_sort_key(item: dict[str, Any]) -> tuple[str, str]:
    return (
        str(item.get("generated_at") or ""),
        str(item.get("_path") or ""),
    )


def _review_key_candidates(path: Path | str) -> set[str]:
    path_string = str(path)
    path_obj = Path(path_string)
    return {
        path_string,
        path_obj.name,
        path_obj.stem,
        str(path_obj.as_posix()),
    }


def _review_index(review_dir: Path, scenario_id: str | None) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}

    for path in _iter_json_files(review_dir):
        payload = _load_json_file(path)
        if payload is None or payload.get("operation") != "live_review_pack":
            continue

        summary = payload.get("summary", {})
        if not isinstance(summary, dict):
            summary = {}

        if scenario_id is not None and summary.get("scenario_id") != scenario_id:
            continue

        artifact_paths = payload.get("artifact_paths", {})
        if not isinstance(artifact_paths, dict):
            artifact_paths = {}

        verification_path = artifact_paths.get("verification_path")
        if not isinstance(verification_path, str):
            continue

        review_payload = {
            "review_pack_path": str(path),
            "review_decision": payload.get("decision"),
            "review_status": payload.get("status"),
            "archive_recommendation": payload.get("archive_recommendation"),
        }

        for key in _review_key_candidates(verification_path):
            index[key] = review_payload

    return index


def _matching_review(
    review_index: dict[str, dict[str, Any]],
    verification_path: Path,
) -> dict[str, Any] | None:
    for key in _review_key_candidates(verification_path):
        if key in review_index:
            return review_index[key]
    return None


def _run_summary(
    *,
    verification_payload: dict[str, Any],
    verification_path: Path,
    review_payload: dict[str, Any] | None,
    require_baseline: bool,
) -> dict[str, Any]:
    acceptance = evaluate_live_acceptance(
        verification_payload,
        verification_path=verification_path,
        require_baseline=require_baseline,
    )
    decision = str(acceptance["decision"])
    warning_values = verification_payload.get("warnings", [])
    if not isinstance(warning_values, list):
        warning_values = ["warnings_field_invalid"]

    return {
        "verification_path": str(verification_path),
        "generated_at": verification_payload.get("generated_at"),
        "scenario_id": verification_payload.get("scenario_id"),
        "verification_status": verification_payload.get("status"),
        "decision": decision,
        "review_pack_exists": review_payload is not None,
        "review_pack_path": review_payload.get("review_pack_path") if review_payload else None,
        "review_decision": review_payload.get("review_decision") if review_payload else None,
        "documents_ingested": _as_int(verification_payload, "documents_ingested"),
        "documents_classified": _as_int(verification_payload, "documents_classified"),
        "score_generated": _as_bool(verification_payload, "score_generated"),
        "alert_generated": _as_bool(verification_payload, "alert_generated"),
        "baseline_available": _as_bool(verification_payload, "baseline_available"),
        "confidence": verification_payload.get("confidence"),
        "sources_total": _as_int(verification_payload, "sources_total"),
        "sources_ok": _as_int(verification_payload, "sources_ok"),
        "source_failure_count": _source_failure_count(verification_payload),
        "warnings": sorted(str(warning) for warning in warning_values),
    }


def _current_usable_streak(runs: list[dict[str, Any]]) -> int:
    streak = 0
    for run in runs:
        if run["decision"] in {"accepted", "accepted_degraded"}:
            streak += 1
        else:
            break
    return streak


def _history_status(
    *,
    runs: list[dict[str, Any]],
    unreviewed_usable_run_count: int,
) -> str:
    if not runs:
        return "empty"

    latest = runs[0]
    if latest["decision"] == "rejected":
        return "attention"
    if unreviewed_usable_run_count:
        return "attention"
    return "ok"


def _history_warnings(
    *,
    scenario_id: str | None,
    runs: list[dict[str, Any]],
    unreviewed_usable_run_count: int,
) -> list[str]:
    warnings: list[str] = []

    if not runs:
        scenario_suffix = f":{scenario_id}" if scenario_id else ""
        return [f"no_live_verification_artifacts{scenario_suffix}"]

    latest = runs[0]
    if latest["decision"] == "rejected":
        warnings.append("latest_live_run_rejected")

    if unreviewed_usable_run_count:
        warnings.append(f"unreviewed_usable_live_runs:{unreviewed_usable_run_count}")

    if not any(run["decision"] in {"accepted", "accepted_degraded"} for run in runs):
        warnings.append("no_accepted_or_degraded_live_runs")

    return sorted(warnings)


def build_live_history(
    *,
    scenario_id: str | None = None,
    runs_dir: Path | str = Path("data/runs"),
    limit: int = 10,
    require_baseline: bool = False,
) -> dict[str, Any]:
    """Summarize recent verify-live artifacts and review-pack coverage.

    This is a read-only operational history view. It does not fetch sources, write
    verification artifacts, update baselines, or generate score/alert output.
    """

    if limit < 1:
        raise ValueError("limit must be at least 1")

    runs_path = Path(runs_dir)
    verification_dir = runs_path / "live_verifications"
    review_dir = runs_path / "live_reviews"
    reviews = _review_index(review_dir, scenario_id)

    verification_payloads: list[dict[str, Any]] = []
    invalid_artifacts: list[str] = []

    for path in _iter_json_files(verification_dir):
        payload = _load_json_file(path)
        if payload is None:
            invalid_artifacts.append(str(path))
            continue
        if payload.get("operation") != "verify_live":
            continue
        if not _scenario_matches(payload, scenario_id):
            continue
        payload["_path"] = str(path)
        verification_payloads.append(payload)

    verification_payloads.sort(key=_verification_sort_key, reverse=True)
    selected_payloads = verification_payloads[:limit]

    runs = [
        _run_summary(
            verification_payload=payload,
            verification_path=Path(str(payload["_path"])),
            review_payload=_matching_review(reviews, Path(str(payload["_path"]))),
            require_baseline=require_baseline,
        )
        for payload in selected_payloads
    ]

    decision_counter = Counter(run["decision"] for run in runs)
    status_counter = Counter(run["verification_status"] for run in runs)

    decision_counts = {decision: decision_counter.get(decision, 0) for decision in DECISION_VALUES}
    verification_status_counts = {
        status: status_counter.get(status, 0) for status in VERIFICATION_STATUS_VALUES
    }

    usable_run_count = decision_counts["accepted"] + decision_counts["accepted_degraded"]
    rejected_run_count = decision_counts["rejected"]
    review_packs_found = sum(1 for run in runs if run["review_pack_exists"])
    unreviewed_usable_run_count = sum(
        1
        for run in runs
        if run["decision"] in {"accepted", "accepted_degraded"}
        and not run["review_pack_exists"]
    )

    latest = runs[0] if runs else None
    warnings = _history_warnings(
        scenario_id=scenario_id,
        runs=runs,
        unreviewed_usable_run_count=unreviewed_usable_run_count,
    )
    warnings.extend(f"invalid_live_verification_artifact:{path}" for path in invalid_artifacts)

    return {
        "status": _history_status(
            runs=runs,
            unreviewed_usable_run_count=unreviewed_usable_run_count,
        ),
        "operation": "live_history",
        "scenario_id": scenario_id or "all",
        "limit": limit,
        "require_baseline": require_baseline,
        "runs_dir": str(runs_path),
        "verification_dir": str(verification_dir),
        "review_dir": str(review_dir),
        "runs_available": len(verification_payloads),
        "runs_considered": len(runs),
        "review_packs_found": review_packs_found,
        "usable_run_count": usable_run_count,
        "rejected_run_count": rejected_run_count,
        "unreviewed_usable_run_count": unreviewed_usable_run_count,
        "current_usable_streak": _current_usable_streak(runs),
        "decision_counts": decision_counts,
        "verification_status_counts": verification_status_counts,
        "latest": latest,
        "runs": runs,
        "warnings": sorted(set(warnings)),
    }
