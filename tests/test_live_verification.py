from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from app.cli import app
from app.ingestion.rss_base import IngestionError, normalize_entry
from app.models import Source


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ID = "cbdc_payment_resilience"
runner = CliRunner()


def fixture_document(source: Source, *, published: str = "2026-05-19"):
    return normalize_entry(
        {
            "title": f"{source.id} CBDC cross-border payments settlement infrastructure",
            "link": f"https://example.com/{source.id}/cbdc-live",
            "published": published,
            "summary": (
                "CBDC, cross-border payments, settlement infrastructure, and "
                "payment system resilience."
            ),
        },
        source,
        "2026-05-19T00:00:00Z",
    )


def test_verify_live_reports_degraded_source_outcomes_and_generates_outputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    runs_dir = tmp_path / "runs"

    def mixed_fetch(source: Source, limit: int = 10):
        if source.id == "bis":
            return [fixture_document(source)]
        if source.id == "imf":
            return []
        if source.id == "rba":
            raise IngestionError("fixture timeout while fetching RBA")
        if source.id == "federal_reserve":
            raise IngestionError("Failed to parse RSS feed 'federal_reserve'")
        raise IngestionError("Failed to fetch RSS source 'ecb': connection failed")

    monkeypatch.setattr("app.live_verification.fetch_rss_documents", mixed_fetch)

    result = runner.invoke(
        app,
        [
            "verify-live",
            "--scenario",
            SCENARIO_ID,
            "--window",
            "30d",
            "--limit",
            "3",
            "--raw-dir",
            str(raw_dir),
            "--processed-dir",
            str(processed_dir),
            "--runs-dir",
            str(runs_dir),
            "--baselines-dir",
            str(tmp_path / "baselines"),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "degraded"
    assert payload["operation"] == "verify_live"
    assert payload["scenario_id"] == SCENARIO_ID
    assert payload["window_days"] == 30
    assert payload["sources_total"] == 5
    assert payload["sources_ok"] == 1
    assert payload["sources_empty"] == 1
    assert payload["sources_timeout"] == 1
    assert payload["sources_parse_error"] == 1
    assert payload["sources_network_error"] == 1
    assert payload["documents_ingested"] == 1
    assert payload["documents_classified"] == 1
    assert payload["score_generated"] is True
    assert payload["alert_generated"] is True
    assert payload["baseline_available"] is False
    assert payload["confidence"] in {"low", "medium", "high"}
    assert set(payload["warnings"]) == {
        "source_empty:imf",
        "source_timeout:rba",
        "source_parse_error:federal_reserve",
        "source_network_error:ecb",
    }

    source_statuses = {
        item["source_id"]: item["status"] for item in payload["source_outcomes"]
    }
    assert source_statuses == {
        "bis": "ok",
        "imf": "empty",
        "rba": "timeout",
        "federal_reserve": "parse_error",
        "ecb": "network_error",
    }

    assert Path(payload["verification_path"]).exists()
    assert Path(payload["run_snapshot_path"]).exists()
    assert (processed_dir / f"{SCENARIO_ID}_classified.jsonl").exists()
    assert (processed_dir / f"{SCENARIO_ID}_score.json").exists()
    assert (processed_dir / f"{SCENARIO_ID}_alert.json").exists()

    health_path = runs_dir / "source_health" / "source_health.json"
    health = json.loads(health_path.read_text(encoding="utf-8"))
    assert health["sources"]["bis"]["status"] == "ok"
    assert health["sources"]["imf"]["status"] == "error"
    assert health["sources"]["rba"]["error"]["type"] == "source_timeout"
    assert health["sources"]["federal_reserve"]["error"]["type"] == "source_parse_error"
    assert health["sources"]["ecb"]["error"]["type"] == "source_network_error"

    verification_artifact = json.loads(
        Path(payload["verification_path"]).read_text(encoding="utf-8")
    )
    assert verification_artifact == payload


def test_verify_live_all_sources_fail_exits_nonzero_without_stable_outputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def failing_fetch(source: Source, limit: int = 10):
        raise IngestionError(f"Failed to fetch RSS source '{source.id}'")

    monkeypatch.setattr("app.live_verification.fetch_rss_documents", failing_fetch)

    processed_dir = tmp_path / "processed"
    result = runner.invoke(
        app,
        [
            "verify-live",
            "--scenario",
            SCENARIO_ID,
            "--raw-dir",
            str(tmp_path / "raw"),
            "--processed-dir",
            str(processed_dir),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--baselines-dir",
            str(tmp_path / "baselines"),
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["documents_ingested"] == 0
    assert payload["documents_classified"] == 0
    assert payload["score_generated"] is False
    assert payload["alert_generated"] is False
    assert "no_live_documents_ingested" in payload["warnings"]
    assert not (processed_dir / f"{SCENARIO_ID}_score.json").exists()
    assert not (processed_dir / f"{SCENARIO_ID}_alert.json").exists()
    assert Path(payload["verification_path"]).exists()
    assert Path(payload["run_snapshot_path"]).exists()


def test_verify_live_handles_disabled_sources_without_fetching(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "scenarios.yaml").write_text(
        (PROJECT_ROOT / "config" / "scenarios.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (config_dir / "sources.yaml").write_text(
        """
sources:
  - id: enabled_fixture
    name: Enabled Fixture
    category: central_bank_coordination
    type: rss
    enabled: true
    trust_weight: 1.0
    url: https://example.com/enabled.xml
  - id: disabled_fixture
    name: Disabled Fixture
    category: central_bank_coordination
    type: rss
    enabled: false
    trust_weight: 1.0
    url: https://example.com/disabled.xml
""".lstrip(),
        encoding="utf-8",
    )

    fetched_source_ids: list[str] = []

    def fake_fetch(source: Source, limit: int = 10):
        fetched_source_ids.append(source.id)
        return [fixture_document(source)]

    monkeypatch.setattr("app.live_verification.fetch_rss_documents", fake_fetch)

    result = runner.invoke(
        app,
        [
            "verify-live",
            "--scenario",
            SCENARIO_ID,
            "--config-dir",
            str(config_dir),
            "--raw-dir",
            str(tmp_path / "raw"),
            "--processed-dir",
            str(tmp_path / "processed"),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--baselines-dir",
            str(tmp_path / "baselines"),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "degraded"
    assert payload["sources_total"] == 2
    assert payload["sources_ok"] == 1
    assert payload["sources_disabled"] == 1
    assert "source_disabled:disabled_fixture" in payload["warnings"]
    assert fetched_source_ids == ["enabled_fixture"]

    source_statuses = {
        item["source_id"]: item["status"] for item in payload["source_outcomes"]
    }
    assert source_statuses == {
        "enabled_fixture": "ok",
        "disabled_fixture": "disabled",
    }


def test_verify_live_preserves_stable_alert_across_runtime_classification_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_fetch(source: Source, limit: int = 10):
        if source.id != "bis":
            return []
        return [fixture_document(source, published="2026-05-19")]

    timestamps = iter(["2026-05-19T01:00:00Z", "2026-05-19T02:00:00Z"])

    monkeypatch.setattr("app.live_verification.fetch_rss_documents", fake_fetch)
    monkeypatch.setattr(
        "app.classification.keyword_matcher.utc_now_iso",
        lambda: next(timestamps),
    )

    common_args = [
        "verify-live",
        "--scenario",
        SCENARIO_ID,
        "--window",
        "30d",
        "--raw-dir",
        str(tmp_path / "raw"),
        "--processed-dir",
        str(tmp_path / "processed"),
        "--runs-dir",
        str(tmp_path / "runs"),
        "--baselines-dir",
        str(tmp_path / "baselines"),
    ]

    first = runner.invoke(app, common_args)
    assert first.exit_code == 0, first.output
    first_alert = (tmp_path / "processed" / f"{SCENARIO_ID}_alert.json").read_text(
        encoding="utf-8"
    )
    first_classified = (
        tmp_path / "processed" / f"{SCENARIO_ID}_classified.jsonl"
    ).read_text(encoding="utf-8")

    second = runner.invoke(app, common_args)
    assert second.exit_code == 0, second.output
    second_alert = (tmp_path / "processed" / f"{SCENARIO_ID}_alert.json").read_text(
        encoding="utf-8"
    )
    second_classified = (
        tmp_path / "processed" / f"{SCENARIO_ID}_classified.jsonl"
    ).read_text(encoding="utf-8")

    assert first_alert == second_alert
    assert first_classified != second_classified
    assert json.loads(first_alert)["generated_at"] == "2026-05-19T00:00:00Z"
