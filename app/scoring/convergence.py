"""Deterministic PR 4 convergence scoring.

This module converts classified JSONL records into an explainable scenario score.
It does not generate alerts, predictions, or narrative interpretations.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path

from dateutil import parser as date_parser
from pydantic import ValidationError

from app.models import (
    ClassifiedDocumentRecord,
    ConfigBundle,
    ScenarioScoreRecord,
    ScoreComponents,
)
from app.scoring.baselines import missing_baseline_comparison


LIMITATIONS = [
    "Baseline model is provisional.",
    "Scoring is deterministic and rule-based.",
    "This does not infer intent, coordination, or future events.",
]


def clamp_score(value: float, minimum: float = 0.0, maximum: float = 10.0) -> float:
    return max(minimum, min(maximum, value))


def parse_window_days(window: str) -> int:
    """Parse a simple day window such as 30d."""

    match = re.fullmatch(r"([1-9][0-9]*)d", window.strip().lower())
    if not match:
        raise ValueError("window must be a positive day window such as 30d")
    return int(match.group(1))


def parse_document_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = date_parser.parse(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(tz=None).replace(tzinfo=None)
    return parsed


def confidence_for_score(score: float) -> str:
    if score >= 7.0:
        return "high"
    if score >= 3.0:
        return "medium"
    return "low"


def load_classified_documents(
    *,
    scenario_id: str,
    processed_dir: Path | str = Path("data/processed"),
) -> list[ClassifiedDocumentRecord]:
    classified_path = Path(processed_dir) / f"{scenario_id}_classified.jsonl"
    if not classified_path.exists():
        return []

    documents: list[ClassifiedDocumentRecord] = []
    with classified_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                documents.append(ClassifiedDocumentRecord.model_validate_json(stripped))
            except ValidationError as exc:
                raise ValueError(
                    f"Invalid classified document record in {classified_path}:{line_number}: {exc}"
                ) from exc

    return documents


def _as_of_datetime(documents: Iterable[ClassifiedDocumentRecord]) -> datetime | None:
    """Use the latest document timestamp as the deterministic scoring anchor.

    This avoids score drift caused by wall-clock time when the stored document set
    has not changed.
    """

    dates = [
        parsed
        for document in documents
        if (parsed := parse_document_datetime(document.published_at)) is not None
    ]
    if not dates:
        return None
    return max(dates)


def filter_documents_to_window(
    documents: list[ClassifiedDocumentRecord],
    *,
    window_days: int,
) -> list[ClassifiedDocumentRecord]:
    if not documents:
        return []

    as_of = _as_of_datetime(documents)
    if as_of is None:
        return documents

    cutoff = as_of - timedelta(days=window_days)
    filtered: list[ClassifiedDocumentRecord] = []
    for document in documents:
        published_at = parse_document_datetime(document.published_at)
        if published_at is None or published_at >= cutoff:
            filtered.append(document)

    return filtered


def _deduplicate_contributing_documents(
    documents: list[ClassifiedDocumentRecord],
) -> list[ClassifiedDocumentRecord]:
    """Keep one scoring contributor per content hash.

    If duplicate hashes have different relevance labels, keep the strongest
    relevance so duplicates do not inflate the positive score.
    """

    priority = {"central": 2, "incidental": 1}
    deduped: dict[str, ClassifiedDocumentRecord] = {}

    for document in documents:
        if document.relevance not in priority:
            continue

        existing = deduped.get(document.content_hash)
        if existing is None:
            deduped[document.content_hash] = document
            continue

        existing_priority = priority[existing.relevance]
        current_priority = priority[document.relevance]
        if current_priority > existing_priority:
            deduped[document.content_hash] = document
        elif current_priority == existing_priority:
            # Stable tie-break: prefer lexical document ID so output is deterministic.
            if document.document_id < existing.document_id:
                deduped[document.content_hash] = document

    return sorted(deduped.values(), key=lambda item: item.document_id)


def _recency_credit(
    document: ClassifiedDocumentRecord,
    *,
    as_of: datetime | None,
) -> float:
    if as_of is None:
        return 0.2

    published_at = parse_document_datetime(document.published_at)
    if published_at is None:
        return 0.2

    age_days = max(0, (as_of - published_at).days)
    if age_days <= 7:
        return 1.0
    if age_days <= 14:
        return 0.7
    if age_days <= 30:
        return 0.4
    return 0.0


def score_documents(
    documents: list[ClassifiedDocumentRecord],
    *,
    bundle: ConfigBundle,
    scenario_id: str,
    window_days: int,
) -> ScenarioScoreRecord:
    # Validate scenario exists even though PR 4 does not use scenario text directly.
    bundle.get_scenario(scenario_id)
    source_weights = {source.id: source.trust_weight for source in bundle.sources.sources}

    window_documents = filter_documents_to_window(documents, window_days=window_days)

    central_documents = [doc for doc in window_documents if doc.relevance == "central"]
    incidental_documents = [doc for doc in window_documents if doc.relevance == "incidental"]
    excluded_documents = [doc for doc in window_documents if doc.relevance == "excluded"]
    irrelevant_documents = [doc for doc in window_documents if doc.relevance == "irrelevant"]

    contributing_documents = central_documents + incidental_documents
    unique_contributors = _deduplicate_contributing_documents(contributing_documents)
    unique_central_count = sum(1 for doc in unique_contributors if doc.relevance == "central")
    unique_incidental_count = sum(
        1 for doc in unique_contributors if doc.relevance == "incidental"
    )

    active_source_categories = len({doc.source_category for doc in unique_contributors})
    active_source_ids = {doc.source_id for doc in unique_contributors}

    central_document_score = min(
        3.0,
        unique_central_count * 0.75 + unique_incidental_count * 0.15,
    )

    if active_source_categories == 0:
        source_diversity_score = 0.0
    elif active_source_categories == 1:
        source_diversity_score = 0.75
    elif active_source_categories == 2:
        source_diversity_score = 1.50
    else:
        source_diversity_score = 2.00

    trust_weight_score = min(
        2.0,
        sum(source_weights.get(source_id, 0.0) for source_id in active_source_ids) * 0.5,
    )

    as_of = _as_of_datetime(window_documents)
    if unique_contributors:
        recency_score = sum(
            _recency_credit(document, as_of=as_of) for document in unique_contributors
        ) / len(unique_contributors)
    else:
        recency_score = 0.0

    duplicate_count = max(0, len(contributing_documents) - len(unique_contributors))
    duplication_penalty = min(2.0, duplicate_count * 0.5)

    raw_score = (
        central_document_score
        + source_diversity_score
        + trust_weight_score
        + recency_score
        - duplication_penalty
    )
    convergence_score = round(clamp_score(raw_score), 1)

    components = ScoreComponents(
        central_document_score=round(central_document_score, 1),
        source_diversity_score=round(source_diversity_score, 1),
        trust_weight_score=round(trust_weight_score, 1),
        recency_score=round(recency_score, 1),
        duplication_penalty=round(duplication_penalty, 1),
    )

    return ScenarioScoreRecord(
        status="ok",
        scenario_id=scenario_id,
        window_days=window_days,
        documents_considered=len(window_documents),
        central_documents=len(central_documents),
        incidental_documents=len(incidental_documents),
        excluded_documents=len(excluded_documents),
        irrelevant_documents=len(irrelevant_documents),
        active_source_categories=active_source_categories,
        convergence_score=convergence_score,
        confidence=confidence_for_score(convergence_score),
        score_components=components,
        baseline_comparison=missing_baseline_comparison(
            scenario_id=scenario_id,
            current_score=convergence_score,
        ).model_dump(mode="json"),
        limitations=LIMITATIONS.copy(),
    )


def save_score_json(
    score: ScenarioScoreRecord,
    *,
    processed_dir: Path | str = Path("data/processed"),
) -> Path:
    output_dir = Path(processed_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{score.scenario_id}_score.json"

    output_path.write_text(
        json.dumps(
            score.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    return output_path
