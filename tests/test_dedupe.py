from __future__ import annotations

from pathlib import Path

from app.ingestion.rss_base import normalize_entry, save_documents_jsonl
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


def make_document(url: str = "https://example.com/cbdc"):
    return normalize_entry(
        {
            "title": "CBDC and settlement infrastructure",
            "link": url,
            "published": "2026-05-19",
            "summary": "Cross-border payments.",
        },
        make_source(),
        "2026-05-19T00:00:00Z",
    )


def test_append_dedupe_prevents_duplicate_raw_records(tmp_path: Path) -> None:
    document = make_document()

    first = save_documents_jsonl([document], source_id="bis", raw_dir=tmp_path)
    second = save_documents_jsonl([document], source_id="bis", raw_dir=tmp_path)

    assert first.saved == 1
    assert first.skipped_existing == 0
    assert second.saved == 0
    assert second.skipped_existing == 1

    lines = (tmp_path / "bis.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_replace_rebuilds_source_file(tmp_path: Path) -> None:
    original = make_document("https://example.com/one")
    replacement = make_document("https://example.com/two")

    save_documents_jsonl([original], source_id="bis", raw_dir=tmp_path)
    result = save_documents_jsonl([replacement], source_id="bis", raw_dir=tmp_path, replace=True)

    assert result.saved == 1
    assert result.skipped_existing == 0

    lines = (tmp_path / "bis.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert "https://example.com/two" in lines[0]
