# Live Acceptance Checklist

## Purpose

This checklist defines the gate for accepting, rejecting, or escalating a live
Convergence Monitor run.

It is intended for operator review, PR acceptance, and pre-go-live validation.

## 1. Static checks

Run:

```bash
python -m app.cli validate-config
pytest -q
python -m compileall -q app tests
python -m app.cli status --scenario cbdc_payment_resilience --window 30d
```

Pass criteria:

- [ ] Config validation returns `status: ok`.
- [ ] Tests pass.
- [ ] Compile succeeds.
- [ ] Status command returns structured JSON.
- [ ] Status warnings are understood and documented.
- [ ] No generated runtime artifacts are packaged in the release zip.

Optional when available:

```bash
python -m ruff check app tests
```

Pass criteria:

- [ ] Ruff passes, or unavailability is explicitly recorded.

## 2. Live verification run

Run:

```bash
python -m app.cli verify-live --scenario cbdc_payment_resilience --window 30d
```

Pass criteria:

- [ ] Command returns structured JSON.
- [ ] `verification_path` is written.
- [ ] `run_snapshot_path` is written.
- [ ] Source outcomes are explicit.
- [ ] Failure states are not hidden.
- [ ] Source availability is not treated as evidence.

## 3. Machine-readable acceptance gate

Run:

```bash
python -m app.cli accept-live --verification data/runs/live_verifications/<verification-file>.json
```

For established scenarios where baseline history is required, run:

```bash
python -m app.cli accept-live --verification data/runs/live_verifications/<verification-file>.json --require-baseline
```

Pass criteria:

- [ ] Output contains `operation: accept_live`.
- [ ] Output contains one decision: `accepted`, `accepted_degraded`, or `rejected`.
- [ ] Required checks all pass for accepted and accepted-degraded runs.
- [ ] Rejected runs exit non-zero.
- [ ] Advisory warnings are documented before archiving.
- [ ] The command is read-only and does not create score, alert, or baseline artifacts.

## 4. Live review pack

Run:

```bash
python -m app.cli review-live --verification data/runs/live_verifications/<verification-file>.json
```

For established scenarios where baseline history is required, run:

```bash
python -m app.cli review-live --verification data/runs/live_verifications/<verification-file>.json --require-baseline
```

Pass criteria:

- [ ] Output contains `operation: live_review_pack`.
- [ ] Output contains the same acceptance decision as `accept-live`.
- [ ] `review_pack_path` is written.
- [ ] Source outcomes are grouped for operator review.
- [ ] Artifact paths are listed when available.
- [ ] Archive recommendation is explicit.
- [ ] Rejected runs still produce a review pack for incident evidence.
- [ ] The command is read-only and does not fetch sources, score, alert, or update baselines.

## 5. Source health gate

Accepted:

- [ ] `status` is `ok`.
- [ ] Most enabled sources return `ok`.
- [ ] No material source category is completely unavailable.

Accepted with degradation:

- [ ] `status` is `degraded`.
- [ ] At least one source returns `ok`.
- [ ] Source failures are named in `warnings`.
- [ ] Remaining evidence is sufficient for the generated score.
- [ ] Degradation is recorded in review notes.

Rejected:

- [ ] `status` is `error`.
- [ ] All enabled sources fail.
- [ ] `documents_ingested` is `0`.
- [ ] `score_generated` is `false` because evidence is unavailable.
- [ ] The operator cannot explain the warnings.

## 6. Evidence gate

Accepted or accepted-degraded runs must satisfy:

- [ ] Evidence is scenario-relevant.
- [ ] Evidence is not dominated by false-positive patterns.
- [ ] Evidence count is consistent with alert confidence.
- [ ] Source category coverage is visible.
- [ ] Excluded evidence is reasonable.
- [ ] Weak evidence is not overstated.

Reject or escalate if:

- [ ] Evidence is unrelated to the scenario.
- [ ] Alert confidence is inconsistent with evidence.
- [ ] Alert includes unsupported claims.
- [ ] Evidence filtering removes essential support.
- [ ] Source failures materially change the interpretation.

## 7. Reproducibility gate

For unchanged raw evidence, rerun:

```text
classify → score → alert
classify → score → alert
```

Pass criteria:

- [ ] Stable alert JSON is identical across reruns.
- [ ] Runtime run snapshots may differ.
- [ ] Classified JSONL may differ only in runtime metadata.
- [ ] `generated_at` is anchored to evidence dates, not runtime classification time.

Reject if:

- [ ] Stable alert JSON changes without evidence changes.
- [ ] Alert `generated_at` is derived from runtime `classified_at`.
- [ ] Golden alert fixture no longer matches expected output.

## 8. Baseline gate

Pass criteria:

- [ ] Missing baseline is reported as `baseline_unavailable`.
- [ ] Available baseline includes observation count.
- [ ] Duplicate baseline observations are suppressed.
- [ ] Baseline comparison does not change the deterministic score.
- [ ] Baseline trend language is conservative.

Reject or escalate if:

- [ ] Missing baseline is treated as negative evidence.
- [ ] Baseline comparison creates false certainty.
- [ ] Duplicate observations inflate history.
- [ ] Generated baseline runtime JSON is packaged accidentally.

## 9. Merge criteria for PRs

A PR can be merged when:

- [ ] Static checks pass.
- [ ] New behavior has deterministic tests.
- [ ] Existing deterministic alert and golden fixture tests pass.
- [ ] No runtime artifacts are included in the release package.
- [ ] Documentation reflects the operator-facing behavior.
- [ ] The PR does not introduce predictions, dashboards, or unsupported narrative.
- [ ] The PR preserves the "no false certainty" rule.

## 10. Go-live criteria for the technical MVP

The technical MVP can be considered live-ready when:

- [ ] Static checks pass in the target environment.
- [ ] At least three real live verification runs have been reviewed.
- [ ] At least one accepted or accepted-degraded run contains real public-source evidence.
- [ ] All rejected runs have clear incident notes.
- [ ] Source failures are understandable and recoverable.
- [ ] Stable alert JSON remains reproducible for unchanged evidence.
- [ ] Baseline state is explicit and does not alter the deterministic score.
- [ ] An operator can explain the latest status output without inspecting code.

## Final acceptance question

Can an operator safely run this system live and know what to do when sources
fail, alerts look weak, or evidence is questionable?


## 11. Live history gate

After repeated live verification runs, run:

```bash
python -m app.cli live-history --scenario cbdc_payment_resilience --runs-dir data/runs
```

Pass criteria:

- [ ] Latest usable run is `accepted` or `accepted_degraded`.
- [ ] Accepted and accepted-degraded runs have review packs.
- [ ] Rejected runs are preserved for incident review.
- [ ] The current usable-run streak is visible.
- [ ] `live-history` warnings are understood before go-live.

Reject or escalate if:

- [ ] Latest live run is rejected.
- [ ] Usable runs are missing review packs.
- [ ] No accepted or accepted-degraded live runs exist.
- [ ] History contradicts the operator's written notes.
