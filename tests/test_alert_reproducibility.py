from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from app.alerts.generator import build_alert_record
from app.models import ClassifiedDocumentRecord, DocumentRecord, load_configs
from app.scoring.convergence import score_documents


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ID = "cbdc_payment_resilience"


def make_hash(label: str) -> str:
    return (label * 64)[:64]


def make_classified(
    *,
    document_id: str,
    relevance: str,
    published_at: str | None,
    classified_at: str,
    source_id: str = "bis",
    source_name: str = "Bank for International Settlements",
    source_category: str = "central_bank_coordination",
    matched_primary_terms: list[str] | None = None,
    matched_secondary_terms: list[str] | None = None,
    total_match_count: int | None = None,
) -> ClassifiedDocumentRecord:
    primary = matched_primary_terms
    secondary = matched_secondary_terms

    if primary is None:
        primary = ["cbdc", "cross-border payments"] if relevance == "central" else []
    if secondary is None:
        secondary = (
            ["settlement infrastructure", "financial market infrastructure"]
            if relevance == "central"
            else []
        )

    if total_match_count is None:
        total_match_count = len(primary) + len(secondary)

    return ClassifiedDocumentRecord(
        document_id=document_id,
        source_id=source_id,
        source_name=source_name,
        source_category=source_category,
        title=f"{document_id} title",
        url=f"https://example.com/{document_id}",
        published_at=published_at,
        summary="CBDC cross-border payments settlement infrastructure.",
        content_hash=make_hash(document_id),
        scenario_id=SCENARIO_ID,
        scenario_name="Cross-border CBDC and payment-system resilience convergence",
        relevance=relevance,  # type: ignore[arg-type]
        matched_primary_terms=primary,
        matched_secondary_terms=secondary,
        matched_exclusion_terms=[],
        total_match_count=total_match_count,
        reason=f"{relevance} fixture",
        classified_at=classified_at,
    )


def build_score_and_alert(
    documents: list[ClassifiedDocumentRecord],
) -> dict:
    bundle = load_configs(PROJECT_ROOT / "config")
    score = score_documents(
        documents,
        bundle=bundle,
        scenario_id=SCENARIO_ID,
        window_days=30,
    )
    alert = build_alert_record(
        bundle=bundle,
        scenario_id=SCENARIO_ID,
        score=score,
        classified_documents=documents,
    )
    return alert.model_dump(mode="json")


def test_generated_at_uses_included_evidence_published_at_not_runtime_or_noise() -> None:
    documents = [
        make_classified(
            document_id="central_old",
            relevance="central",
            published_at="2026-05-10T00:00:00Z",
            classified_at="2026-05-21T01:00:00Z",
        ),
        make_classified(
            document_id="central_new",
            relevance="central",
            published_at="2026-05-12T00:00:00Z",
            classified_at="2026-05-21T01:00:00Z",
        ),
        make_classified(
            document_id="irrelevant_newer",
            relevance="irrelevant",
            published_at="2026-05-20T00:00:00Z",
            classified_at="2026-05-21T01:00:00Z",
            matched_primary_terms=[],
            matched_secondary_terms=[],
            total_match_count=0,
        ),
    ]

    alert = build_score_and_alert(documents)

    assert alert["generated_at"] == "2026-05-12T00:00:00Z"
    assert alert["generated_at"] != "2026-05-21T01:00:00Z"


def test_generated_at_falls_back_to_classified_document_published_at_without_evidence() -> None:
    documents = [
        make_classified(
            document_id="irrelevant_old",
            relevance="irrelevant",
            published_at="2026-05-18T00:00:00Z",
            classified_at="2026-05-21T01:00:00Z",
            matched_primary_terms=[],
            matched_secondary_terms=[],
            total_match_count=0,
        ),
        make_classified(
            document_id="irrelevant_new",
            relevance="irrelevant",
            published_at="2026-05-20T00:00:00Z",
            classified_at="2026-05-21T02:00:00Z",
            matched_primary_terms=[],
            matched_secondary_terms=[],
            total_match_count=0,
        ),
    ]

    alert = build_score_and_alert(documents)

    assert alert["evidence"] == []
    assert alert["generated_at"] == "2026-05-20T00:00:00Z"


def test_generated_at_falls_back_to_epoch_when_no_stable_timestamp_exists() -> None:
    documents = [
        make_classified(
            document_id="undated",
            relevance="irrelevant",
            published_at=None,
            classified_at="2026-05-21T01:00:00Z",
            matched_primary_terms=[],
            matched_secondary_terms=[],
            total_match_count=0,
        )
    ]

    alert = build_score_and_alert(documents)

    assert alert["evidence"] == []
    assert alert["generated_at"] == "1970-01-01T00:00:00Z"


