# Evaluation harness

This directory turns "the classifier and weights seem fine" into **measured,
reproducible** quality with floors that fail CI on regression.

## Contents

- `labeled_documents.jsonl` — a **provisional seed** labeled set (~37 items) of
  realistic CBDC-domain headlines + summaries with an expert `expected_relevance`.
  It deliberately includes adversarial cases (`h*`) — paraphrases and synonyms not
  in the scenario term list — that the deterministic keyword classifier *misses*,
  so the measured numbers reflect the real recall ceiling rather than a flattering
  subset. This is a seed; growing it (especially with more hard cases and real
  ingested documents) is the main way to harden the validity story.
- `test_classifier_quality.py` — classifies every labeled item, computes a
  confusion matrix and per-class precision/recall/F1, writes `classifier_report.json`,
  and asserts per-class **floor thresholds** (honest current numbers, not targets).
- `classifier_report.json` — the committed measurement (regenerated deterministically
  by the test, so a classifier/term change shows a visible diff).
- `weight_calibration_report.md` — output of `tools/calibrate_weights.py`, a
  deterministic grid search over `ScoringWeights` ranked by window separation +
  monotonicity. Advisory only; weights change via a governed PR.

## Current measured quality (seed set)

| class | precision floor | recall floor |
|-------|-----------------|--------------|
| central | 0.85 | 0.70 |
| incidental | 0.50 | 0.50 |
| excluded | 1.00 | 1.00 |
| irrelevant | 0.60 | 0.70 |

The low `irrelevant` precision and `central` recall are **expected and honest**:
the keyword classifier sends paraphrased central items to `irrelevant`. This is the
exact gap an advisory semantic/LLM second stage (build plan, deferred) would close —
without ever overriding the deterministic, auditable floor.

## Running

```bash
python -m pytest tests/eval -q            # measure + enforce floors
python tools/calibrate_weights.py         # regenerate the calibration report
```
