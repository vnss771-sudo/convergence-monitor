from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from app.cli import app


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = PROJECT_ROOT / "docs" / "examples"
SCENARIO_ID = "cbdc_payment_resilience"
runner = CliRunner()


def _write_verification(
    runs_dir: Path,
    example_name: str,
    filename: str,
    generated_at: str,
    edits: dict[str, object] | None = None,
) -> Path:
    payload = json.loads((EXAMPLES_DIR / example_name).read_text(encoding="utf-8"))
    payload["generated_at"] = generated_at

    verification_dir = runs_dir / "live_verifications"
    verification_dir.mkdir(parents=True, exist_ok=True)
    path = verification_dir / filename
    payload["verification_path"] = str(path)

    if edits:
        payload.update(edits)

    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_review_pack(runs_dir: Path, verification_path: Path) -> dict[str, object]:
    result = runner.invoke(
        app,
        [
            "review-live",
            "--verification",
            str(verification_path),
            "--output-dir",
            str(runs_dir / "live_reviews"),
        ],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_live_history_summarizes_recent_reviewed_live_runs(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    error_path = _write_verification(
        runs_dir,
        "verification_error.json",
        "verify_live_error.json",
        "2026-05-19T00:00:00Z",
    )
    degraded_path = _write_verification(
        runs_dir,
        "verification_degraded.json",
        "verify_live_degraded.json",
        "2026-05-20T00:00:00Z",
    )
    accepted_path = _write_verification(
        runs_dir,
        "verification_accepted.json",
        "verify_live_accepted.json",
        "2026-05-21T00:00:00Z",
    )

    assert error_path.exists()
    _write_review_pack(runs_dir, degraded_path)
    _write_review_pack(runs_dir, accepted_path)

    result = runner.invoke(
        app,
        [
            "live-history",
            "--scenario",
            SCENARIO_ID,
            "--runs-dir",
            str(runs_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["operation"] == "live_history"
    assert payload["status"] == "ok"
    assert payload["scenario_id"] == SCENARIO_ID
    assert payload["runs_available"] == 3
    assert payload["runs_considered"] == 3
    assert payload["review_packs_found"] == 2
    assert payload["usable_run_count"] == 2
    assert payload["rejected_run_count"] == 1
    assert payload["unreviewed_usable_run_count"] == 0
    assert payload["current_usable_streak"] == 2
    assert payload["decision_counts"] == {
        "accepted": 1,
        "accepted_degraded": 1,
        "rejected": 1,
    }
    assert payload["verification_status_counts"] == {
        "ok": 1,
        "degraded": 1,
        "error": 1,
    }
    assert payload["latest"]["decision"] == "accepted"
    assert payload["latest"]["generated_at"] == "2026-05-21T00:00:00Z"
    assert payload["latest"]["review_pack_exists"] is True
    assert payload["warnings"] == []


def test_live_history_flags_unreviewed_usable_runs(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _write_verification(
        runs_dir,
        "verification_accepted.json",
        "verify_live_accepted.json",
        "2026-05-21T00:00:00Z",
    )

    result = runner.invoke(
        app,
        [
            "live-history",
            "--scenario",
            SCENARIO_ID,
            "--runs-dir",
            str(runs_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "attention"
    assert payload["usable_run_count"] == 1
    assert payload["unreviewed_usable_run_count"] == 1
    assert "unreviewed_usable_live_runs:1" in payload["warnings"]
    assert payload["latest"]["review_pack_exists"] is False


def test_live_history_reports_empty_state_without_artifacts(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "live-history",
            "--scenario",
            SCENARIO_ID,
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "empty"
    assert payload["runs_available"] == 0
    assert payload["runs_considered"] == 0
    assert payload["latest"] is None
    assert payload["runs"] == []
    assert f"no_live_verification_artifacts:{SCENARIO_ID}" in payload["warnings"]


def test_live_history_can_apply_required_baseline_gate(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    accepted_without_baseline = _write_verification(
        runs_dir,
        "verification_accepted.json",
        "verify_live_no_baseline.json",
        "2026-05-21T00:00:00Z",
        edits={"baseline_available": False},
    )
    _write_review_pack(runs_dir, accepted_without_baseline)

    result = runner.invoke(
        app,
        [
            "live-history",
            "--scenario",
            SCENARIO_ID,
            "--runs-dir",
            str(runs_dir),
            "--require-baseline",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["require_baseline"] is True
    assert payload["status"] == "attention"
    assert payload["decision_counts"]["rejected"] == 1
    assert payload["latest"]["decision"] == "rejected"
    assert payload["latest"]["baseline_available"] is False
    assert "latest_live_run_rejected" in payload["warnings"]


def test_live_history_respects_limit_and_scenario_filter(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _write_verification(
        runs_dir,
        "verification_accepted.json",
        "verify_live_other_scenario.json",
        "2026-05-22T00:00:00Z",
        edits={"scenario_id": "other_scenario"},
    )
    _write_verification(
        runs_dir,
        "verification_accepted.json",
        "verify_live_accepted_newest.json",
        "2026-05-21T00:00:00Z",
    )
    _write_verification(
        runs_dir,
        "verification_degraded.json",
        "verify_live_degraded_oldest.json",
        "2026-05-20T00:00:00Z",
    )

    result = runner.invoke(
        app,
        [
            "live-history",
            "--scenario",
            SCENARIO_ID,
            "--runs-dir",
            str(runs_dir),
            "--limit",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["runs_available"] == 2
    assert payload["runs_considered"] == 1
    assert len(payload["runs"]) == 1
    assert payload["latest"]["verification_path"].endswith("verify_live_accepted_newest.json")
