#!/usr/bin/env python3
"""Generate deterministic local JSONL fixtures for operator demos and tests."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DOCUMENTS: tuple[dict[str, Any], ...] = (
    {
        "source_id": "bis",
        "source_name": "Bank for International Settlements",
        "source_category": "central_bank_coordination",
        "title": "Cross-border payments and settlement infrastructure resilience",
        "url": "https://example.invalid/bis/cross-border-payments-resilience",
        "published_at": "2026-05-01T00:00:00+00:00",
        "summary": (
            "Central bank digital currency work, settlement infrastructure, "
            "cross-border payments, and payment system resilience are discussed."
        ),
    },
    {
        "source_id": "ecb",
        "source_name": "European Central Bank",
        "source_category": "national_central_bank",
        "title": "Payment rails and wholesale CBDC operational update",
        "url": "https://example.invalid/ecb/payment-rails-wholesale-cbdc",
        "published_at": "2026-05-03T00:00:00+00:00",
        "summary": (
            "Wholesale CBDC, instant payments, digital settlement, and financial market "
            "infrastructure modernization are covered."
        ),
    },
    {
        "source_id": "imf",
        "source_name": "International Monetary Fund",
        "source_category": "international_finance",
        "title": "Tokenisation and correspondent banking policy note",
        "url": "https://example.invalid/imf/tokenisation-correspondent-banking",
        "published_at": "2026-05-05T00:00:00+00:00",
        "summary": (
            "Tokenisation, correspondent banking, liquidity bridge design, and "
            "cross-border payments policy coordination are summarized."
        ),
    },
    {
        "source_id": "noise_fixture",
        "source_name": "Noise Fixture",
        "source_category": "fixture",
        "title": "Bitcoin trading desk discusses meme coin momentum",
        "url": "https://example.invalid/noise/bitcoin-meme-coin",
        "published_at": "2026-05-07T00:00:00+00:00",
        "summary": "Cryptocurrency price, bitcoin trading, and meme coin speculation.",
    },
)


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_document(item: dict[str, Any]) -> dict[str, Any]:
    basis = f"{item['source_id']}|{item['url']}|{item['title']}"
    content = f"{item['title']}\n{item['summary']}"
    return {
        "document_id": stable_hash(basis)[:24],
        **item,
        "content_hash": stable_hash(content),
        "ingested_at": datetime(2026, 5, 20, tzinfo=UTC).isoformat(),
        "raw": {"fixture": True, "phase": 2},
    }


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def generate(output_dir: Path) -> None:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in DOCUMENTS:
        record = build_document(item)
        grouped.setdefault(record["source_id"], []).append(record)

    for source_id, records in grouped.items():
        write_jsonl(output_dir / f"{source_id}.jsonl", records)

    manifest = {
        "status": "ok",
        "fixture": "operator_demo_phase2",
        "record_count": sum(len(records) for records in grouped.values()),
        "sources": sorted(grouped),
        "generated_at": datetime(2026, 5, 20, tzinfo=UTC).isoformat(),
    }
    (output_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    generate(args.output_dir)
    print(f"wrote fixture JSONL under {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
