"""Stable JSON alert generation.

This module turns the PR 4 score JSON and classified evidence JSONL into a
conservative institutional JSON alert card. It reports public-document
convergence only. It does not infer intent, coordination, causation, market
direction, or future events.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from dateutil import parser as date_parser

from app.persistence import write_json_atomic

from app.alerts.evidence_filter import filter_evidence_documents, matched_terms
from app.models import (
    AlertEvidenceItem,
    AlertRecord,
    ClassifiedDocumentRecord,
    ConfigBundle,
    ScenarioScoreRecord,
)


ALERT_SCHEMA_VERSION = "sprint-2-pr10"

REQUIRED_ALERT_FIELDS = [
    "scenario_id",
    "scenario_name",
    "generated_at",
    "window_days",
    "convergence_score",
    "confidence",
    "source_categories_active",
    "document_count",
    "summary",
    "evidence",
    "warnings",
    "limitations",
]

WARNINGS = [
    "Baseline model is provisional.",
    "Market-price module is disabled.",
    "Narrative interpretation is disabled.",
]

LIMITATIONS = [
    "This alert reports public-document convergence only.",
    "It does not infer intent, coordination, causation, or future events.",
]


def required_alert_fields() -> list[str]:
    return list(REQUIRED_ALERT_FIELDS)


def load_score_json(
    *,
    scenario_id: str,
    processed_dir: Path | str = Path("data/processed"),
) -> ScenarioScoreRecord:
    score_path = Path(processed_dir) / f"{scenario_id}_score.json"
    if not score_path.exists():
        raise FileNotFoundError(f"Score JSON not found: {score_path}")
    return ScenarioScoreRecord.model_validate_json(score_path.read_text(encoding="utf-8"))


def select_evidence(
    documents: list[ClassifiedDocumentRecord],
    *,
    bundle: ConfigBundle,
    limit: int = 10,
) -> list[AlertEvidenceItem]:
    """Select quality-controlled, deduplicated evidence for the alert card."""

    candidates = filter_evidence_documents(documents, bundle=bundle, limit=limit)

    return [
        AlertEvidenceItem(
            source_id=candidate.document.source_id,
            source_name=candidate.document.source_name,
            source_category=candidate.document.source_category,
            title=candidate.document.title,
            url=candidate.document.url,
            published_at=candidate.document.published_at,
            relevance=candidate.document.relevance,  # type: ignore[arg-type]
            matched_terms=matched_terms(candidate.document),
            reason=candidate.document.reason,
            quality_flags=candidate.quality_flags,
        )
        for candidate in candidates
    ]


def parse_stable_datetime(value: str | None) -> datetime | None:
    """Parse a stored timestamp without falling back to wall-clock time.

    Naive timestamps are treated as UTC so results are independent of the host
    timezone. Invalid or missing timestamps are ignored.
    """

    if not value:
        return None
    try:
        parsed = date_parser.parse(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def canonical_utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def max_stable_timestamp(values: Iterable[str | None]) -> str | None:
    parsed_values = [
        parsed for value in values if (parsed := parse_stable_datetime(value)) is not None
    ]
    if not parsed_values:
        return None
    return canonical_utc_iso(max(parsed_values))


def deterministic_score_anchor(score: ScenarioScoreRecord) -> str | None:
    """Return a stable score-level anchor when the score schema exposes one.

    PR 10 does not introduce a new score field. This hook keeps alert generation
    compatible with a future deterministic score anchor without reading runtime
    run-snapshot timestamps.
    """

    payload = score.model_dump(mode="json")
    for key in ("score_anchor", "score_as_of", "as_of", "anchor_timestamp"):
        anchor = payload.get(key)
        if isinstance(anchor, str):
            parsed = parse_stable_datetime(anchor)
            if parsed is not None:
                return canonical_utc_iso(parsed)
    return None


def deterministic_generated_at(
    evidence: list[AlertEvidenceItem],
    classified_documents: list[ClassifiedDocumentRecord],
    score: ScenarioScoreRecord,
) -> str:
    """Build the stable alert timestamp from evidence, never runtime metadata.

    Fallback order:
    1. Latest ``published_at`` from evidence included in the alert.
    2. Latest ``published_at`` from classified documents.
    3. Future score-level deterministic anchor, when available.
    4. Unix epoch sentinel.
    """

    evidence_anchor = max_stable_timestamp(item.published_at for item in evidence)
    if evidence_anchor is not None:
        return evidence_anchor

    classified_anchor = max_stable_timestamp(
        document.published_at for document in classified_documents
    )
    if classified_anchor is not None:
        return classified_anchor

    score_anchor = deterministic_score_anchor(score)
    if score_anchor is not None:
        return score_anchor

    return "1970-01-01T00:00:00Z"


def build_summary(score: ScenarioScoreRecord) -> str:
    if score.convergence_score >= 7.0:
        return (
            "Public institutional activity related to CBDC and payment-system resilience "
            "is elevated across the classified source set."
        )
    if score.convergence_score >= 3.0:
        return (
            "Public institutional activity related to CBDC and payment-system resilience "
            "is present across the classified source set."
        )
    return (
        "Public institutional activity related to CBDC and payment-system resilience "
        "is limited in the classified source set."
    )


def build_alert_record(
    *,
    bundle: ConfigBundle,
    scenario_id: str,
    score: ScenarioScoreRecord,
    classified_documents: list[ClassifiedDocumentRecord],
) -> AlertRecord:
    scenario = bundle.get_scenario(scenario_id)
    evidence = select_evidence(classified_documents, bundle=bundle)

    return AlertRecord(
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        generated_at=deterministic_generated_at(evidence, classified_documents, score),
        window_days=score.window_days,
        convergence_score=score.convergence_score,
        confidence=score.confidence,
        source_categories_active=score.active_source_categories,
        document_count=score.documents_considered,
        summary=build_summary(score),
        evidence=evidence,
        warnings=WARNINGS.copy(),
        limitations=LIMITATIONS.copy(),
    )


def save_alert_json(
    alert: AlertRecord,
    *,
    processed_dir: Path | str = Path("data/processed"),
) -> Path:
    output_path = Path(processed_dir) / f"{alert.scenario_id}_alert.json"
    write_json_atomic(output_path, alert.model_dump(mode="json"))
    return output_path
