from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dateutil import parser as date_parser

from app.models import DocumentRecord, IngestionSaveResult, Source


class IngestionError(RuntimeError):
    """Raised when RSS ingestion cannot complete."""


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_whitespace(value: str | None) -> str:
    if not value:
        return ""
    cleaned = html.unescape(value)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def parse_datetime(value: Any) -> str | None:
    """Parse RSS date strings into stable UTC ISO-8601 strings."""
    if not value:
        return None

    if isinstance(value, str):
        try:
            parsed = date_parser.parse(value)
        except (ValueError, TypeError, OverflowError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    return None


def stable_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_document_id(source_id: str, url: str) -> str:
    """Create a deterministic ID from source and canonical item URL."""
    return stable_hash(f"{source_id}|{url}")[:24]


def make_content_hash(
    *,
    source_id: str,
    title: str,
    url: str,
    published_at: str | None,
    summary: str,
) -> str:
    """Hash normalized document content fields deterministically."""
    payload = json.dumps(
        {
            "source_id": source_id,
            "title": title,
            "url": url,
            "published_at": published_at,
            "summary": summary,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return stable_hash(payload)


def extract_entry_url(entry: dict[str, Any]) -> str:
    for key in ("link", "id", "guid"):
        value = entry.get(key)
        if value:
            return str(value).strip()
    raise IngestionError("RSS entry is missing a usable URL, id, or guid.")


def extract_entry_summary(entry: dict[str, Any]) -> str:
    for key in ("summary", "description", "subtitle"):
        value = entry.get(key)
        if value:
            return normalize_whitespace(str(value))
    content = entry.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict) and first.get("value"):
            return normalize_whitespace(str(first["value"]))
    return ""


def normalize_entry(entry: dict[str, Any], source: Source, ingested_at: str) -> DocumentRecord:
    title = normalize_whitespace(str(entry.get("title") or "Untitled RSS item"))
    url = extract_entry_url(entry)
    summary = extract_entry_summary(entry)

    published_at = parse_datetime(
        entry.get("published") or entry.get("updated") or entry.get("created")
    )

    content_hash = make_content_hash(
        source_id=source.id,
        title=title,
        url=url,
        published_at=published_at,
        summary=summary,
    )

    raw_payload = {
        key: value
        for key, value in dict(entry).items()
        if key
        in {
            "id",
            "guid",
            "title",
            "link",
            "published",
            "updated",
            "summary",
            "description",
            "tags",
            "authors",
        }
    }

    return DocumentRecord(
        document_id=make_document_id(source.id, url),
        source_id=source.id,
        source_name=source.name,
        source_category=source.category,
        title=title,
        url=url,
        published_at=published_at,
        summary=summary,
        content_hash=content_hash,
        ingested_at=ingested_at,
        raw=raw_payload,
    )


def fetch_rss_payload(source: Source, timeout_seconds: float = 20.0) -> bytes:
    try:
        import httpx
    except ImportError as exc:
        raise IngestionError(
            "Missing dependency 'httpx'. Install project dependencies with: pip install -e ."
        ) from exc

    try:
        response = httpx.get(str(source.url), timeout=timeout_seconds, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise IngestionError(f"Failed to fetch RSS source '{source.id}': {exc}") from exc

    if not response.content:
        raise IngestionError(f"RSS source '{source.id}' returned an empty response.")

    return response.content


def parse_rss_payload(payload: bytes, source_id: str) -> list[dict[str, Any]]:
    try:
        import feedparser
    except ImportError:
        return parse_rss_payload_stdlib(payload, source_id)

    parsed = feedparser.parse(payload)
    if getattr(parsed, "bozo", False):
        exception = getattr(parsed, "bozo_exception", None)
        raise IngestionError(f"Failed to parse RSS feed '{source_id}': {exception}")

    entries = list(getattr(parsed, "entries", []))
    return [dict(entry) for entry in entries]


def xml_text(element: Any, child_name: str) -> str | None:
    child = element.find(child_name)
    if child is not None and child.text:
        return child.text.strip()

    # Namespace-tolerant fallback for RSS/Atom variants.
    for descendant in list(element):
        if descendant.tag.split("}")[-1] == child_name and descendant.text:
            return descendant.text.strip()

    return None


def parse_rss_payload_stdlib(payload: bytes, source_id: str) -> list[dict[str, Any]]:
    """Minimal RSS/Atom parser used when feedparser is unavailable.

    It intentionally extracts only the fields PR 2 needs. Project environments that
    install dependencies will use feedparser; this fallback keeps tests and basic
    ingestion portable.
    """
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise IngestionError(f"Failed to parse RSS feed '{source_id}': {exc}") from exc

    entries: list[dict[str, Any]] = []

    # RSS 2.0: channel/item
    for item in root.findall(".//item"):
        entries.append(
            {
                "title": xml_text(item, "title"),
                "link": xml_text(item, "link") or xml_text(item, "guid"),
                "id": xml_text(item, "guid"),
                "published": xml_text(item, "pubDate") or xml_text(item, "published"),
                "updated": xml_text(item, "updated"),
                "summary": xml_text(item, "description") or xml_text(item, "summary"),
            }
        )

    if entries:
        return entries

    # Atom: feed/entry
    for entry in root.findall(".//{*}entry"):
        link = None
        for link_element in entry.findall("{*}link"):
            link = link_element.attrib.get("href")
            if link:
                break

        entries.append(
            {
                "title": xml_text(entry, "title"),
                "link": link or xml_text(entry, "id"),
                "id": xml_text(entry, "id"),
                "published": xml_text(entry, "published"),
                "updated": xml_text(entry, "updated"),
                "summary": xml_text(entry, "summary") or xml_text(entry, "content"),
            }
        )

    return entries


def fetch_rss_documents(source: Source, limit: int = 10) -> list[DocumentRecord]:
    if limit < 1:
        raise ValueError("limit must be at least 1")

    payload = fetch_rss_payload(source)
    entries = parse_rss_payload(payload, source.id)[:limit]
    ingested_at = utc_now_iso()

    documents: list[DocumentRecord] = []
    for entry in entries:
        try:
            documents.append(normalize_entry(entry, source, ingested_at))
        except IngestionError:
            # Skip unusable entries but keep the command deterministic for usable records.
            continue

    return documents


def read_documents_jsonl(path: Path) -> list[DocumentRecord]:
    if not path.exists():
        return []

    records: list[DocumentRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(DocumentRecord.model_validate_json(stripped))
            except Exception as exc:
                message = f"Invalid raw JSONL record in {path}:{line_number}: {exc}"
                raise IngestionError(message) from exc
    return records


def save_documents_jsonl(
    documents: list[DocumentRecord],
    *,
    source_id: str,
    raw_dir: Path | str = Path("data/raw"),
    replace: bool = False,
) -> IngestionSaveResult:
    """Append raw documents while deduplicating by document_id and content_hash.

    Repeated ingestion runs must not inflate the raw document set. By default,
    existing records are preserved and only new records are appended. Set
    ``replace=True`` for controlled fixture rebuilds.
    """

    raw_path = Path(raw_dir)
    raw_path.mkdir(parents=True, exist_ok=True)
    output_path = raw_path / f"{source_id}.jsonl"

    existing = [] if replace else read_documents_jsonl(output_path)
    existing_document_ids = {document.document_id for document in existing}
    existing_content_hashes = {document.content_hash for document in existing}

    to_save: list[DocumentRecord] = []
    skipped_document_ids: list[str] = []

    for document in documents:
        document_seen = document.document_id in existing_document_ids
        content_seen = document.content_hash in existing_content_hashes
        if document_seen or content_seen:
            skipped_document_ids.append(document.document_id)
            continue

        to_save.append(document)
        existing_document_ids.add(document.document_id)
        existing_content_hashes.add(document.content_hash)

    mode = "w" if replace else "a"
    with output_path.open(mode, encoding="utf-8") as handle:
        for document in to_save:
            handle.write(
                json.dumps(
                    document.model_dump(mode="json"),
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )

    return IngestionSaveResult(
        raw_path=str(output_path),
        fetched=len(documents),
        saved=len(to_save),
        skipped_existing=len(skipped_document_ids),
        saved_document_ids=[document.document_id for document in to_save],
        skipped_document_ids=skipped_document_ids,
    )
