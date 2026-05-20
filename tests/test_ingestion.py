from __future__ import annotations

import json
from pathlib import Path

from app.ingestion.rss_base import (
    fetch_rss_documents,
    make_content_hash,
    make_document_id,
    normalize_entry,
    save_documents_jsonl,
)
from app.models import Source


def make_source() -> Source:
    return Source(
        id="bis",
        name="Bank for International Settlements",
        category="central_bank_coordination",
        type="rss",
        enabled=True,
        trust_weight=1.0,
        url="https://www.bis.org/rss/bispublications.xml",
    )


def test_document_id_is_deterministic() -> None:
    assert make_document_id("bis", "https://example.com/doc") == make_document_id(
        "bis", "https://example.com/doc"
    )
    assert make_document_id("bis", "https://example.com/doc") != make_document_id(
        "imf", "https://example.com/doc"
    )


def test_content_hash_is_deterministic() -> None:
    kwargs = {
        "source_id": "bis",
        "title": "CBDC paper",
        "url": "https://example.com/cbdc",
        "published_at": "2026-05-19T00:00:00Z",
        "summary": "Cross-border payments and settlement infrastructure.",
    }

    assert make_content_hash(**kwargs) == make_content_hash(**kwargs)


def test_normalize_entry_contains_required_fields() -> None:
    source = make_source()
    document = normalize_entry(
        {
            "title": "CBDC and cross-border payments",
            "link": "https://example.com/cbdc",
            "published": "Tue, 19 May 2026 00:00:00 GMT",
            "summary": "<p>Settlement infrastructure update.</p>",
        },
        source,
        "2026-05-19T00:00:00Z",
    )

    payload = document.model_dump()
    assert set(payload) == {
        "document_id",
        "source_id",
        "source_name",
        "source_category",
        "title",
        "url",
        "published_at",
        "summary",
        "content_hash",
        "ingested_at",
        "raw",
    }
    assert payload["source_id"] == "bis"
    assert payload["source_name"] == "Bank for International Settlements"
    assert payload["source_category"] == "central_bank_coordination"
    assert payload["summary"] == "Settlement infrastructure update."


def test_save_documents_jsonl_writes_one_record_per_line(tmp_path: Path) -> None:
    source = make_source()
    document = normalize_entry(
        {
            "title": "CBDC and settlement infrastructure",
            "link": "https://example.com/cbdc",
            "published": "2026-05-19",
            "summary": "Cross-border payments.",
        },
        source,
        "2026-05-19T00:00:00Z",
    )

    result = save_documents_jsonl([document], source_id="bis", raw_dir=tmp_path)

    assert result.raw_path == str(tmp_path / "bis.jsonl")
    assert result.fetched == 1
    assert result.saved == 1
    assert result.skipped_existing == 0

    lines = (tmp_path / "bis.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    payload = json.loads(lines[0])
    assert payload["document_id"] == document.document_id
    assert payload["content_hash"] == document.content_hash


def test_fetch_rss_documents_uses_source_and_limit(monkeypatch) -> None:
    source = make_source()

    def fake_fetch_payload(_source: Source) -> bytes:
        return b"fake"

    def fake_parse_payload(_payload: bytes, _source_id: str) -> list[dict]:
        return [
            {
                "title": "CBDC item 1",
                "link": "https://example.com/1",
                "published": "2026-05-19",
                "summary": "Cross-border payments.",
            },
            {
                "title": "CBDC item 2",
                "link": "https://example.com/2",
                "published": "2026-05-18",
                "summary": "Settlement infrastructure.",
            },
        ]

    monkeypatch.setattr("app.ingestion.rss_base.fetch_rss_payload", fake_fetch_payload)
    monkeypatch.setattr("app.ingestion.rss_base.parse_rss_payload", fake_parse_payload)

    documents = fetch_rss_documents(source, limit=1)

    assert len(documents) == 1
    assert documents[0].source_id == "bis"
    assert documents[0].title == "CBDC item 1"
