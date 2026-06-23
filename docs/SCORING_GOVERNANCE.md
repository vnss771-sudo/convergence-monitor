# Scoring Governance

## Principle

The score is a deterministic evidence-convergence indicator. It is not a prediction, causation model, intent detector, or coordination detector.

## Any scoring change must include

- before/after fixture output
- regression tests
- score-component rationale
- effect on false-positive fixtures
- alert-schema compatibility review

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

1. Add static calibration fixtures.
2. Add expected component-level outputs.
3. Add adversarial false-positive fixtures.
4. Add scenario-specific acceptance thresholds.
5. Add snapshot tests for generated alert JSON.

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
