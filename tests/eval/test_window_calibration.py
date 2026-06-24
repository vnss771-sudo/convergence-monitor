"""Validate the convergence score against expert-labeled windows.

Each window in `labeled_windows.jsonl` is a set of documents with an expert
ordinal band (low/medium/high) for how much convergence the set represents. We
classify + score each window deterministically and measure agreement with the
expert label. This is the step that turns calibration from synthetic sensitivity
(`tools/calibrate_weights.py`) into validation against human judgment.

The agreement floor is a regression guard at the honest measured level — NOT 100%.
The `w_hard_paraphrase` window is expert-high but paraphrased, so the keyword
classifier under-counts it: that disagreement is expected and documents the recall
ceiling an advisory semantic stage would close.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.models import DocumentRecord, load_configs
from app.classification.keyword_matcher import classify_document
from app.scoring.convergence import score_documents

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = Path(__file__).resolve().parent
SCENARIO_ID = "cbdc_payment_resilience"

# Honest agreement floor: the measured exact-band agreement of the current
# deterministic model against the expert windows. It is 0.7, NOT higher, because
# the harness surfaced three genuine disagreements that are the calibration
# backlog (see tests/eval/README.md), not bugs to paper over:
#   - w_low_single / w_low_incidental: the model is generous to thin/incidental
#     evidence (1 central doc or incidental-only reads as low-medium, not low) —
#     "convergence" arguably should require corroboration; addressing it is a
#     governed scoring change (it trades against the components-sum-to-score
#     invariant, so it needs deliberate design, not a reflexive cap).
#   - w_hard_paraphrase: expert-high but paraphrased, so the keyword classifier
#     under-counts it — the recall ceiling an advisory semantic stage would close.
# This floor is a regression guard: agreement must not drop below today's level.
AGREEMENT_FLOOR = 0.70


def _band(score: float) -> str:
    if score >= 7.0:
        return "high"
    if score >= 3.0:
        return "medium"
    return "low"


def _document(window_id: str, index: int, doc: dict) -> DocumentRecord:
    key = f"{window_id}:{index}:{doc['title']}:{doc['summary']}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return DocumentRecord(
        document_id=f"{window_id}-{index}",
        source_id=doc["source_id"],
        source_name=doc["source_id"].upper(),
        source_category=doc["source_category"],
        title=doc["title"],
        url=f"https://example.org/{window_id}/{index}",
        published_at="2026-05-19T00:00:00Z",
        summary=doc["summary"],
        content_hash=digest,
        ingested_at="2026-05-19T00:00:00Z",
        raw={},
    )


def _load_windows() -> list[dict]:
    with (EVAL_DIR / "labeled_windows.jsonl").open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def test_window_band_agreement_meets_floor_and_writes_report() -> None:
    bundle = load_configs(PROJECT_ROOT / "config")
    scenario = bundle.get_scenario(SCENARIO_ID)
    windows = _load_windows()
    assert len(windows) >= 8

    rows = []
    agree = 0
    for window in windows:
        classified = [
            classify_document(_document(window["id"], i, doc), scenario)
            for i, doc in enumerate(window["documents"])
        ]
        score = score_documents(
            classified, bundle=bundle, scenario_id=SCENARIO_ID, window_days=30
        )
        produced = _band(score.convergence_score)
        matched = produced == window["expected_band"]
        agree += int(matched)
        rows.append(
            {
                "id": window["id"],
                "expected_band": window["expected_band"],
                "produced_band": produced,
                "score": score.convergence_score,
                "agree": matched,
            }
        )

    agreement = round(agree / len(windows), 3)
    report = {"agreement": agreement, "windows": rows}
    (EVAL_DIR / "window_calibration_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    assert agreement >= AGREEMENT_FLOOR, (
        f"window band agreement {agreement} < floor {AGREEMENT_FLOOR}: "
        + json.dumps([r for r in rows if not r["agree"]])
    )
