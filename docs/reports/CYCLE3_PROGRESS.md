# Cycle 3 — Progress Note

**Predecessors:** `CODE_COUNCIL_REPORT_CYCLE2.md`, `BUILD_PLAN_CYCLE2.md`.
**Focus:** execution of the two frontier items the cycle-2 council said matter most —
**validity** (make the number defensible) and **product** (pipeline → user surface) —
plus the supporting harness. The codebase was well-mapped by two prior council
rounds, so this cycle built rather than re-audited.

## Shipped

### Validity — weight calibration & classifier measurement
- **Weights externalized** into `app/scoring/weights.py` (`ScoringWeights`),
  threaded through `score_documents` with defaults that reproduce current behavior
  exactly. Weights are now auditable data, and scoring can be evaluated under
  alternative vectors.
- **Labeled evaluation set** (`tests/eval/labeled_documents.jsonl`, ~37 items)
  including adversarial paraphrase cases the keyword classifier provably misses.
- **Classifier quality measured & gated** (`tests/eval/test_classifier_quality.py`):
  per-class precision/recall/F1 with CI-enforced floors. Honest measured baseline:
  **accuracy 0.865, central recall 0.769, irrelevant precision 0.615** — the keyword
  layer's real recall ceiling, now a regression guard rather than a vibe.
- **Calibration harness** (`tools/calibrate_weights.py`): deterministic grid search
  over `ScoringWeights`, ranked by window separation + monotonicity, writing an
  advisory report. Weight changes go through a governed PR with the report attached.

### Product — static dashboard
- **`web/`**: a dependency-free static dashboard rendering the existing alert JSON —
  score gauge + band, confidence badge, summary, ranked evidence table, verbatim
  warnings/limitations, and an SVG score-over-time sparkline. Ships with seed data so
  it renders out of the box, and carries a visible *"Provisional — not yet
  calibrated"* banner.
- **`.github/workflows/dashboard-refresh.yml`**: nightly + manual, least-privilege,
  runs the pipeline and commits refreshed `web/data`.

**Gate:** do not publish the dashboard to real users until weight calibration against
labeled *windows* lands — an uncalibrated public number is the credibility risk.

## Verification
`make check` green (134 tests, ~85% coverage), ruff clean, guardrail audit clean,
golden/byte-stability/property tests intact. Behavior-preserving weight externalization.

## Remaining (carried forward)
| Item | Effort | Note |
|---|---|---|
| `labeled_windows.jsonl` + true window-level calibration | M | turns the sensitivity tool into calibration against human ordinal judgment |
| Advisory semantic/LLM relevance second stage over the keyword floor | M–L | closes the measured recall gap without overriding the deterministic score |
| SHA-pin GitHub Actions | S–M | deferred: reliable tag→SHA resolution needs gh/API; verify on CI |
| `tests/conftest.py` consolidation | S–M | mechanical; divergent helper defaults need care |
| Package `config/*.yaml` as data (`pip install` outside repo) | L | changes the repo-relative runtime contract |
| Per-patch coverage floor (`diff-cover`) + CLI command-body tests | M | lifts the 31–37% command glue |
