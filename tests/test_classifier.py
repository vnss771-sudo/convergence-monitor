from __future__ import annotations

import json
from pathlib import Path

from app.classification.keyword_matcher import (
    classify_document,
    classify_documents,
    load_raw_documents,
    match_terms,
    save_classified_documents_jsonl,
)
from app.ingestion.rss_base import make_content_hash
from app.models import DocumentRecord, Scenario, load_configs


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def scenario() -> Scenario:
    return load_configs(PROJECT_ROOT / "config").get_scenario("cbdc_payment_resilience")


def make_document(
    *,
    title: str,
    summary: str,
    document_id: str = "doc1",
    source_id: str = "bis",
) -> DocumentRecord:
    content_hash = make_content_hash(
        source_id=source_id,
        title=title,
        url=f"https://example.com/{document_id}",
        published_at="2026-05-19T00:00:00Z",
        summary=summary,
    )
    return DocumentRecord(
        document_id=document_id,
        source_id=source_id,
        source_name="Bank for International Settlements",
        source_category="central_bank_coordination",
        title=title,
        url=f"https://example.com/{document_id}",
        published_at="2026-05-19T00:00:00Z",
        summary=summary,
        content_hash=content_hash,
        ingested_at="2026-05-19T01:00:00Z",
        raw={"title": title},
    )


def test_term_matching_is_case_insensitive_and_deterministic() -> None:
    text = "CBDC research on Cross-Border Payments and settlement infrastructure."
    terms = ["cbdc", "cross-border payments", "settlement infrastructure"]

    assert match_terms(text, terms) == [
        "cbdc",
        "cross-border payments",
        "settlement infrastructure",
    ]


def test_term_matching_ignores_absent_terms() -> None:
    text = "This document is about general financial stability."
    terms = ["cbdc", "programmable money"]

    assert match_terms(text, terms) == []


def test_classifier_marks_central_document() -> None:
    document = make_document(
        title="CBDC work on cross-border payments",
        summary=(
            "Central bank digital currency settlement infrastructure and "
            "financial market infrastructure resilience."
        ),
    )

    classified = classify_document(
        document,
        scenario(),
        classified_at="2026-05-19T02:00:00Z",
    )

    assert classified.relevance == "central"
    assert classified.matched_primary_terms == [
        "cbdc",
        "central bank digital currency",
        "cross-border payments",
        "financial market infrastructure",
        "settlement infrastructure",
    ]
    assert classified.matched_secondary_terms == []
    assert classified.matched_exclusion_terms == []
    assert "central to the document" in classified.reason


def test_classifier_marks_incidental_document() -> None:
    document = make_document(
        title="General payments speech",
        summary="The speech briefly mentions instant payments and correspondent banking.",
    )

    classified = classify_document(document, scenario(), classified_at="2026-05-19T02:00:00Z")

    assert classified.relevance == "incidental"
    assert classified.matched_primary_terms == []
    assert classified.matched_secondary_terms == ["correspondent banking", "instant payments"]
    assert classified.total_match_count == 2
    assert "below the central relevance threshold" in classified.reason


def test_classifier_marks_excluded_document_even_with_matches() -> None:
    document = make_document(
        title="CBDC and cryptocurrency price commentary",
        summary="A bitcoin trading note mentions cross-border payments.",
    )

    classified = classify_document(document, scenario(), classified_at="2026-05-19T02:00:00Z")

    assert classified.relevance == "excluded"
    assert classified.matched_primary_terms == ["cbdc", "cross-border payments"]
    assert classified.matched_exclusion_terms == ["bitcoin trading", "cryptocurrency price"]
    assert classified.reason.startswith("Excluded because")


def test_classifier_marks_irrelevant_document() -> None:
    document = make_document(
        title="Financial stability review",
        summary="This document discusses banking profitability.",
    )

    classified = classify_document(document, scenario(), classified_at="2026-05-19T02:00:00Z")

    assert classified.relevance == "irrelevant"
    assert classified.total_match_count == 0
    assert classified.reason == "No configured scenario terms were matched."


def test_load_raw_and_save_classified_documents_jsonl(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    raw_dir.mkdir()

    documents = [
        make_document(
            title="CBDC settlement infrastructure",
            summary="Cross-border payments and central bank digital currency.",
            document_id="doc1",
        ),
        make_document(
            title="Unrelated note",
            summary="Banking profitability update.",
            document_id="doc2",
        ),
    ]

    raw_path = raw_dir / "bis.jsonl"
    with raw_path.open("w", encoding="utf-8") as handle:
        for document in documents:
            handle.write(json.dumps(document.model_dump(mode="json"), sort_keys=True) + "\n")

    loaded_documents = load_raw_documents(raw_dir)
    classified = classify_documents(
        loaded_documents,
        scenario(),
        classified_at="2026-05-19T02:00:00Z",
    )
    output_path = save_classified_documents_jsonl(
        classified,
        scenario_id="cbdc_payment_resilience",
        processed_dir=processed_dir,
    )

    assert output_path == processed_dir / "cbdc_payment_resilience_classified.jsonl"
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2

    payload = json.loads(lines[0])
    assert set(payload) == {
        "document_id",
        "source_id",
        "source_name",
        "source_category",
        "title",
        "url",
        "published_at",
        "summary",
        "content_hash",
        "scenario_id",
        "scenario_name",
        "relevance",
        "matched_primary_terms",
        "matched_secondary_terms",
        "matched_exclusion_terms",
        "total_match_count",
        "reason",
        "classified_at",
    }
    assert payload["scenario_id"] == "cbdc_payment_resilience"
    assert payload["relevance"] == "central"


def test_classifier_ignores_negated_primary_terms() -> None:
    document = make_document(
        title="Clarification note",
        summary=(
            "This is not a CBDC initiative. It is unrelated to cross-border payments "
            "and does not concern settlement infrastructure or programmable money."
        ),
    )

    classified = classify_document(
        document,
        scenario(),
        classified_at="2026-05-19T02:00:00Z",
    )

    assert classified.relevance == "irrelevant"
    assert classified.matched_primary_terms == []
    assert classified.total_match_count == 0


def test_classifier_excludes_search_or_tag_pages() -> None:
    document = make_document(
        title="Search results for CBDC settlement infrastructure",
        summary=(
            "This search page lists CBDC, cross-border payments, settlement "
            "infrastructure, and programmable money results."
        ),
        document_id="search?q=cbdc",
    )

    classified = classify_document(
        document,
        scenario(),
        classified_at="2026-05-19T02:00:00Z",
    )

    assert classified.relevance == "excluded"
    assert "search-results page" in classified.reason


def test_classifier_prevents_title_only_central_false_positive() -> None:
    document = make_document(
        title="CBDC cross-border payments settlement infrastructure programmable money",
        summary="Index page.",
    )

    classified = classify_document(
        document,
        scenario(),
        classified_at="2026-05-19T02:00:00Z",
    )

    assert classified.relevance == "incidental"
    assert "lacks a substantive summary" in classified.reason
