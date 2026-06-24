#!/usr/bin/env python3
"""Deterministic weight-calibration harness for the convergence score.

This does NOT auto-change the weights. It grid-searches a constrained, documented
space of `ScoringWeights`, evaluates each vector against representative document
windows built from the labeled eval set, and writes a ranked markdown report so a
human can choose (and justify) a vector via a governed change.

Objective (deterministic, explainable): a good weight vector should
  1. separate a clearly-high-activity window from a clearly-low-activity window
     (larger gap is better), and
  2. stay monotonic — adding corroborating central documents must not lower the
     score.
The default vector is always included and flagged, so the report shows whether the
current expert priors are dominated by an alternative.

Usage:
    python tools/calibrate_weights.py            # writes tests/eval/weight_calibration_report.md
"""

from __future__ import annotations

import itertools
from dataclasses import replace
from pathlib import Path

from app.models import ClassifiedDocumentRecord, load_configs
from app.scoring.convergence import score_documents
from app.scoring.weights import DEFAULT_WEIGHTS, ScoringWeights

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ID = "cbdc_payment_resilience"

# A small, documented grid. Recency tiers and caps are held; the levers most worth
# revisiting are the per-document and trust multipliers and the diversity step.
GRID = {
    "central_per_doc": [0.5, 0.75, 1.0],
    "incidental_per_doc": [0.1, 0.15, 0.25],
    "trust_multiplier": [0.5, 0.75],
    "diversity_two": [1.25, 1.5, 1.75],
}

SOURCES = [
    ("bis", "central_bank_coordination"),
    ("imf", "international_finance"),
    ("rba", "national_central_bank"),
    ("ecb", "national_central_bank"),
    ("federal_reserve", "national_central_bank"),
]


def _doc(i: int, source_id: str, category: str, relevance: str) -> ClassifiedDocumentRecord:
    return ClassifiedDocumentRecord(
        document_id=f"doc{i}",
        source_id=source_id,
        source_name=source_id.upper(),
        source_category=category,
        title=f"doc{i}",
        url=f"https://example.org/{i}",
        published_at="2026-05-19T00:00:00Z",
        summary="CBDC cross-border payments settlement infrastructure.",
        content_hash=f"{i:064d}",
        scenario_id=SCENARIO_ID,
        scenario_name="x",
        relevance=relevance,  # type: ignore[arg-type]
        matched_primary_terms=["cbdc"] if relevance == "central" else [],
        matched_secondary_terms=[],
        matched_exclusion_terms=[],
        total_match_count=2 if relevance == "central" else 1,
        reason="window",
        classified_at="2026-05-19T01:00:00Z",
    )


def _window(n_central: int, categories: int) -> list[ClassifiedDocumentRecord]:
    docs = []
    for i in range(n_central):
        source_id, category = SOURCES[i % max(1, categories)]
        docs.append(_doc(i, source_id, category, "central"))
    return docs


def _score(weights: ScoringWeights, docs: list[ClassifiedDocumentRecord]) -> float:
    bundle = load_configs(ROOT / "config")
    return score_documents(
        docs, bundle=bundle, scenario_id=SCENARIO_ID, window_days=30, weights=weights
    ).convergence_score


def _evaluate(weights: ScoringWeights) -> dict:
    high = _score(weights, _window(5, 3))      # many central docs, broad agreement
    low = _score(weights, _window(1, 1))       # a single isolated central doc
    separation = round(high - low, 2)
    ramp = [_score(weights, _window(n, 3)) for n in (1, 2, 3, 4, 5)]
    monotonic = all(b >= a for a, b in zip(ramp, ramp[1:]))
    return {"high": high, "low": low, "separation": separation, "monotonic": monotonic}


def _vectors() -> list[tuple[ScoringWeights, bool]]:
    keys = list(GRID)
    out: list[tuple[ScoringWeights, bool]] = [(DEFAULT_WEIGHTS, True)]
    for combo in itertools.product(*(GRID[k] for k in keys)):
        weights = replace(DEFAULT_WEIGHTS, **dict(zip(keys, combo)))
        if weights != DEFAULT_WEIGHTS:
            out.append((weights, False))
    return out


def main() -> None:
    rows = []
    for weights, is_default in _vectors():
        result = _evaluate(weights)
        rows.append((weights, is_default, result))

    # Rank monotonic vectors by separation (descending), then deterministically.
    rows.sort(key=lambda r: (not r[2]["monotonic"], -r[2]["separation"]))

    lines = [
        "# Weight calibration report",
        "",
        "Deterministic grid search over `ScoringWeights`. This report is advisory:",
        "weights change only via a governed PR (see docs/SCORING_GOVERNANCE.md).",
        "Objective: maximise separation between a high- and low-activity window while",
        "staying monotonic in corroborating central documents.",
        "",
        "| rank | central/doc | incid/doc | trust×  | div(2) | separation | monotonic | default |",
        "|------|-------------|-----------|---------|--------|------------|-----------|---------|",
    ]
    for rank, (w, is_default, res) in enumerate(rows[:15], start=1):
        lines.append(
            f"| {rank} | {w.central_per_doc} | {w.incidental_per_doc} | "
            f"{w.trust_multiplier} | {w.diversity_two} | {res['separation']} | "
            f"{'yes' if res['monotonic'] else 'NO'} | {'★' if is_default else ''} |"
        )
    default_rank = next(i for i, r in enumerate(rows, 1) if r[1])
    lines += [
        "",
        f"Default vector rank: **{default_rank} / {len(rows)}**.",
        "",
        "Note: windows here are synthetic representatives, not human-labeled ordinal",
        "targets. Building `labeled_windows.jsonl` (expert band per real document set)",
        "is the next step to turn this from a sensitivity tool into true calibration.",
        "",
    ]
    out_path = ROOT / "tests/eval/weight_calibration_report.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out_path.relative_to(ROOT)} ({len(rows)} vectors evaluated)")


if __name__ == "__main__":
    main()
