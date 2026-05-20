from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ACCEPTED = "accepted"
ACCEPTED_DEGRADED = "accepted_degraded"
REJECTED = "rejected"

PASS = "pass"
FAIL = "fail"
WARN = "warn"

REQUIRED_SOURCE_COUNT_FIELDS = {
    "ok": "sources_ok",
    "empty": "sources_empty",
    "timeout": "sources_timeout",
    "parse_error": "sources_parse_error",
    "network_error": "sources_network_error",
    "disabled": "sources_disabled",
}

CRITICAL_WARNINGS = {"no_live_documents_ingested"}


def _check(
    *,
    name: str,
    status: str,
    severity: str,
    message: str,
) -> dict[str, str]:
    return {
        "name": name,
        "status": status,
        "severity": severity,
        "message": message,
    }


def _as_int(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def _as_bool(payload: dict[str, Any], field: str) -> bool:
    return payload.get(field) is True


def load_live_verification_payload(verification_path: Path | str) -> dict[str, Any]:
    """Load one verify-live artifact as a JSON object."""

    path = Path(verification_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("live verification artifact must be a JSON object")
    return payload


def _source_count_check(payload: dict[str, Any]) -> dict[str, str]:
    source_outcomes = payload.get("source_outcomes", [])
    if not isinstance(source_outcomes, list):
        return _check(
            name="source_outcomes_shape",
            status=FAIL,
            severity="required",
            message="source_outcomes must be a list.",
        )

    expected_total = _as_int(payload, "sources_total")
    if expected_total != len(source_outcomes):
        return _check(
            name="source_count_consistency",
            status=FAIL,
            severity="required",
            message=(
                "sources_total must equal the number of source_outcomes "
                f"({expected_total} != {len(source_outcomes)})."
            ),
        )

    for outcome_status, count_field in REQUIRED_SOURCE_COUNT_FIELDS.items():
        expected = _as_int(payload, count_field)
        actual = sum(
            1
            for outcome in source_outcomes
            if isinstance(outcome, dict) and outcome.get("status") == outcome_status
        )
        if expected != actual:
            return _check(
                name="source_count_consistency",
                status=FAIL,
                severity="required",
                message=f"{count_field} must equal counted {outcome_status} outcomes.",
            )

    return _check(
        name="source_count_consistency",
        status=PASS,
        severity="required",
        message="Source outcome counts are internally consistent.",
    )


def _required_checks(
    payload: dict[str, Any],
    *,
    require_baseline: bool,
) -> list[dict[str, str]]:
    verification_status = str(payload.get("status", ""))
    warnings = payload.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = []

    checks = [
        _check(
            name="operation_is_verify_live",
            status=PASS if payload.get("operation") == "verify_live" else FAIL,
            severity="required",
            message="Artifact must come from the verify-live command.",
        ),
        _check(
            name="verification_status_usable",
            status=PASS if verification_status in {"ok", "degraded"} else FAIL,
            severity="required",
            message="Verification status must be ok or degraded, not error.",
        ),
        _check(
            name="live_documents_ingested",
            status=PASS if _as_int(payload, "documents_ingested") > 0 else FAIL,
            severity="required",
            message="At least one live document must be ingested.",
        ),
        _check(
            name="live_documents_classified",
            status=PASS if _as_int(payload, "documents_classified") > 0 else FAIL,
            severity="required",
            message="At least one live document must be classified.",
        ),
        _check(
            name="score_generated",
            status=PASS if _as_bool(payload, "score_generated") else FAIL,
            severity="required",
            message="A score must be generated from live evidence.",
        ),
        _check(
            name="alert_generated",
            status=PASS if _as_bool(payload, "alert_generated") else FAIL,
            severity="required",
            message="An alert JSON must be generated from live evidence.",
        ),
        _check(
            name="source_available",
            status=PASS if _as_int(payload, "sources_ok") > 0 else FAIL,
            severity="required",
            message="At least one configured source must return usable documents.",
        ),
        _source_count_check(payload),
        _check(
            name="no_critical_warnings",
            status=FAIL
            if any(str(warning) in CRITICAL_WARNINGS for warning in warnings)
            else PASS,
            severity="required",
            message="Critical live-verification warnings must be absent.",
        ),
    ]

    if require_baseline:
        checks.append(
            _check(
                name="baseline_available",
                status=PASS if _as_bool(payload, "baseline_available") else FAIL,
                severity="required",
                message="A baseline must be available when --require-baseline is used.",
            )
        )

    return checks


def _advisory_checks(payload: dict[str, Any]) -> list[dict[str, str]]:
    verification_status = str(payload.get("status", ""))
    warnings = payload.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = []

    source_error_count = (
        _as_int(payload, "sources_empty")
        + _as_int(payload, "sources_timeout")
        + _as_int(payload, "sources_parse_error")
        + _as_int(payload, "sources_network_error")
        + _as_int(payload, "sources_disabled")
    )

    return [
        _check(
            name="all_sources_ok",
            status=PASS if source_error_count == 0 else WARN,
            severity="advisory",
            message="All configured sources returned ok."
            if source_error_count == 0
            else "One or more sources were empty, disabled, or failed.",
        ),
        _check(
            name="verification_not_degraded",
            status=PASS if verification_status == "ok" else WARN,
            severity="advisory",
            message="Verification status is ok."
            if verification_status == "ok"
            else (
                "Verification status is degraded; operator review is required."
                if verification_status == "degraded"
                else "Verification status is not ok; required checks decide rejection."
            ),
        ),
        _check(
            name="baseline_available",
            status=PASS if _as_bool(payload, "baseline_available") else WARN,
            severity="advisory",
            message="Baseline is available."
            if _as_bool(payload, "baseline_available")
            else "Baseline is unavailable; accept only with explicit operator note.",
        ),
        _check(
            name="warnings_empty",
            status=PASS if not warnings else WARN,
            severity="advisory",
            message="No verification warnings are present."
            if not warnings
            else "Verification warnings are present and require operator review.",
        ),
    ]


def evaluate_live_acceptance(
    payload: dict[str, Any],
    *,
    verification_path: Path | str,
    require_baseline: bool = False,
) -> dict[str, Any]:
    """Evaluate a verify-live artifact against the operator acceptance gate.

    The acceptance gate is read-only. It never fetches sources, generates scores,
    writes alerts, updates baselines, or mutates source-health state.
    """

    required_checks = _required_checks(payload, require_baseline=require_baseline)
    advisory_checks = _advisory_checks(payload)
    checks = required_checks + advisory_checks

    failed_required = [
        check for check in required_checks if check["status"] == FAIL
    ]
    advisory_warnings = [
        check for check in advisory_checks if check["status"] == WARN
    ]

    if failed_required:
        decision = REJECTED
    elif advisory_warnings:
        decision = ACCEPTED_DEGRADED
    else:
        decision = ACCEPTED

    operator_actions: list[str] = []
    if decision == REJECTED:
        operator_actions.append("Do not use this run for go-live acceptance.")
        operator_actions.append("Open an incident note and rerun after resolving required failures.")
    elif decision == ACCEPTED_DEGRADED:
        operator_actions.append("Record an operator note explaining degraded acceptance.")
        operator_actions.append("Review source warnings before archiving the run.")
    else:
        operator_actions.append("Archive the verification artifact as accepted evidence.")

    payload_warnings = payload.get("warnings", [])
    if not isinstance(payload_warnings, list):
        payload_warnings = ["warnings_field_invalid"]

    return {
        "status": "ok" if decision != REJECTED else "error",
        "operation": "accept_live",
        "decision": decision,
        "verification_path": str(verification_path),
        "scenario_id": payload.get("scenario_id"),
        "window_days": payload.get("window_days"),
        "verification_status": payload.get("status"),
        "generated_at": payload.get("generated_at"),
        "documents_ingested": payload.get("documents_ingested", 0),
        "documents_classified": payload.get("documents_classified", 0),
        "score_generated": payload.get("score_generated", False),
        "alert_generated": payload.get("alert_generated", False),
        "baseline_available": payload.get("baseline_available", False),
        "sources_total": payload.get("sources_total", 0),
        "sources_ok": payload.get("sources_ok", 0),
        "source_failure_count": (
            _as_int(payload, "sources_empty")
            + _as_int(payload, "sources_timeout")
            + _as_int(payload, "sources_parse_error")
            + _as_int(payload, "sources_network_error")
            + _as_int(payload, "sources_disabled")
        ),
        "warnings": sorted(str(warning) for warning in payload_warnings),
        "checks": checks,
        "operator_actions": operator_actions,
    }
