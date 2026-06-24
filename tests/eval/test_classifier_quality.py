"""Measure the deterministic classifier against a labeled evaluation set.

This turns "the keyword classifier seems fine" into measured per-class
precision/recall with explicit floor thresholds that fail CI on regression. The
labeled set (`labeled_documents.jsonl`) is a PROVISIONAL seed — see
tests/eval/README.md — and the floors are the honest current numbers, not
aspirational targets. As the labeled set grows, expect the floors to be revisited.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.classification.keyword_matcher import classify_document
from app.models import DocumentRecord, load_configs

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = Path(__file__).resolve().parent
SCENARIO_ID = "cbdc_payment_resilience"
CLASSES = ["central", "incidental", "excluded", "irrelevant"]

# Honest floors: the current deterministic keyword classifier's measured numbers
# (rounded down). They are regression guards, not aspirations — the keyword layer
# has a real recall ceiling on central items (paraphrase / <2 primary terms).
PRECISION_FLOORS = {"central": 0.85, "incidental": 0.50, "excluded": 1.0, "irrelevant": 0.60}
RECALL_FLOORS = {"central": 0.70, "incidental": 0.50, "excluded": 1.0, "irrelevant": 0.70}


def _load_labeled() -> list[dict]:
    path = EVAL_DIR / "labeled_documents.jsonl"
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _as_document(entry: dict) -> DocumentRecord:
    return DocumentRecord(
        document_id=entry["id"],
        source_id="eval",
        source_name="Evaluation Set",
        source_category="evaluation",
        title=entry["title"],
        url=f"https://example.org/eval/{entry['id']}",
        published_at="2026-05-19T00:00:00Z",
        summary=entry["summary"],
        content_hash=(entry["id"] * 64)[:64],
        ingested_at="2026-05-19T00:00:00Z",
        raw={},
    )


def _metrics(labeled: list[dict]) -> dict:
    bundle = load_configs(PROJECT_ROOT / "config")
    scenario = bundle.get_scenario(SCENARIO_ID)

    confusion = {actual: {predicted: 0 for predicted in CLASSES} for actual in CLASSES}
    for entry in labeled:
        predicted = classify_document(_as_document(entry), scenario).relevance
        confusion[entry["expected_relevance"]][predicted] += 1

    report = {"total": len(labeled), "classes": {}, "confusion": confusion}
    for cls in CLASSES:
        tp = confusion[cls][cls]
        fp = sum(confusion[other][cls] for other in CLASSES if other != cls)
        fn = sum(confusion[cls][other] for other in CLASSES if other != cls)
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall = tp / (tp + fn) if (tp + fn) else 1.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        report["classes"][cls] = {
            "support": tp + fn,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
        }
    correct = sum(confusion[c][c] for c in CLASSES)
    report["accuracy"] = round(correct / len(labeled), 3)
    return report


def test_classifier_quality_meets_floors_and_writes_report() -> None:
    labeled = _load_labeled()
    assert len(labeled) >= 30, "labeled eval set should not shrink below its seed size"

    report = _metrics(labeled)
    # Persist a committed report so weight/classifier changes show a visible diff.
    (EVAL_DIR / "classifier_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    failures = []
    for cls in CLASSES:
        p = report["classes"][cls]["precision"]
        r = report["classes"][cls]["recall"]
        if p < PRECISION_FLOORS[cls]:
            failures.append(f"{cls} precision {p} < floor {PRECISION_FLOORS[cls]}")
        if r < RECALL_FLOORS[cls]:
            failures.append(f"{cls} recall {r} < floor {RECALL_FLOORS[cls]}")
    assert not failures, "; ".join(failures)
