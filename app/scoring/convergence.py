"""Deterministic PR 4 convergence scoring.

This module converts classified JSONL records into an explainable scenario score.
It does not generate alerts, predictions, or narrative interpretations.
"""
from __future__ import annotations

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
from app.persistence import write_json_atomic
from app.scoring.baselines import missing_baseline_comparison
from app.scoring.weights import DEFAULT_WEIGHTS, ScoringWeights


LIMITATIONS = [
    "Baseline model is provisional.",
    "Scoring is deterministic and rule-based.",
    "This does not infer intent, coordination, or future events.",
]

# The component formulas historically produced a basis that summed to a maximum of
# 8.0 (central 3.0 + diversity 2.0 + trust 2.0 + recency 1.0), which left the top of
# the documented 0–10 range — including most of the "high" band — unreachable. A
# single uniform scale factor maps that basis onto the full 0–10 range while
# preserving the relative weighting of every component and the duplication penalty.
# 10 / 8 = 1.25. See docs/SCORING_GOVERNANCE.md for the before/after rationale.
SCORE_SCALE = 10.0 / 8.0


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


def confidence_for_evidence(
    *,
    unique_contributor_count: int,
    active_source_categories: int,
) -> str:
    """Confidence in the score, derived from how much evidence supports it.

    Confidence is deliberately independent of the score's magnitude. It measures
    evidence sufficiency: how many distinct (deduplicated) documents contribute and
    how many institution categories agree. A high score from a single document is
    low confidence; a moderate score corroborated across many sources is not.
    """

    if unique_contributor_count >= 6 and active_source_categories >= 3:
        return "high"
    if unique_contributor_count >= 3 and active_source_categories >= 2:
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
    weights: ScoringWeights = DEFAULT_WEIGHTS,
) -> float:
    if as_of is None:
        return weights.recency_unknown_credit

    published_at = parse_document_datetime(document.published_at)
    if published_at is None:
        return weights.recency_unknown_credit

    age_days = max(0, (as_of - published_at).days)
    if age_days <= weights.recency_recent_days:
        return weights.recency_recent_credit
    if age_days <= weights.recency_mid_days:
        return weights.recency_mid_credit
    if age_days <= weights.recency_old_days:
        return weights.recency_old_credit
    return weights.recency_stale_credit


def score_documents(
    documents: list[ClassifiedDocumentRecord],
    *,
    bundle: ConfigBundle,
    scenario_id: str,
    window_days: int,
    weights: ScoringWeights = DEFAULT_WEIGHTS,
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

    # Component basis values (max sum 8.0); each is scaled onto the 0–10 range below.
    central_basis = min(
        weights.central_cap,
        unique_central_count * weights.central_per_doc
        + unique_incidental_count * weights.incidental_per_doc,
    )

    if active_source_categories == 0:
        diversity_basis = 0.0
    elif active_source_categories == 1:
        diversity_basis = weights.diversity_one
    elif active_source_categories == 2:
        diversity_basis = weights.diversity_two
    else:
        diversity_basis = weights.diversity_many

    trust_basis = min(
        weights.trust_cap,
        sum(source_weights.get(source_id, 0.0) for source_id in active_source_ids)
        * weights.trust_multiplier,
    )

    as_of = _as_of_datetime(window_documents)
    if unique_contributors:
        recency_basis = sum(
            _recency_credit(document, as_of=as_of, weights=weights)
            for document in unique_contributors
        ) / len(unique_contributors)
    else:
        recency_basis = 0.0

    duplicate_count = max(0, len(contributing_documents) - len(unique_contributors))
    penalty_basis = min(weights.penalty_cap, duplicate_count * weights.penalty_per_duplicate)

    # Round each component once, then derive the score from those rounded values so
    # the published breakdown reconciles exactly: convergence_score equals
    # (Σ positive components − penalty), clamped to 0–10. Rounding the score
    # independently of the components (the previous behavior) let the two drift by up
    # to 0.2, which is unacceptable for an explainable, auditable score.
    central_document_score = round(central_basis * SCORE_SCALE, 1)
    source_diversity_score = round(diversity_basis * SCORE_SCALE, 1)
    trust_weight_score = round(trust_basis * SCORE_SCALE, 1)
    recency_score = round(recency_basis * SCORE_SCALE, 1)
    duplication_penalty = round(penalty_basis * SCORE_SCALE, 1)

    convergence_score = round(
        clamp_score(
            central_document_score
            + source_diversity_score
            + trust_weight_score
            + recency_score
            - duplication_penalty
        ),
        1,
    )

    components = ScoreComponents(
        central_document_score=central_document_score,
        source_diversity_score=source_diversity_score,
        trust_weight_score=trust_weight_score,
        recency_score=recency_score,
        duplication_penalty=duplication_penalty,
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
        confidence=confidence_for_evidence(
            unique_contributor_count=len(unique_contributors),
            active_source_categories=active_source_categories,
        ),
        score_components=components,
        baseline_comparison=missing_baseline_comparison(
            scenario_id=scenario_id,
            current_score=convergence_score,
        ),
        limitations=LIMITATIONS.copy(),
    )


def save_score_json(
    score: ScenarioScoreRecord,
    *,
    processed_dir: Path | str = Path("data/processed"),
) -> Path:
    output_path = Path(processed_dir) / f"{score.scenario_id}_score.json"
    write_json_atomic(output_path, score.model_dump(mode="json"))
    return output_path
