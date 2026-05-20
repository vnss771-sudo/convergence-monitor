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
