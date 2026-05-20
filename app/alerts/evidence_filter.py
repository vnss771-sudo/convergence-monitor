"""Evidence quality controls for alert generation.

This module keeps weak or noisy keyword matches from becoming positive alert
support. It does not change scoring and does not add narrative interpretation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from dateutil import parser as date_parser

from app.models import ClassifiedDocumentRecord, ConfigBundle


RELEVANCE_PRIORITY = {"central": 2, "incidental": 1}


@dataclass(frozen=True)
class EvidenceCandidate:
    document: ClassifiedDocumentRecord
    quality_flags: list[str]


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


def matched_terms(document: ClassifiedDocumentRecord) -> list[str]:
    """Return unique matched primary + secondary terms in deterministic order."""

    return list(dict.fromkeys(document.matched_primary_terms + document.matched_secondary_terms))


def quality_flags_for_document(document: ClassifiedDocumentRecord) -> list[str]:
    """Describe why a document is eligible but still analytically bounded."""

    flags: list[str] = []

    if document.relevance == "central":
        flags.append("central_relevance")
        if document.matched_primary_terms:
            flags.append("primary_terms_present")
        if len(document.matched_primary_terms) >= 2:
            flags.append("multiple_primary_terms")
    elif document.relevance == "incidental":
        flags.append("incidental_relevance")
        flags.append("limited_support")
        if not document.matched_primary_terms:
            flags.append("secondary_terms_only")

    if document.total_match_count <= 1:
        flags.append("weak_keyword_match")

    return flags


def is_evidence_eligible(
    document: ClassifiedDocumentRecord,
    *,
    bundle: ConfigBundle,
) -> bool:
    """Return whether a classified document can appear as positive alert evidence."""

    if document.relevance not in RELEVANCE_PRIORITY:
        return False

    if document.matched_exclusion_terms:
        return False

    scenario = bundle.get_scenario(document.scenario_id)
    rules = scenario.relevance_rules

    if document.relevance == "central":
        return (
            len(document.matched_primary_terms) >= rules.central_min_primary_matches
            and document.total_match_count >= rules.central_min_total_matches
        )

    if document.relevance == "incidental":
        return document.total_match_count >= rules.incidental_min_total_matches

    return False


def _candidate_sort_key(
    candidate: EvidenceCandidate,
    *,
    source_weights: dict[str, float],
) -> tuple[int, float, datetime, str]:
    document = candidate.document
    return (
        RELEVANCE_PRIORITY[document.relevance],
        source_weights.get(document.source_id, 0.0),
        parse_document_datetime(document.published_at) or datetime.min,
        document.document_id,
    )


def filter_evidence_documents(
    documents: list[ClassifiedDocumentRecord],
    *,
    bundle: ConfigBundle,
    limit: int = 10,
    incidental_limit: int = 2,
) -> list[EvidenceCandidate]:
    """Filter, dedupe, and rank evidence candidates for alert JSON.

    Rules:
    - excluded and irrelevant documents never become positive evidence
    - documents with exclusion terms never become positive evidence
    - duplicate content hashes and URLs are suppressed
    - central evidence ranks before incidental evidence
    - incidental evidence is capped so weak matches cannot dominate
    """

    source_weights = {source.id: source.trust_weight for source in bundle.sources.sources}
    best_by_hash: dict[str, EvidenceCandidate] = {}
    seen_urls: set[str] = set()

    for document in documents:
        if not is_evidence_eligible(document, bundle=bundle):
            continue

        if document.url in seen_urls:
            continue
        seen_urls.add(document.url)

        candidate = EvidenceCandidate(
            document=document,
            quality_flags=quality_flags_for_document(document),
        )
        existing = best_by_hash.get(document.content_hash)
        if existing is None:
            best_by_hash[document.content_hash] = candidate
            continue

        if _candidate_sort_key(candidate, source_weights=source_weights) > _candidate_sort_key(
            existing,
            source_weights=source_weights,
        ):
            best_by_hash[document.content_hash] = candidate

    ranked = sorted(
        best_by_hash.values(),
        key=lambda candidate: _candidate_sort_key(candidate, source_weights=source_weights),
        reverse=True,
    )

    central = [candidate for candidate in ranked if candidate.document.relevance == "central"]
    incidental = [
        candidate for candidate in ranked if candidate.document.relevance == "incidental"
    ][:incidental_limit]

    return (central + incidental)[:limit]
