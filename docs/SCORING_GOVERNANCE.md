# Scoring Governance

## Principle

The score is a deterministic evidence-convergence indicator. It is not a prediction, causation model, intent detector, or coordination detector.

## Any scoring change must include

- before/after fixture output
- regression tests
- score-component rationale
- effect on false-positive fixtures
- alert-schema compatibility review
- for weight changes: a regenerated `tests/eval/weight_calibration_report.md` and an
  updated `tests/eval/classifier_report.json`, justifying the chosen vector

## Required score report fields

- scenario ID
- window
- documents considered
- relevance counts
- source-category diversity
- score components
- duplicate/content-hash penalty
- limitations

## Score calibration roadmap

1. ✅ Externalize weights into `app/scoring/weights.py` (`ScoringWeights`), so they
   are auditable data and `score_documents` can be evaluated under alternatives.
2. ✅ Add a labeled evaluation set (`tests/eval/labeled_documents.jsonl`, with
   adversarial cases) and measure classifier precision/recall with CI-enforced floors.
3. ✅ Add a deterministic weight-calibration harness (`tools/calibrate_weights.py`)
   that ranks weight vectors by window separation + monotonicity (advisory).
4. ✅ Build `labeled_windows.jsonl` (expert ordinal band per real document set) and
   measure band agreement (`tests/eval/test_window_calibration.py`); the calibration
   tool now ranks weight vectors by agreement against these windows.
5. ✅ Address the **thin-evidence over-scoring** the windows surfaced (see change log
   below). Implemented as a corroboration factor folded into the components — which
   preserves the components-sum-to-score invariant — rather than a post-hoc cap.
6. Add an advisory semantic/LLM relevance second stage over the keyword floor to
   close the measured recall gap — never overriding the deterministic score.

## Change log

### 0–10 range correction + evidence-based confidence

**Problem.** The component ceilings summed to a maximum of `8.0` (central `3.0` +
diversity `2.0` + trust `2.0` + recency `1.0`), so the documented `0–10` range and
the top of the `high` band were unreachable without a code change. Separately,
`confidence` was a verbatim relabeling of the score band (`>=7` high, `>=3`
medium), so it carried no information independent of the score.

**Change.**
- A single uniform scale factor `SCORE_SCALE = 10/8 = 1.25` maps the component
  basis onto the full `0–10` range. Every component and the duplication penalty are
  scaled by the same factor, so relative weighting and `score = Σ components −
  penalty` are preserved. New ceilings: central `3.75`, diversity `2.5`, trust
  `2.5`, recency `1.25`, penalty `2.5`.
- `confidence` is now derived from evidence sufficiency — the count of distinct
  (deduplicated) contributing documents and the number of agreeing source
  categories — and is independent of score magnitude. Bands: `high` ≥6 docs & ≥3
  categories; `medium` ≥3 docs & ≥2 categories; `low` otherwise.

**Before/after fixture output** (golden alert, `tests/fixtures/golden_alert_cbdc_payment_resilience.json`):

| Field | Before | After |
|---|---|---|
| `convergence_score` | `6.0` | `7.5` (= `6.0 × 1.25`) |
| `confidence` | `medium` (from score band) | `medium` (3 docs / 3 categories) |
| `summary` | "…is present…" | "…is elevated…" (score now reaches the `high` band) |

Representative scoring fixture (`tests/test_scoring.py`): `convergence_score` `5.4 →
6.8`, `source_diversity_score` `2.0 → 2.5`, `duplication_penalty` `0.5 → 0.6`.

**Effect on false-positive fixtures.** Unchanged behavior: false-positive sets
still score below `3.0` and now also report `low` confidence (thin/low-diversity
evidence), reinforcing the guard rather than weakening it.

**Alert-schema compatibility.** No schema change: field names, types, and the
`confidence` enum (`low`/`medium`/`high`) are identical; only values change.

**Not yet done (tracked in the build plan).** Component weights remain
expert-set, not calibrated against a labeled evaluation set. This correction makes
the range honest; it does not yet validate the weights.

### Score additivity + anchored baseline

**Additivity.** `convergence_score` is now derived from the already-rounded
components — `score = clamp(Σ positive components − penalty)` — so the published
breakdown reconciles exactly to the score (previously the score was rounded from
the unrounded sum, allowing up to 0.2 drift). `ScoreComponents` ceilings are
expressed as one-decimal display maxima. A regression test pins the invariant.

**Baseline anchoring.** Baseline comparison no longer compares a score to the
running mean of all its own past scores. Observations are collapsed to one per
calendar day; the reference is a fixed trailing window (`REFERENCE_WINDOW_DAYS`)
that **excludes the current day**; and directional language
(`above`/`below`/`near_baseline`) is withheld — returning `not_enough_history` with
descriptive stats only — until there are at least `MIN_REFERENCE_BUCKETS` daily
buckets spanning at least `REFERENCE_GATE_DAYS`. This removes the cadence-gaming and
self-reference of the previous design. No schema change (the directional fields
were already nullable).

### Corroboration gate (thin-evidence over-scoring)

**Problem (surfaced by window calibration).** Diversity/trust/recency credit
accrued even without corroborating central evidence, so a single central document
scored ~3.6 and incidental-only evidence ~4.7 — both reading as "medium" when
"convergence" should require corroboration. Expert-window band agreement was 0.7.

**Change.** A corroboration factor `min(1, unique_central_count /
corroboration_central_target)` (target = 2) is folded into the diversity, trust,
and recency component bases before scaling. Central evidence is not gated (it *is*
the corroboration) and the duplicate penalty is never softened. This was chosen over
a post-hoc score cap specifically so the components-sum-to-score invariant still
holds (the gate changes component *values*, which still sum to the score).

**Before/after.** Single central doc 3.6 → **2.3** (low); incidental-only 4.7 →
**0.4** (low). Sets with ≥2 central documents are unchanged, so the golden alert
(7.5) and the scoring fixture (6.8) are unaffected. Expert-window band agreement
0.7 → **0.9** (the only remaining disagreement is the paraphrased window — the
keyword recall ceiling, addressed later by an advisory semantic stage).

**Effect on false-positive fixtures / alert schema.** False-positive sets stay
low; no schema change; the additivity invariant and property tests still pass.
