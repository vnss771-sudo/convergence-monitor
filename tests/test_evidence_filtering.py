from __future__ import annotations

from app.alerts.evidence_filter import filter_evidence_documents
from app.alerts.generator import select_evidence
from app.models import ClassifiedDocumentRecord, load_configs


PROJECT_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


def make_hash(label: str) -> str:
    return (label * 64)[:64]


def make_classified(
    *,
    document_id: str,
    relevance: str,
    source_id: str = "bis",
    source_name: str = "Bank for International Settlements",
    source_category: str = "central_bank_coordination",
    content_hash: str | None = None,
    url: str | None = None,
    published_at: str = "2026-05-19T00:00:00Z",
    matched_primary_terms: list[str] | None = None,
    matched_secondary_terms: list[str] | None = None,
    matched_exclusion_terms: list[str] | None = None,
    total_match_count: int | None = None,
) -> ClassifiedDocumentRecord:
    primary = matched_primary_terms
    secondary = matched_secondary_terms
    exclusions = matched_exclusion_terms or []

    if primary is None:
        primary = ["cbdc", "cross-border payments"] if relevance == "central" else []
    if secondary is None:
        secondary = (
            ["settlement infrastructure", "financial market infrastructure"]
            if relevance == "central"
            else ["instant payments"]
        )

    if total_match_count is None:
        total_match_count = len(primary) + len(secondary)

    return ClassifiedDocumentRecord(
        document_id=document_id,
        source_id=source_id,
        source_name=source_name,
        source_category=source_category,
        title=f"{document_id} title",
        url=url or f"https://example.com/{document_id}",
        published_at=published_at,
        summary="CBDC cross-border payments settlement infrastructure.",
        content_hash=content_hash or make_hash(document_id),
        scenario_id="cbdc_payment_resilience",
        scenario_name="Cross-border CBDC and payment-system resilience convergence",
        relevance=relevance,  # type: ignore[arg-type]
        matched_primary_terms=primary,
        matched_secondary_terms=secondary,
        matched_exclusion_terms=exclusions,
        total_match_count=total_match_count,
        reason=f"{relevance} fixture",
        classified_at="2026-05-19T01:00:00Z",
    )


def test_excluded_and_irrelevant_documents_never_become_evidence() -> None:
    bundle = load_configs(PROJECT_ROOT / "config")
    documents = [
        make_classified(document_id="central", relevance="central"),
        make_classified(
            document_id="excluded",
            relevance="excluded",
            matched_primary_terms=["cbdc", "cross-border payments"],
            matched_secondary_terms=[
                "settlement infrastructure",
                "financial market infrastructure",
            ],
            matched_exclusion_terms=["bitcoin trading"],
            total_match_count=4,
        ),
        make_classified(
            document_id="irrelevant",
            relevance="irrelevant",
            matched_primary_terms=[],
            matched_secondary_terms=[],
            total_match_count=0,
        ),
    ]

    evidence = select_evidence(documents, bundle=bundle)

    assert [item.source_id for item in evidence] == ["bis"]
    assert len(evidence) == 1
    assert evidence[0].title == "central title"
    assert evidence[0].quality_flags == [
        "central_relevance",
        "primary_terms_present",
        "multiple_primary_terms",
    ]


def test_evidence_is_ranked_and_incidental_documents_are_limited() -> None:
    bundle = load_configs(PROJECT_ROOT / "config")
    documents = [
        make_classified(document_id="incidental1", relevance="incidental"),
        make_classified(document_id="incidental2", relevance="incidental"),
        make_classified(document_id="incidental3", relevance="incidental"),
        make_classified(
            document_id="central",
            relevance="central",
            source_id="imf",
            source_name="International Monetary Fund",
            source_category="international_finance",
            published_at="2026-05-18T00:00:00Z",
        ),
    ]

    candidates = filter_evidence_documents(documents, bundle=bundle, incidental_limit=2)

    assert [candidate.document.relevance for candidate in candidates] == [
        "central",
        "incidental",
        "incidental",
    ]
    incidental_count = sum(
        1 for candidate in candidates if candidate.document.relevance == "incidental"
    )
    assert incidental_count == 2


def test_duplicate_content_hashes_are_suppressed_in_evidence() -> None:
    bundle = load_configs(PROJECT_ROOT / "config")
    duplicate_hash = make_hash("x")
    documents = [
        make_classified(
            document_id="lower_trust",
            relevance="central",
            source_id="rba",
            source_name="Reserve Bank of Australia",
            source_category="national_central_bank",
            content_hash=duplicate_hash,
            published_at="2026-05-18T00:00:00Z",
        ),
        make_classified(
            document_id="higher_trust",
            relevance="central",
            source_id="bis",
            source_name="Bank for International Settlements",
            source_category="central_bank_coordination",
            content_hash=duplicate_hash,
            published_at="2026-05-17T00:00:00Z",
        ),
    ]

    evidence = select_evidence(documents, bundle=bundle)

    assert len(evidence) == 1
    assert evidence[0].source_id == "bis"