def test_alert_body_is_identical_when_only_classified_at_changes() -> None:
    first_documents = [
        make_classified(
            document_id="central",
            relevance="central",
            published_at="2026-05-19T00:00:00Z",
            classified_at="2026-05-21T01:00:00Z",
        )
    ]
    second_documents = [
        make_classified(
            document_id="central",
            relevance="central",
            published_at="2026-05-19T00:00:00Z",
            classified_at="2026-05-21T02:00:00Z",
        )
    ]

    assert build_score_and_alert(first_documents) == build_score_and_alert(second_documents)


def make_raw_document(*, ingested_at: str) -> DocumentRecord:
    return DocumentRecord(
        document_id="raw_central",
        source_id="bis",
        source_name="Bank for International Settlements",
        source_category="central_bank_coordination",
        title="CBDC work on cross-border payments",
        url="https://example.com/raw_central",
        published_at="2026-05-19T00:00:00Z",
        summary=(
            "Central bank digital currency settlement infrastructure and "
            "financial market infrastructure resilience."
        ),
        content_hash=make_hash("raw_central"),
        ingested_at=ingested_at,
        raw={"title": "CBDC work on cross-border payments"},
    )


def run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "app.cli", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def run_full_alert_pipeline(tmp_path: Path) -> dict:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    runs_dir = tmp_path / "runs"
    raw_dir.mkdir(exist_ok=True)
    processed_dir.mkdir(exist_ok=True)

    raw_path = raw_dir / "bis.jsonl"
    raw_path.write_text(
        json.dumps(make_raw_document(ingested_at="2026-05-19T01:00:00Z").model_dump(mode="json"))
        + "\n",
        encoding="utf-8",
    )

    classify = run_cli(
        [
            "classify",
            "--scenario",
            SCENARIO_ID,
            "--raw-dir",
            str(raw_dir),
            "--processed-dir",
            str(processed_dir),
            "--runs-dir",
            str(runs_dir),
        ]
    )
    assert classify.returncode == 0, classify.stderr

    score = run_cli(
        [
            "score",
            "--scenario",
            SCENARIO_ID,
            "--window",
            "30d",
            "--processed-dir",
            str(processed_dir),
            "--runs-dir",
            str(runs_dir),
        ]
    )
    assert score.returncode == 0, score.stderr

    alert = run_cli(
        [
            "alert",
            "--scenario",
            SCENARIO_ID,
            "--window",
            "30d",
            "--json",
            "--processed-dir",
            str(processed_dir),
            "--runs-dir",
            str(runs_dir),
        ]
    )
    assert alert.returncode == 0, alert.stderr

    alert_path = processed_dir / f"{SCENARIO_ID}_alert.json"
    return json.loads(alert_path.read_text(encoding="utf-8"))


def test_full_cli_alert_json_is_stable_across_repeated_pipeline_runs(tmp_path: Path) -> None:
    first_alert = run_full_alert_pipeline(tmp_path)
    first_classified = (tmp_path / "processed" / f"{SCENARIO_ID}_classified.jsonl").read_text(
        encoding="utf-8"
    )

    time.sleep(1.1)

    second_alert = run_full_alert_pipeline(tmp_path)
    second_classified = (tmp_path / "processed" / f"{SCENARIO_ID}_classified.jsonl").read_text(
        encoding="utf-8"
    )

    assert first_classified != second_classified
    assert first_alert == second_alert
    assert first_alert["generated_at"] == "2026-05-19T00:00:00Z"


def test_golden_alert_fixture_remains_stable() -> None:
    documents = [
        make_classified(
            document_id="central_bis",
            relevance="central",
            published_at="2026-05-19T00:00:00Z",
            classified_at="2026-05-21T01:00:00Z",
        ),
        make_classified(
            document_id="central_imf",
            relevance="central",
            published_at="2026-05-18T00:00:00Z",
            classified_at="2026-05-21T01:00:00Z",
            source_id="imf",
            source_name="International Monetary Fund",
            source_category="international_finance",
        ),
        make_classified(
            document_id="incidental_rba",
            relevance="incidental",
            published_at="2026-05-17T00:00:00Z",
            classified_at="2026-05-21T01:00:00Z",
            source_id="rba",
            source_name="Reserve Bank of Australia",
            source_category="national_central_bank",
            matched_primary_terms=[],
            matched_secondary_terms=["instant payments"],
            total_match_count=1,
        ),
    ]

    expected_path = PROJECT_ROOT / "tests/fixtures/golden_alert_cbdc_payment_resilience.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    assert build_score_and_alert(documents) == expected
