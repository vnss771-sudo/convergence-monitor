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


def test_review_live_writes_deterministic_accepted_pack(tmp_path: Path) -> None:
    output_dir = tmp_path / "reviews"

    first = runner.invoke(
        app,
        [
            "review-live",
            "--verification",
            str(EXAMPLES_DIR / "verification_accepted.json"),
            "--output-dir",
            str(output_dir),
        ],
    )
    second = runner.invoke(
        app,
        [
            "review-live",
            "--verification",
            str(EXAMPLES_DIR / "verification_accepted.json"),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    first_payload = json.loads(first.stdout)
    second_payload = json.loads(second.stdout)
    assert first_payload == second_payload
    assert first_payload["operation"] == "live_review_pack"
    assert first_payload["decision"] == "accepted"
    assert first_payload["status"] == "ok"
    assert first_payload["generated_at"] == "2026-05-19T00:00:00Z"
    assert first_payload["acceptance"]["decision"] == "accepted"
    assert first_payload["summary"]["scenario_id"] == "cbdc_payment_resilience"
    assert first_payload["source_summary"]["sources_ok"] == 5
    assert first_payload["source_summary"]["groups"]["ok"]
    assert first_payload["artifact_paths"]["verification_path"].endswith(
        "verification_accepted.json"
    )
    assert first_payload["archive_recommendation"]["action"] == "archive_as_accepted"

    review_pack_path = Path(first_payload["review_pack_path"])
    assert review_pack_path.exists()
    assert json.loads(review_pack_path.read_text(encoding="utf-8")) == first_payload


def test_review_live_summarizes_degraded_source_groups(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "review-live",
            "--verification",
            str(EXAMPLES_DIR / "verification_degraded.json"),
            "--output-dir",
            str(tmp_path / "reviews"),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["decision"] == "accepted_degraded"
    assert payload["status"] == "ok"
    assert payload["acceptance"]["decision"] == "accepted_degraded"
    assert payload["source_summary"]["sources_network_error"] == 1
    assert payload["source_summary"]["groups"]["network_error"][0]["source_id"] == "bis"
    assert "source_network_error:bis" in payload["warnings"]
    assert payload["archive_recommendation"]["action"] == "archive_with_operator_note"
    assert any("degraded run" in question for question in payload["operator_questions"])


def test_review_live_writes_rejected_pack_for_incident_evidence(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "review-live",
            "--verification",
            str(EXAMPLES_DIR / "verification_error.json"),
            "--output-dir",
            str(tmp_path / "reviews"),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["decision"] == "rejected"
    assert payload["status"] == "error"
    assert payload["acceptance"]["status"] == "error"
    assert payload["source_summary"]["sources_network_error"] == 5
    assert payload["archive_recommendation"]["action"] == "archive_as_rejected_incident"
    assert any("incident note" in question for question in payload["operator_questions"])
    assert Path(payload["review_pack_path"]).exists()


def test_review_live_can_apply_required_baseline_gate(tmp_path: Path) -> None:
    verification_path = _write_payload(
        tmp_path,
        "verification_accepted.json",
        edits={"baseline_available": False},
    )

    result = runner.invoke(
        app,
        [
            "review-live",
            "--verification",
            str(verification_path),
            "--output-dir",
            str(tmp_path / "reviews"),
            "--require-baseline",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["decision"] == "rejected"
    assert payload["require_baseline"] is True
    assert payload["summary"]["baseline_available"] is False
    assert any(
        check["name"] == "baseline_available"
        and check["severity"] == "required"
        and check["status"] == "fail"
        for check in payload["acceptance"]["checks"]
    )
