"""Deterministic PR 3 keyword classification.

This module intentionally stops at relevance classification. It does not score,
alert, infer intent, or produce narrative interpretation.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from app.models import ClassifiedDocumentRecord, DocumentRecord, Scenario


NEGATION_PREFIX_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:^|\b)not\s+(?:a|an|the\s+)?$"),
    re.compile(r"(?:^|\b)no\s+$"),
    re.compile(r"(?:^|\b)unrelated\s+to\s+$"),
    re.compile(r"(?:^|\b)not\s+about\s+$"),
    re.compile(r"(?:^|\b)not\s+related\s+to\s+$"),
    re.compile(r"(?:^|\b)excluded\s+from\s+$"),
    re.compile(r"(?:^|\b)outside\s+the\s+scope\s+of\s+$"),
    re.compile(r"(?:^|\b)out\s+of\s+scope\s+for\s+$"),
    re.compile(r"(?:^|\b)without\s+$"),
    re.compile(
        r"(?:^|\b)(?:does|do|did|is|are|was|were)\s+not\s+"
        r"(?:cover|concern|involve|address|relate\s+to|represent|include)\s+$"
    ),
)

INDEX_URL_MARKERS = (
    "/search",
    "?q=",
    "&q=",
    "/tag/",
    "/tags/",
    "/topic/",
    "/topics/",
    "/category/",
    "/categories/",
)

INDEX_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*search\s+results?\b", re.IGNORECASE),
    re.compile(r"^\s*tag\s*:", re.IGNORECASE),
    re.compile(r"^\s*topic\s*:", re.IGNORECASE),
    re.compile(r"^\s*category\s*:", re.IGNORECASE),
    re.compile(r"\bsearch\s+results?\s+for\b", re.IGNORECASE),
)

MIN_SUBSTANTIVE_SUMMARY_CHARS = 40
MIN_SUBSTANTIVE_SUMMARY_WORDS = 6
NEGATION_WINDOW_CHARS = 48


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _term_pattern(term: str) -> re.Pattern[str]:
    """Build a conservative phrase pattern for deterministic matching."""
    normalized = normalize_text(term)
    escaped = re.escape(normalized)
    escaped = escaped.replace(r"\ ", r"\s+")
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)


def _sentence_prefix(text: str, match_start: int) -> str:
    sentence_start = max(
        text.rfind(".", 0, match_start),
        text.rfind("!", 0, match_start),
        text.rfind("?", 0, match_start),
        text.rfind(";", 0, match_start),
    )
    return text[sentence_start + 1 : match_start]


def _has_sentence_level_negation(prefix: str) -> bool:
    negation_markers = (
        "not a",
        "not an",
        "not the",
        "no",
        "unrelated to",
        "not about",
        "not related to",
        "excluded from",
        "outside the scope of",
        "out of scope for",
        "without",
        "does not cover",
        "does not concern",
        "does not involve",
        "does not address",
        "does not relate to",
        "does not represent",
        "does not include",
        "do not cover",
        "do not concern",
        "do not involve",
        "do not address",
        "do not relate to",
        "do not represent",
        "do not include",
        "is not",
        "are not",
        "was not",
        "were not",
    )
    normalized = f" {normalize_text(prefix)} "
    return any(f" {marker} " in normalized for marker in negation_markers)


def _is_negated_match(text: str, match_start: int) -> bool:
    window_start = max(0, match_start - NEGATION_WINDOW_CHARS)
    prefix = text[window_start:match_start]

    if any(pattern.search(prefix) for pattern in NEGATION_PREFIX_PATTERNS):
        return True

    return _has_sentence_level_negation(_sentence_prefix(text, match_start))


def _has_unnegated_term(text: str, term: str) -> bool:
    pattern = _term_pattern(term)

    for match in pattern.finditer(text):
        if not _is_negated_match(text, match.start()):
            return True

    return False


def match_terms(text: str, terms: list[str]) -> list[str]:
    normalized = normalize_text(text)
    matches: list[str] = []

    for term in terms:
        term_normalized = normalize_text(term)
        if term_normalized and _has_unnegated_term(normalized, term_normalized):
            matches.append(term_normalized)

    return sorted(set(matches))


def document_text(document: DocumentRecord) -> str:
    return normalize_text(f"{document.title} {document.summary}")


def _is_index_or_search_page(document: DocumentRecord) -> bool:
    url = document.url.lower()
    title = document.title.strip()

    if any(marker in url for marker in INDEX_URL_MARKERS):
        return True

    return any(pattern.search(title) for pattern in INDEX_TITLE_PATTERNS)


def _has_substantive_summary(summary: str) -> bool:
    normalized = normalize_text(summary)
    words = re.findall(r"\b[\w-]+\b", normalized)

    return (
        len(normalized) >= MIN_SUBSTANTIVE_SUMMARY_CHARS
        and len(words) >= MIN_SUBSTANTIVE_SUMMARY_WORDS
    )


def classify_document(
    document: DocumentRecord,
    scenario: Scenario,
    *,
    classified_at: str | None = None,
) -> ClassifiedDocumentRecord:
    text = document_text(document)
    matched_primary = match_terms(text, scenario.primary_terms)
    matched_secondary = match_terms(text, scenario.secondary_terms)
    matched_exclusion = match_terms(text, scenario.exclusion_terms)
    total_match_count = len(matched_primary) + len(matched_secondary)
    rules = scenario.relevance_rules

    if matched_exclusion:
        relevance = "excluded"
        reason = (
            "Excluded because exclusion terms were matched: "
            + ", ".join(matched_exclusion)
            + "."
        )
    elif _is_index_or_search_page(document):
        relevance = "excluded"
        reason = "Excluded because the document appears to be a tag, topic, or search-results page."
    elif (
        len(matched_primary) >= rules.central_min_primary_matches
        and total_match_count >= rules.central_min_total_matches
        and _has_substantive_summary(document.summary)
    ):
        relevance = "central"
        reason = (
            "The scenario is central to the document because it matched "
            f"{len(matched_primary)} primary term(s) and {total_match_count} total "
            "configured scenario term(s)."
        )
    elif (
        len(matched_primary) >= rules.central_min_primary_matches
        and total_match_count >= rules.central_min_total_matches
        and not _has_substantive_summary(document.summary)
    ):
        relevance = "incidental"
        reason = (
            "The scenario matched configured terms, but the document lacks a "
            "substantive summary required for central relevance."
        )
    elif total_match_count >= rules.incidental_min_total_matches:
        relevance = "incidental"
        reason = (
            "The scenario is mentioned incidentally because it matched "
            f"{total_match_count} configured scenario term(s), below the central "
            "relevance threshold."
        )
    else:
        relevance = "irrelevant"
        reason = "No configured scenario terms were matched."

    return ClassifiedDocumentRecord(
        document_id=document.document_id,
        source_id=document.source_id,
        source_name=document.source_name,
        source_category=document.source_category,
        title=document.title,
        url=document.url,
        published_at=document.published_at,
        summary=document.summary,
        content_hash=document.content_hash,
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        relevance=relevance,
        matched_primary_terms=matched_primary,
        matched_secondary_terms=matched_secondary,
        matched_exclusion_terms=matched_exclusion,
        total_match_count=total_match_count,
        reason=reason,
        classified_at=classified_at or utc_now_iso(),
    )


def load_raw_documents(raw_dir: Path | str = Path("data/raw")) -> list[DocumentRecord]:
    raw_path = Path(raw_dir)

    if not raw_path.exists():
        return []

    documents: list[DocumentRecord] = []

    for jsonl_path in sorted(raw_path.glob("*.jsonl")):
        with jsonl_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()

                if not stripped:
                    continue

                try:
                    documents.append(DocumentRecord.model_validate_json(stripped))
                except ValidationError as exc:
                    raise ValueError(
                        f"Invalid raw document record in {jsonl_path}:{line_number}: {exc}"
                    ) from exc

    return documents


def classify_documents(
    documents: list[DocumentRecord],
    scenario: Scenario,
    *,
    classified_at: str | None = None,
) -> list[ClassifiedDocumentRecord]:
    timestamp = classified_at or utc_now_iso()

    return [
        classify_document(document, scenario, classified_at=timestamp)
        for document in documents
    ]


def save_classified_documents_jsonl(
    classified_documents: list[ClassifiedDocumentRecord],
    *,
    scenario_id: str,
    processed_dir: Path | str = Path("data/processed"),
) -> Path:
    output_dir = Path(processed_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{scenario_id}_classified.jsonl"

    with output_path.open("w", encoding="utf-8") as handle:
        for document in classified_documents:
            handle.write(
                json.dumps(
                    document.model_dump(mode="json"),
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )

    return output_path
