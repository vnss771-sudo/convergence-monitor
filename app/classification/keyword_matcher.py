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


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _term_pattern(term: str) -> re.Pattern[str]:
    """Build a conservative phrase pattern for deterministic matching.

    Terms are matched case-insensitively with non-word boundaries so short terms
    such as CBDC do not match inside unrelated longer tokens.
    """
    normalized = normalize_text(term)
    escaped = re.escape(normalized)
    escaped = escaped.replace(r"\ ", r"\s+")
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)


def match_terms(text: str, terms: list[str]) -> list[str]:
    normalized = normalize_text(text)
    matches: list[str] = []
    for term in terms:
        term_normalized = normalize_text(term)
        if term_normalized and _term_pattern(term_normalized).search(normalized):
            matches.append(term_normalized)
    return sorted(set(matches))


def document_text(document: DocumentRecord) -> str:
    return normalize_text(f"{document.title} {document.summary}")


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
    elif (
        len(matched_primary) >= rules.central_min_primary_matches
        and total_match_count >= rules.central_min_total_matches
    ):
        relevance = "central"
        reason = (
            "The scenario is central to the document because it matched "
            f"{len(matched_primary)} primary term(s) and {total_match_count} total "
            "configured scenario term(s)."
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
