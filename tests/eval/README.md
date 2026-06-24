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
- `labeled_windows.jsonl` — expert-labeled *windows*: each is a set of documents
  with an ordinal `expected_band` (low/medium/high) for how much convergence the
  set represents. `test_window_calibration.py` scores each window and measures
  exact-band agreement against the expert label (regression-guarded floor),
  writing `window_calibration_report.json`.
- `weight_calibration_report.md` — output of `tools/calibrate_weights.py`, a
  deterministic grid search over `ScoringWeights` ranked by **window agreement**
  (then separation + monotonicity) against the labeled windows. Advisory only;
  weights change via a governed PR.

## Calibration backlog (what the windows surfaced)

Current window band-agreement is **0.7** — and the grid search shows the default
weights already rank #1, i.e. these disagreements are **not** fixable by tuning the
weight knobs:

1. **The model is generous to thin/incidental evidence.** A single central document
   scores ~3.6 (medium) and incidental-only evidence ~4.7 (medium), because the
   diversity/trust/recency components give a floor even without corroboration.
   "Convergence" arguably should require corroboration (≥2 contributing documents,
   ≥1 of them central) to leave the low band. This is a **governed scoring change**:
   it trades against the cycle-2 "components sum to the score" invariant (a
   corroboration cap makes the components exceed the score in capped cases), so it
   needs deliberate design + before/after fixtures, not a reflexive cap.
2. **Paraphrase under-counting** (`w_hard_paraphrase`): an expert-high window scores
   low because the keyword classifier misses paraphrases — the recall ceiling an
   advisory semantic/LLM stage (over the deterministic floor) would close.

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
