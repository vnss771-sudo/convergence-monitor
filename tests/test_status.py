from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from app.alerts.generator import build_alert_record, save_alert_json
from app.cli import app
from app.ingestion.failures import update_source_health
from app.models import ClassifiedDocumentRecord, load_configs
from app.runs.snapshots import write_run_snapshot
from app.scoring.baselines import add_baseline_observation, compare_score_to_baseline
from app.scoring.convergence import save_score_json, score_documents


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ID = "cbdc_payment_resilience"
runner = CliRunner()


def make_hash(label: str) -> str:
    return (label * 64)[:64]


def make_classified(
    *,
    document_id: str,
    source_id: str = "bis",
    source_name: str = "Bank for International Settlements",
    source_category: str = "central_bank_coordination",
    relevance: str = "central",
    content_hash: str | None = None,
) -> ClassifiedDocumentRecord:
    return ClassifiedDocumentRecord(
        document_id=document_id,
        source_id=source_id,
        source_name=source_name,
        source_category=source_category,
        title=f"{document_id} title",
        url=f"https://example.com/{document_id}",
        published_at="2026-05-19T00:00:00Z",
        summary="CBDC cross-border payments settlement infrastructure.",
        content_hash=content_hash or make_hash(document_id),
        scenario_id=SCENARIO_ID,
        scenario_name="Cross-border CBDC and payment-system resilience convergence",
        relevance=relevance,  # type: ignore[arg-type]
        matched_primary_terms=["cbdc", "cross-border payments"] if relevance == "central" else [],
        matched_secondary_terms=[],
        matched_exclusion_terms=[],
        total_match_count=2 if relevance == "central" else 0,
        reason=f"{relevance} fixture",
        classified_at="2026-05-19T01:00:00Z",
    )


def test_status_cli_reports_complete_scenario_state(tmp_path: Path) -> None:
    processed_dir = tmp_path / "processed"
    runs_dir = tmp_path / "runs"
    baselines_dir = tmp_path / "baselines"
    bundle = load_configs(PROJECT_ROOT / "config")
    documents = [
        make_classified(document_id="doc1"),
        make_classified(
            document_id="doc2",
            source_id="imf",
            source_name="International Monetary Fund",
            source_category="international_finance",
        ),
    ]

    score = score_documents(
        documents,
        bundle=bundle,
        scenario_id=SCENARIO_ID,
        window_days=30,
    )
    add_baseline_observation(score=score, baselines_dir=baselines_dir)
    score.baseline_comparison = compare_score_to_baseline(
        score=score,
        baselines_dir=baselines_dir,
    ).model_dump(mode="json")
    save_score_json(score, processed_dir=processed_dir)

    alert = build_alert_record(
        bundle=bundle,
        scenario_id=SCENARIO_ID,
        score=score,
        classified_documents=documents,
    )
    save_alert_json(alert, processed_dir=processed_dir)

    for source in bundle.enabled_sources:
        update_source_health(
            runs_dir=runs_dir,
            source_id=source.id,
            status="error" if source.id == "imf" else "ok",
            counts={"saved": 1},
            error={
                "source_id": source.id,
                "type": "fixture_error",
                "message": "fixture degraded source",
            }
            if source.id == "imf"
            else None,
            timestamp="2026-05-19T00:00:00Z",
        )

    write_run_snapshot(
        runs_dir=runs_dir,
        operation="ingest",
        subject="all",
        status="ok",
        config_dir=PROJECT_ROOT / "config",
        timestamp="2026-05-19T00:00:00Z",
    )
    for operation in ("classify", "score", "alert"):
        write_run_snapshot(
            runs_dir=runs_dir,
            operation=operation,
            subject=SCENARIO_ID,
            status="ok",
            config_dir=PROJECT_ROOT / "config",
            timestamp=f"2026-05-19T00:0{len(operation)}:00Z",
            window_days=30 if operation in {"score", "alert"} else None,
        )

    result = runner.invoke(
        app,
        [
            "status",
            "--scenario",
            SCENARIO_ID,
            "--window",
            "30d",
            "--processed-dir",
            str(processed_dir),
            "--runs-dir",
            str(runs_dir),
            "--baselines-dir",
            str(baselines_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["scenario_id"] == SCENARIO_ID
    assert payload["scenario_name"] == (
        "Cross-border CBDC and payment-system resilience convergence"
    )
    assert payload["window_days"] == 30
    assert payload["score"] == {
        "exists": True,
        "convergence_score": score.convergence_score,
        "confidence": score.confidence,
        "active_source_categories": score.active_source_categories,
        "documents_considered": score.documents_considered,
    }
    assert payload["alert"] == {
        "exists": True,
        "generated_at": "2026-05-19T00:00:00Z",
        "evidence_count": len(alert.evidence),
    }
    assert payload["baseline"] == {
        "status": "baseline_available",
        "observation_count": 1,
        "comparison": "near_baseline",
    }
    assert payload["source_health"]["sources_total"] == 5
    assert payload["source_health"]["sources_ok"] == 4
    assert payload["source_health"]["sources_error"] == 1
    assert payload["source_health"]["overall"] == "degraded"
    assert payload["latest_runs"] == {
        "ingest": "ok",
        "classify": "ok",
        "score": "ok",
        "alert": "ok",
    }
    assert payload["warnings"] == []


def test_status_cli_reports_missing_artifacts_without_failing(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "status",
            "--scenario",
            SCENARIO_ID,
            "--window",
            "30d",
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
    assert payload["status"] == "ok"
    assert payload["score"]["exists"] is False
    assert payload["alert"]["exists"] is False
    assert payload["baseline"] == {
        "status": "baseline_unavailable",
        "observation_count": 0,
        "comparison": "not_enough_history",
    }
    assert payload["source_health"] == {
        "sources_total": 5,
        "sources_ok": 0,
        "sources_error": 0,
        "sources_unknown": 5,
        "overall": "unknown",
    }
    assert payload["latest_runs"] == {
        "ingest": "missing",
        "classify": "missing",
        "score": "missing",
        "alert": "missing",
    }
    assert set(payload["warnings"]) == {
        "score_json_missing",
        "alert_json_missing",
        "baseline_unavailable",
        "ingest_run_missing",
        "classify_run_missing",
        "score_run_missing",
        "alert_run_missing",
    }


def test_status_cli_rejects_unknown_scenario(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "status",
            "--scenario",
            "unknown_scenario",
            "--processed-dir",
            str(tmp_path / "processed"),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--baselines-dir",
            str(tmp_path / "baselines"),
        ],
    )

    assert result.exit_code == 1
    assert "Unknown scenario_id" in result.output
