from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from app.cli import app


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = PROJECT_ROOT / "docs" / "examples"
runner = CliRunner()


def _write_payload(tmp_path: Path, filename: str, edits: dict[str, object] | None = None) -> Path:
    payload = json.loads((EXAMPLES_DIR / filename).read_text(encoding="utf-8"))
    if edits:
        payload.update(edits)
    path = tmp_path / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_accept_live_accepts_clean_verification_artifact() -> None:
    result = runner.invoke(
        app,
        [
            "accept-live",
            "--verification",
            str(EXAMPLES_DIR / "verification_accepted.json"),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["operation"] == "accept_live"
    assert payload["decision"] == "accepted"
    assert payload["status"] == "ok"
    assert payload["verification_status"] == "ok"
    assert payload["documents_ingested"] > 0
    assert payload["score_generated"] is True
    assert payload["alert_generated"] is True
    assert payload["source_failure_count"] == 0
    assert all(check["status"] == "pass" for check in payload["checks"])


def test_accept_live_accepts_degraded_artifact_with_operator_actions() -> None:
    result = runner.invoke(
        app,
        [
            "accept-live",
            "--verification",
            str(EXAMPLES_DIR / "verification_degraded.json"),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["decision"] == "accepted_degraded"
    assert payload["status"] == "ok"
    assert payload["verification_status"] == "degraded"
    assert payload["source_failure_count"] == 1
    assert "source_network_error:bis" in payload["warnings"]
    assert any(check["status"] == "warn" for check in payload["checks"])
    assert any("operator note" in action for action in payload["operator_actions"])


def test_accept_live_rejects_error_artifact() -> None:
    result = runner.invoke(
        app,
        [
            "accept-live",
            "--verification",
            str(EXAMPLES_DIR / "verification_error.json"),
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["decision"] == "rejected"
    assert payload["status"] == "error"
    failed_required = [
        check
        for check in payload["checks"]
        if check["severity"] == "required" and check["status"] == "fail"
    ]
    assert {check["name"] for check in failed_required} >= {
        "verification_status_usable",
        "live_documents_ingested",
        "live_documents_classified",
        "score_generated",
        "alert_generated",
        "source_available",
        "no_critical_warnings",
    }


def test_accept_live_can_require_baseline(tmp_path: Path) -> None:
    path = _write_payload(
        tmp_path,
        "verification_accepted.json",
        edits={"baseline_available": False},
    )

    without_requirement = runner.invoke(
        app,
        [
            "accept-live",
            "--verification",
            str(path),
        ],
    )
    assert without_requirement.exit_code == 0
    degraded_payload = json.loads(without_requirement.stdout)
    assert degraded_payload["decision"] == "accepted_degraded"

    with_requirement = runner.invoke(
        app,
        [
            "accept-live",
            "--verification",
            str(path),
            "--require-baseline",
        ],
    )
    assert with_requirement.exit_code == 1
    rejected_payload = json.loads(with_requirement.stdout)
    assert rejected_payload["decision"] == "rejected"
    assert any(
        check["name"] == "baseline_available"
        and check["severity"] == "required"
        and check["status"] == "fail"
        for check in rejected_payload["checks"]
    )


def test_accept_live_rejects_inconsistent_source_counts(tmp_path: Path) -> None:
    path = _write_payload(
        tmp_path,
        "verification_accepted.json",
        edits={"sources_ok": 4},
    )

    result = runner.invoke(
        app,
        [
            "accept-live",
            "--verification",
            str(path),
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["decision"] == "rejected"
    assert any(
        check["name"] == "source_count_consistency"
        and check["severity"] == "required"
        and check["status"] == "fail"
        for check in payload["checks"]
    )
