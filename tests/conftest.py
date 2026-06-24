"""Shared pytest fixtures and factories.

New tests should use these instead of re-declaring local copies (the council
flagged `make_classified`/`make_hash`/`PROJECT_ROOT` duplicated across many files).
Existing modules keep their local helpers for now; this is the canonical source
going forward.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.models import ClassifiedDocumentRecord

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ID = "cbdc_payment_resilience"
SCENARIO_NAME = "Cross-border CBDC and payment-system resilience convergence"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def config_dir() -> Path:
    return PROJECT_ROOT / "config"


def make_hash(label: str) -> str:
    """Deterministic 64-char content hash from a short label."""
    return (label * 64)[:64]


def make_classified(
    *,
    document_id: str,
    source_id: str = "bis",
    source_name: str = "Bank for International Settlements",
    source_category: str = "central_bank_coordination",
    relevance: str = "central",
    content_hash: str | None = None,
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
        content_hash=content_hash or make_hash(document_id),
        scenario_id=SCENARIO_ID,
        scenario_name=SCENARIO_NAME,
        relevance=relevance,  # type: ignore[arg-type]
        matched_primary_terms=["cbdc", "cross-border payments"] if relevance == "central" else [],
        matched_secondary_terms=["instant payments"] if relevance == "incidental" else [],
        matched_exclusion_terms=[],
        total_match_count=2 if relevance == "central" else 1,
        reason=f"{relevance} fixture",
        classified_at="2026-05-19T01:00:00Z",
    )


@pytest.fixture
def classified_factory() -> Callable[..., ClassifiedDocumentRecord]:
    return make_classified
