from __future__ import annotations

import json
from pathlib import Path

from app.alerts.generator import build_alert_record
from app.classification.keyword_matcher import classify_documents
from app.models import DocumentRecord, load_configs
from app.scoring.convergence import score_documents


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_false_positive_documents() -> list[DocumentRecord]:
    fixture_path = (
        PROJECT_ROOT
        / "data"
        / "fixtures"
        / "false_positives"
        / "cbdc_payment_resilience_raw.jsonl"
    )
    return [
        DocumentRecord.model_validate_json(line)
        for line in fixture_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_false_positive_fixtures_do_not_inflate_score_or_evidence() -> None:
    bundle = load_configs(PROJECT_ROOT / "config")
    scenario = bundle.get_scenario("cbdc_payment_resilience")
    raw_documents = load_false_positive_documents()

    classified = classify_documents(
        raw_documents,
        scenario,
        classified_at="2026-05-19T01:00:00Z",
    )
    counts = {label: sum(1 for item in classified if item.relevance == label) for label in {
        "central",
        "incidental",
        "excluded",
        "irrelevant",
    }}

    score = score_documents(
        classified,
        bundle=bundle,
        scenario_id="cbdc_payment_resilience",
        window_days=30,
    )
    alert = build_alert_record(
        bundle=bundle,
        scenario_id="cbdc_payment_resilience",
        score=score,
        classified_documents=classified,
    )

    assert counts == {
        "central": 0,
        "incidental": 1,
        "excluded": 1,
        "irrelevant": 1,
    }
    assert score.convergence_score < 3.0
    assert score.confidence == "low"
    assert all(item.relevance != "excluded" for item in alert.evidence)
    assert all("bitcoin trading" not in json.dumps(item.model_dump()) for item in alert.evidence)
    assert len(alert.evidence) == 1
    assert alert.evidence[0].quality_flags == [
        "incidental_relevance",
        "limited_support",
        "secondary_terms_only",
        "weak_keyword_match",
    ]
