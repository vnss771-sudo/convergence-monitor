from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJECT_ROOT / "docs"
EXAMPLES_DIR = DOCS_DIR / "examples"


def test_operator_docs_exist_and_define_required_commands() -> None:
    required_docs = [
        DOCS_DIR / "OPERATOR_RUNBOOK.md",
        DOCS_DIR / "LIVE_ACCEPTANCE_CHECKLIST.md",
        DOCS_DIR / "INCIDENT_RESPONSE.md",
    ]

    for path in required_docs:
        assert path.exists(), f"Missing operator document: {path.name}"

    combined = "\n".join(path.read_text(encoding="utf-8") for path in required_docs)

    for command in [
        "python -m app.cli validate-config",
        "pytest -q",
        "python -m compileall -q app tests",
        "python -m app.cli status --scenario cbdc_payment_resilience --window 30d",
        "python -m app.cli verify-live --scenario cbdc_payment_resilience --window 30d",
        "python -m app.cli accept-live --verification",
        "python -m app.cli review-live --verification",
        "python -m app.cli live-history --scenario cbdc_payment_resilience",
    ]:
        assert command in combined

    for decision_state in ["accepted", "accepted_degraded", "rejected"]:
        assert decision_state in combined

    assert "no false certainty" in combined
    assert "dashboard" in combined
    assert "predictions" in combined


def test_live_acceptance_checklist_contains_merge_and_go_live_gates() -> None:
    checklist = (DOCS_DIR / "LIVE_ACCEPTANCE_CHECKLIST.md").read_text(encoding="utf-8")

    assert "Merge criteria for PRs" in checklist
    assert "Go-live criteria for the technical MVP" in checklist
    assert "Stable alert JSON is identical across reruns" in checklist
    assert "Source availability is not treated as evidence" in checklist
    assert "Machine-readable acceptance gate" in checklist
    assert "python -m app.cli accept-live --verification" in checklist
    assert "python -m app.cli review-live --verification" in checklist
    assert "Live review pack" in checklist
    assert "Live history gate" in checklist
    assert "python -m app.cli live-history --scenario cbdc_payment_resilience" in checklist


def test_example_live_verification_outputs_are_valid_and_consistent() -> None:
    examples = {
        "verification_accepted.json": "ok",
        "verification_degraded.json": "degraded",
        "verification_error.json": "error",
    }

    for filename, expected_status in examples.items():
        path = EXAMPLES_DIR / filename
        assert path.exists(), f"Missing example output: {filename}"
        payload = json.loads(path.read_text(encoding="utf-8"))

        assert payload["operation"] == "verify_live"
        assert payload["status"] == expected_status
        assert payload["scenario_id"] == "cbdc_payment_resilience"
        assert payload["sources_total"] == len(payload["source_outcomes"])
        assert "verification_path" in payload
        assert "run_snapshot_path" in payload

        counted_statuses = {
            "ok": payload["sources_ok"],
            "empty": payload["sources_empty"],
            "timeout": payload["sources_timeout"],
            "parse_error": payload["sources_parse_error"],
            "network_error": payload["sources_network_error"],
            "disabled": payload["sources_disabled"],
        }
        for status, expected_count in counted_statuses.items():
            actual_count = sum(
                1 for outcome in payload["source_outcomes"] if outcome["status"] == status
            )
            assert actual_count == expected_count

    error_payload = json.loads(
        (EXAMPLES_DIR / "verification_error.json").read_text(encoding="utf-8")
    )
    assert error_payload["documents_ingested"] == 0
    assert error_payload["score_generated"] is False
    assert error_payload["alert_generated"] is False
    assert "no_live_documents_ingested" in error_payload["warnings"]

    degraded_payload = json.loads(
        (EXAMPLES_DIR / "verification_degraded.json").read_text(encoding="utf-8")
    )
    assert degraded_payload["documents_ingested"] > 0
    assert degraded_payload["score_generated"] is True
    assert degraded_payload["alert_generated"] is True
    assert degraded_payload["warnings"]
