# Scoring Governance — Phase 2

## Rule

A score is a deterministic summary of observed public documents.
It is not a prediction and not evidence of intent, causation, coordination, or inevitability.

## Required score-change process

Any pull request that changes scoring behavior must include:

1. A plain-language rationale.
2. Before/after fixture outputs.
3. Golden regression updates.
4. A statement of non-goals.
5. Operator-facing release notes.

## Score components

Document these for every scenario:

- central document contribution;
- incidental document contribution;
- source-category diversity;
- source trust weighting;
- recency contribution;
- duplicate penalties;
- evidence suppression rules;
- confidence band thresholds.

## Fixture policy

Maintain three fixture classes:

1. **Positive convergence fixture** — should produce a non-zero score.
2. **False-positive fixture** — should not inflate score materially.
3. **Duplicate fixture** — should prove duplicate suppression.

## Review checklist

- Does the score increase only because observable documents justify it?
- Are exclusion terms still respected?
- Are low-quality or duplicate documents suppressed?
- Does the alert language preserve the guardrails?
- Can a reviewer reproduce the score locally?
