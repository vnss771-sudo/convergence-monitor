from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from app.cli import app
from app.models import ClassifiedDocumentRecord, load_configs
from app.scoring.baselines import (
    add_baseline_observation,
    baseline_show_payload,
    compare_score_to_baseline,
)
from app.scoring.convergence import score_documents


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
        matched_secondary_terms=["instant payments"] if relevance == "incidental" else [],
        matched_exclusion_terms=[],
        total_match_count=2 if relevance == "central" else 1,
        reason=f"{relevance} fixture",
        classified_at="2026-05-19T01:00:00Z",
    )


def make_score(documents: list[ClassifiedDocumentRecord]):
    bundle = load_configs(PROJECT_ROOT / "config")
    return score_documents(
        documents,
        bundle=bundle,
        scenario_id=SCENARIO_ID,
        window_days=30,
    )


def write_classified(processed_dir: Path, documents: list[ClassifiedDocumentRecord]) -> None:
    processed_dir.mkdir(parents=True, exist_ok=True)
    path = processed_dir / f"{SCENARIO_ID}_classified.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for document in documents:
            handle.write(json.dumps(document.model_dump(mode="json"), sort_keys=True) + "\n")


def test_missing_baseline_comparison_is_explicit(tmp_path: Path) -> None:
    score = make_score([])

    comparison = compare_score_to_baseline(score=score, baselines_dir=tmp_path)

    assert comparison.status == "baseline_unavailable"
    assert comparison.scenario_id == SCENARIO_ID
    assert comparison.baseline_observation_count == 0
    assert comparison.comparison == "not_enough_history"


def test_available_baseline_comparison_is_descriptive_only(tmp_path: Path) -> None:
    baseline_score = make_score([])
    current_score = make_score([make_classified(document_id="doc1")])

    add_baseline_observation(score=baseline_score, baselines_dir=tmp_path)
    comparison = compare_score_to_baseline(score=current_score, baselines_dir=tmp_path)

    assert comparison.status == "baseline_available"
    assert comparison.baseline_observation_count == 1
    assert comparison.comparison == "above_baseline"
    assert comparison.current_score == current_score.convergence_score
    assert current_score.convergence_score > baseline_score.convergence_score


def test_duplicate_baseline_observation_is_suppressed(tmp_path: Path) -> None:
    score = make_score([make_classified(document_id="doc1")])

    first_store, first_record, first_created, _ = add_baseline_observation(
        score=score,
        baselines_dir=tmp_path,
    )
    second_store, second_record, second_created, _ = add_baseline_observation(
        score=score,
        baselines_dir=tmp_path,
    )

    assert first_created is True
    assert second_created is False
    assert first_record.observation_id == second_record.observation_id
    assert len(first_store.observations) == 1
    assert len(second_store.observations) == 1


def test_baseline_show_cli_reports_unavailable(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "baselines",
            "show",
            "--scenario",
            SCENARIO_ID,
            "--baselines-dir",
            str(tmp_path / "baselines"),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "baseline_unavailable"
    assert payload["baseline_observation_count"] == 0


def test_baseline_update_cli_writes_human_readable_json(tmp_path: Path) -> None:
    baselines_dir = tmp_path / "baselines"
    processed_dir = tmp_path / "processed"

    result = runner.invoke(
        app,
        [
            "baselines",
            "update",
            "--scenario",
            SCENARIO_ID,
            "--processed-dir",
            str(processed_dir),
            "--baselines-dir",
            str(baselines_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["observation_created"] is True
    baseline_path = Path(payload["baseline_path"])
    assert baseline_path.exists()

    stored = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert stored["status"] == "baseline_available"
    assert stored["scenario_id"] == SCENARIO_ID
    assert len(stored["observations"]) == 1
    assert "\n  " in baseline_path.read_text(encoding="utf-8")


def test_score_cli_integrates_baseline_and_update_suppression(tmp_path: Path) -> None:
    processed_dir = tmp_path / "processed"
    baselines_dir = tmp_path / "baselines"
    runs_dir = tmp_path / "runs"
    write_classified(processed_dir, [make_classified(document_id="doc1")])

    first = runner.invoke(
        app,
        [
            "score",
            "--scenario",
            SCENARIO_ID,
            "--window",
            "30d",
            "--processed-dir",
            str(processed_dir),
            "--baselines-dir",
            str(baselines_dir),
            "--runs-dir",
            str(runs_dir),
            "--update-baseline",
        ],
    )
    assert first.exit_code == 0, first.output
    first_payload = json.loads(first.stdout)
    assert first_payload["baseline_comparison"]["status"] == "baseline_unavailable"
    assert first_payload["baseline_update"]["observation_created"] is True

    second = runner.invoke(
        app,
        [
            "score",
            "--scenario",
            SCENARIO_ID,
            "--window",
            "30d",
            "--processed-dir",
            str(processed_dir),
            "--baselines-dir",
            str(baselines_dir),
            "--runs-dir",
            str(runs_dir),
            "--update-baseline",
        ],
    )
    assert second.exit_code == 0, second.output
    second_payload = json.loads(second.stdout)
    assert second_payload["baseline_comparison"]["status"] == "baseline_available"
    assert second_payload["baseline_update"]["duplicate_suppressed"] is True

    show_payload = baseline_show_payload(
        scenario_id=SCENARIO_ID,
        baselines_dir=baselines_dir,
    )
    assert show_payload["baseline_observation_count"] == 1
