"""Property-based invariant tests (hypothesis).

These complement the example-based tests by asserting invariants across many
generated inputs: the score always stays in range and reconciles to its
components, dedupe is deterministic, and date parsing is total (valid ``…Z`` or
``None``, never a crash).
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from app.ingestion.rss_base import parse_datetime
from app.models import ClassifiedDocumentRecord, load_configs
from app.scoring.convergence import score_documents

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_BUNDLE = load_configs(PROJECT_ROOT / "config")

RELEVANCES = ["central", "incidental", "excluded", "irrelevant"]
SOURCES = [
    ("bis", "central_bank_coordination"),
    ("imf", "international_finance"),
    ("rba", "national_central_bank"),
    ("ecb", "national_central_bank"),
    ("federal_reserve", "national_central_bank"),
]


def _hash(seed: int) -> str:
    return f"{seed:064d}"


@st.composite
def _documents(draw):
    n = draw(st.integers(min_value=0, max_value=12))
    docs = []
    for i in range(n):
        relevance = draw(st.sampled_from(RELEVANCES))
        source_id, category = draw(st.sampled_from(SOURCES))
        # Hash drawn from a small pool so duplicates (and the dedup penalty) occur.
        content_hash = _hash(draw(st.integers(min_value=0, max_value=5)))
        docs.append(
            ClassifiedDocumentRecord(
                document_id=f"doc{i}",
                source_id=source_id,
                source_name=source_id.upper(),
                source_category=category,
                title=f"doc{i} title",
                url=f"https://example.com/doc{i}",
                published_at="2026-05-19T00:00:00Z",
                summary="CBDC cross-border payments settlement infrastructure.",
                content_hash=content_hash,
                scenario_id="cbdc_payment_resilience",
                scenario_name="Cross-border CBDC and payment-system resilience convergence",
                relevance=relevance,  # type: ignore[arg-type]
                matched_primary_terms=["cbdc"] if relevance == "central" else [],
                matched_secondary_terms=["instant payments"] if relevance == "incidental" else [],
                matched_exclusion_terms=[],
                total_match_count=2 if relevance == "central" else 1,
                reason=f"{relevance} fixture",
                classified_at="2026-05-19T01:00:00Z",
            )
        )
    return docs


@settings(max_examples=200, deadline=None)
@given(documents=_documents())
def test_score_within_range_and_reconciles(documents):
    score = score_documents(
        documents, bundle=_BUNDLE, scenario_id="cbdc_payment_resilience", window_days=30
    )
    assert 0.0 <= score.convergence_score <= 10.0
    c = score.score_components
    expected = round(
        min(
            10.0,
            max(
                0.0,
                c.central_document_score
                + c.source_diversity_score
                + c.trust_weight_score
                + c.recency_score
                - c.duplication_penalty,
            ),
        ),
        1,
    )
    assert score.convergence_score == expected


@settings(max_examples=100, deadline=None)
@given(documents=_documents())
def test_scoring_is_deterministic(documents):
    a = score_documents(
        documents, bundle=_BUNDLE, scenario_id="cbdc_payment_resilience", window_days=30
    )
    b = score_documents(
        list(reversed(documents)),
        bundle=_BUNDLE,
        scenario_id="cbdc_payment_resilience",
        window_days=30,
    )
    # Order of input documents must not change the deterministic score.
    assert a.convergence_score == b.convergence_score
    assert a.score_components.model_dump() == b.score_components.model_dump()


@given(value=st.text(max_size=40))
def test_parse_datetime_is_total(value):
    result = parse_datetime(value)
    assert result is None or (isinstance(result, str) and result.endswith("Z"))
