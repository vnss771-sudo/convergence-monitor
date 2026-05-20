from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.models import ClassifiedDocumentRecord, load_configs
from app.scoring.convergence import (
    confidence_for_score,
    parse_window_days,
    save_score_json,
    score_documents,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def make_hash(label: str) -> str:
    return (label * 64)[:64]


def make_classified(
    *,
    document_id: str,
    source_id: str,
    source_name: str,
    source_category: str,
    relevance: str,
    content_hash: str,
    published_at: str = "2026-05-19T00:00:00Z",
) -> ClassifiedDocumentRecord:
    return ClassifiedDocumentRecord(
        document_id=document_id,
        source_id=source_id,
        source_name=source_name,
        source_category=source_category,
        title=f"{document_id} title",
        url=f"https://example.com/{document_id}",
        published_at=published_at,
        summary="CBDC cross-border payments settlement infrastructure.",
        content_hash=content_hash,
        scenario_id="cbdc_payment_resilience",
        scenario_name="Cross-border CBDC and payment-system resilience convergence",
        relevance=relevance,  # type: ignore[arg-type]
        matched_primary_terms=["cbdc", "cross-border payments"] if relevance == "central" else [],
        matched_secondary_terms=["instant payments"] if relevance == "incidental" else [],
        matched_exclusion_terms=["bitcoin trading"] if relevance == "excluded" else [],
        total_match_count=2 if relevance == "central" else 1,
        reason=f"{relevance} fixture",
        classified_at="2026-05-19T01:00:00Z",
    )


def test_clamp_score_bounds_values() -> None:
    from app.scoring.convergence import clamp_score

    assert clamp_score(-1) == 0.0
    assert clamp_score(5.5) == 5.5
    assert clamp_score(11) == 10.0


def test_parse_window_days_accepts_day_window_only() -> None:
    assert parse_window_days("30d") == 30
    assert parse_window_days("7D") == 7

    with pytest.raises(ValueError):
        parse_window_days("one month")


def test_confidence_bands_are_stable() -> None:
    assert confidence_for_score(2.9) == "low"
    assert confidence_for_score(3.0) == "medium"
    assert confidence_for_score(6.9) == "medium"
    assert confidence_for_score(7.0) == "high"


def test_score_documents_is_explainable_and_deduplicates_content_hashes() -> None:
    bundle = load_configs(PROJECT_ROOT / "config")
    documents = [
        make_classified(
            document_id="doc1",
            source_id="bis",
            source_name="Bank for International Settlements",
            source_category="central_bank_coordination",
            relevance="central",
            content_hash=make_hash("a"),
            published_at="2026-05-19T00:00:00Z",
        ),
        make_classified(
            document_id="doc2",
            source_id="imf",
            source_name="International Monetary Fund",
            source_category="international_finance",
            relevance="central",
            content_hash=make_hash("b"),
            published_at="2026-05-18T00:00:00Z",
        ),
        make_classified(
            document_id="doc3",
            source_id="rba",
            source_name="Reserve Bank of Australia",
            source_category="national_central_bank",
            relevance="incidental",
            content_hash=make_hash("c"),
            published_at="2026-05-11T00:00:00Z",
        ),
        make_classified(
            document_id="doc4",
            source_id="ecb",
            source_name="European Central Bank",
            source_category="national_central_bank",
            relevance="central",
            content_hash=make_hash("b"),
            published_at="2026-05-18T00:00:00Z",
        ),
        make_classified(
            document_id="doc5",
            source_id="federal_reserve",
            source_name="Federal Reserve",
            source_category="national_central_bank",
            relevance="excluded",
            content_hash=make_hash("d"),
        ),
        make_classified(
            document_id="doc6",
            source_id="bis",
            source_name="Bank for International Settlements",
            source_category="central_bank_coordination",
            relevance="irrelevant",
            content_hash=make_hash("e"),
        ),
    ]

    score = score_documents(
        documents,
        bundle=bundle,
        scenario_id="cbdc_payment_resilience",
        window_days=30,
    )

    assert score.status == "ok"
    assert score.documents_considered == 6
    assert score.central_documents == 3
    assert score.incidental_documents == 1
    assert score.excluded_documents == 1
    assert score.irrelevant_documents == 1
    assert score.active_source_categories == 3
    assert score.score_components.source_diversity_score == 2.0
    assert score.score_components.duplication_penalty == 0.5
    assert score.convergence_score == 5.4
    assert score.confidence == "medium"
    assert score.limitations == [
        "Baseline model is provisional.",
        "Scoring is deterministic and rule-based.",
        "This does not infer intent, coordination, or future events.",
    ]


def test_score_json_output_shape_is_stable(tmp_path: Path) -> None:
    bundle = load_configs(PROJECT_ROOT / "config")
    score = score_documents(
        [
            make_classified(
                document_id="doc1",
                source_id="bis",
                source_name="Bank for International Settlements",
                source_category="central_bank_coordination",
                relevance="central",
                content_hash=make_hash("a"),
            )
        ],
        bundle=bundle,
        scenario_id="cbdc_payment_resilience",
        window_days=30,
    )

    output_path = save_score_json(score, processed_dir=tmp_path)

    assert output_path == tmp_path / "cbdc_payment_resilience_score.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert set(payload) == {
        "status",
        "scenario_id",
        "window_days",
        "documents_considered",
        "central_documents",
        "incidental_documents",
        "excluded_documents",
        "irrelevant_documents",
        "active_source_categories",
        "convergence_score",
        "confidence",
        "score_components",
        "baseline_comparison",
        "limitations",
    }
    assert set(payload["score_components"]) == {
        "central_document_score",
        "source_diversity_score",
        "trust_weight_score",
        "recency_score",
        "duplication_penalty",
    }
    assert payload["baseline_comparison"]["status"] == "baseline_unavailable"


def test_score_cli_reads_classified_jsonl_and_writes_score_json(tmp_path: Path) -> None:
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    classified_path = processed_dir / "cbdc_payment_resilience_classified.jsonl"

    documents = [
        make_classified(
            document_id="doc1",
            source_id="bis",
            source_name="Bank for International Settlements",
            source_category="central_bank_coordination",
            relevance="central",
            content_hash=make_hash("a"),
        ),
        make_classified(
            document_id="doc2",
            source_id="imf",
            source_name="International Monetary Fund",
            source_category="international_finance",
            relevance="incidental",
            content_hash=make_hash("b"),
        ),
    ]
    with classified_path.open("w", encoding="utf-8") as handle:
        for document in documents:
            handle.write(json.dumps(document.model_dump(mode="json"), sort_keys=True) + "\n")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.cli",
            "score",
            "--scenario",
            "cbdc_payment_resilience",
            "--window",
            "30d",
            "--processed-dir",
            str(processed_dir),
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["scenario_id"] == "cbdc_payment_resilience"
    assert payload["window_days"] == 30
    assert (processed_dir / "cbdc_payment_resilience_score.json").exists()
