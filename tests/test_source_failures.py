from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from app.cli import app
from app.ingestion.rss_base import IngestionError, normalize_entry
from app.models import Source


PROJECT_ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def fixture_document(source: Source):
    return normalize_entry(
        {
            "title": f"{source.id} CBDC settlement infrastructure",
            "link": f"https://example.com/{source.id}/cbdc",
            "published": "2026-05-19",
            "summary": "Cross-border payments and central bank digital currency.",
        },
        source,
        "2026-05-19T00:00:00Z",
    )


def test_single_source_failure_returns_structured_json_and_health(
    tmp_path: Path,
    monkeypatch,
) -> None:
    raw_dir = tmp_path / "raw"
    runs_dir = tmp_path / "runs"

    def failing_fetch(_source: Source, limit: int = 10, timeout_seconds: float = 20.0):
        raise IngestionError("fixture network failure")

    monkeypatch.setattr("app.commands.ingest.fetch_rss_documents", failing_fetch)

    result = runner.invoke(
        app,
        [
            "ingest",
            "--source",
            "bis",
            "--limit",
            "10",
            "--raw-dir",
            str(raw_dir),
            "--runs-dir",
            str(runs_dir),
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["operation"] == "ingest"
    assert payload["source_id"] == "bis"
    assert payload["error"]["type"] == "ingestion_error"
    assert "fixture network failure" in payload["error"]["message"]
    assert payload["saved"] == 0

    snapshots = list(runs_dir.glob("*.json"))
    assert len(snapshots) == 1
    snapshot = json.loads(snapshots[0].read_text(encoding="utf-8"))
    assert snapshot["status"] == "error"
    assert snapshot["operation"] == "ingest"
    assert snapshot["error"]["type"] == "ingestion_error"

    health_path = runs_dir / "source_health" / "source_health.json"
    health = json.loads(health_path.read_text(encoding="utf-8"))
    assert health["sources"]["bis"]["status"] == "error"
    assert health["sources"]["bis"]["error"]["type"] == "ingestion_error"


def test_multi_source_ingest_reports_degraded_status(tmp_path: Path, monkeypatch) -> None:
    raw_dir = tmp_path / "raw"
    runs_dir = tmp_path / "runs"

    def mixed_fetch(source: Source, limit: int = 10, timeout_seconds: float = 20.0):
        if source.id == "imf":
            raise IngestionError("fixture IMF failure")
        return [fixture_document(source)]

    monkeypatch.setattr("app.commands.ingest.fetch_rss_documents", mixed_fetch)

    result = runner.invoke(
        app,
        [
            "ingest",
            "--source",
            "all",
            "--limit",
            "1",
            "--raw-dir",
            str(raw_dir),
            "--runs-dir",
            str(runs_dir),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "degraded"
    assert payload["operation"] == "ingest"
    assert payload["sources_attempted"] == 5
    assert payload["sources_succeeded"] == 4
    assert payload["sources_failed"] == 1
    assert payload["saved"] == 4
    assert [failure["source_id"] for failure in payload["failures"]] == ["imf"]

    snapshots = [json.loads(path.read_text(encoding="utf-8")) for path in runs_dir.glob("*.json")]
    global_snapshots = [item for item in snapshots if item["subject"] == "all"]
    assert len(global_snapshots) == 1
    assert global_snapshots[0]["status"] == "degraded"
    assert global_snapshots[0]["counts"]["sources_failed"] == 1

    health_result = runner.invoke(
        app,
        ["runs", "health", "--runs-dir", str(runs_dir)],
    )
    assert health_result.exit_code == 0
    health_payload = json.loads(health_result.stdout)
    assert health_payload["status"] == "ok"
    assert health_payload["sources"]["imf"]["status"] == "error"
    assert health_payload["sources"]["bis"]["status"] == "ok"
    assert health_payload["summary"]["overall"] == "degraded"
    assert health_payload["summary"]["failure_types"] == {"ingestion_error": 1}
    assert health_payload["summary"]["failed_sources"][0]["source_id"] == "imf"
    assert health_payload["summary"]["failed_sources"][0]["error_type"] == "ingestion_error"


def test_unknown_source_failure_is_structured_json(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "ingest",
            "--source",
            "broken_fixture",
            "--limit",
            "10",
            "--runs-dir",
            str(runs_dir),
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["operation"] == "ingest"
    assert payload["source_id"] == "broken_fixture"
    assert payload["error"]["type"] == "unknown_source"

    snapshots = list(runs_dir.glob("*.json"))
    assert len(snapshots) == 1
    snapshot = json.loads(snapshots[0].read_text(encoding="utf-8"))
    assert snapshot["status"] == "error"
    assert snapshot["subject"] == "broken_fixture"


def test_disabled_source_failure_writes_snapshot_and_health(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    (config_dir / "scenarios.yaml").write_text(
        (PROJECT_ROOT / "config" / "scenarios.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (config_dir / "sources.yaml").write_text(
        """
sources:
  - id: disabled_bis
    name: Disabled BIS
    category: central_bank_coordination
    type: rss
    enabled: false
    trust_weight: 1.0
    url: https://www.bis.org/rss/bispublications.xml
""".lstrip(),
        encoding="utf-8",
    )

    runs_dir = tmp_path / "runs"
    raw_dir = tmp_path / "raw"

    result = runner.invoke(
        app,
        [
            "ingest",
            "--source",
            "disabled_bis",
            "--limit",
            "10",
            "--config-dir",
            str(config_dir),
            "--raw-dir",
            str(raw_dir),
            "--runs-dir",
            str(runs_dir),
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error"]["type"] == "source_disabled"
    assert payload["run_snapshot_path"]

    snapshot = json.loads(Path(payload["run_snapshot_path"]).read_text(encoding="utf-8"))
    assert snapshot["status"] == "error"
    assert snapshot["error"]["type"] == "source_disabled"

    health_path = runs_dir / "source_health" / "source_health.json"
    health = json.loads(health_path.read_text(encoding="utf-8"))
    assert health["sources"]["disabled_bis"]["status"] == "error"
    assert health["sources"]["disabled_bis"]["error"]["type"] == "source_disabled"
