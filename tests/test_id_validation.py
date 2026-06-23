"""Source/Scenario id format validation (path-safety hardening)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import RelevanceRules, Scenario, Source


def _source(source_id: str) -> Source:
    return Source(
        id=source_id,
        name="Example",
        category="central_bank_coordination",
        type="rss",
        trust_weight=1.0,
        url="https://example.com/feed.xml",
    )


def _scenario(scenario_id: str) -> Scenario:
    return Scenario(
        id=scenario_id,
        name="Example",
        description="Example scenario",
        primary_terms=["alpha"],
        secondary_terms=["beta"],
        relevance_rules=RelevanceRules(
            central_min_primary_matches=1,
            central_min_total_matches=2,
            incidental_min_total_matches=1,
        ),
    )


@pytest.mark.parametrize("good", ["bis", "federal_reserve", "cbdc_payment_resilience", "src-1"])
def test_valid_ids_accepted(good):
    assert _source(good).id == good
    assert _scenario(good).id == good


@pytest.mark.parametrize("bad", ["../evil", "a/b", "with space", "q?x=1", "name.json", ""])
def test_unsafe_ids_rejected(bad):
    with pytest.raises(ValidationError):
        _source(bad)
    with pytest.raises(ValidationError):
        _scenario(bad)
