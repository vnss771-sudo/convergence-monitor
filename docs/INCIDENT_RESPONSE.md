# Incident Response

## Purpose

This guide defines how to respond when live verification, source health, scoring,
alerting, or reproducibility checks fail.

The goal is to preserve trust. A visible failure is better than a hidden or
overstated signal.

## Severity levels

### SEV-3: Minor degradation

Examples:

- One non-critical source returns `empty`.
- One source has a transient timeout.
- A baseline is unavailable for a new scenario.
- Status warnings are informational and explainable.

Response:

1. Record the warning.
2. Mark the run `accepted_degraded` if evidence remains sufficient.
3. Recheck source health on the next live run.
4. Do not change score logic.

### SEV-2: Material degradation

Examples:

- A major source category is unavailable.
- Multiple sources return `network_error`, `timeout`, or `parse_error`.
- Evidence count is low but score/alert artifacts are generated.
- Baseline comparison is unavailable for an established scenario.
- Alert confidence appears higher than evidence quality supports.

Response:

1. Mark the run `accepted_degraded` or `rejected`.
2. Identify impacted source IDs.
3. Inspect verification and run snapshot artifacts.
4. Review evidence manually.
5. File a source-specific hardening task if parsing or feed structure changed.
6. Do not claim full scenario health.

### SEV-1: Trust failure

Examples:

- All live sources fail.
- No documents are ingested.
- Alert JSON changes across repeated runs with unchanged evidence.
- Alert generation occurs without evidence.
- Runtime timestamps leak into stable alert JSON.
- False-positive evidence drives the alert.
- Score or alert artifacts are malformed.
- The operator cannot explain the output.

Response:

1. Mark the run `rejected`.
2. Do not use the alert operationally.
3. Preserve verification and run snapshot artifacts.
4. Identify the first failing pipeline stage.
5. Fix the deterministic or evidence-quality issue before accepting new output.
6. Add or update tests to prevent recurrence.

## Common incidents

### All sources return `network_error`

Likely causes:

- Sandbox or host has no DNS/network access.
- External network is blocked.
- Source domains are temporarily unavailable.

Operator action:

- Treat the run as `rejected` for live evidence.
- Confirm that `score_generated` and `alert_generated` are false when no
  documents were ingested.
- Confirm warnings name each failing source.
- Do not interpret source failure as scenario signal.

### Source returns `parse_error`

Likely causes:

- Feed schema changed.
- HTML or XML format changed.
- Required fields are missing or malformed.

Operator action:

- Record the source ID.
- Inspect the raw source manually outside the monitor if network access exists.
- Add parser hardening or source-specific tests.
- Keep the run degraded or rejected depending on evidence impact.

### Source returns `empty`

Likely causes:

- No recent documents in the selected window.
- Source feed is live but quiet.
- Limit/window combination is too narrow.

Operator action:

- Confirm the source did not fail.
- Review whether other sources provide enough evidence.
- Do not treat an empty source as negative convergence evidence.

### Alert looks weak

Warning signs:

- Low evidence count.
- Narrow source coverage.
- Evidence is tangential.
- Confidence appears too high.
- Included evidence resembles known false positives.

Operator action:

- Review included and excluded evidence.
- Compare with false-positive fixtures.
- Reject or escalate if the alert overstates the evidence.
- Add a fixture if a new false-positive pattern is found.

### Alert is not reproducible

Warning signs:

- Stable alert JSON changes between reruns.
- `generated_at` changes despite unchanged raw evidence.
- Golden alert fixture test fails.

Operator action:

- Mark as SEV-1.
- Inspect alert timestamp anchoring.
- Confirm generated stable fields do not depend on runtime classification time.
- Add a regression test before accepting a fix.

### Baseline state is confusing

Warning signs:

- `baseline_unavailable` is interpreted as a trend.
- Duplicate observations inflate baseline history.
- Baseline comparison appears to alter the score.

Operator action:

- Treat baseline as advisory only.
- Verify duplicate suppression.
- Reject language that implies trend without adequate baseline history.
- Confirm deterministic score is unchanged by baseline comparison.

## Recovery checklist

Before returning to accepted status:

- [ ] Root cause is identified.
- [ ] Runtime artifact paths are preserved.
- [ ] A deterministic test or fixture covers the failure when practical.
- [ ] Static checks pass.
- [ ] Live verification returns structured JSON.
- [ ] Operator can explain source health, evidence quality, and confidence.
- [ ] No generated runtime artifacts are included in release packaging.

## Incident record template

```text
Date:
Scenario:
Command:
Exit code:
Status:
Decision: accepted | accepted_degraded | rejected
Impacted sources:
Documents ingested:
Score generated:
Alert generated:
Warnings:
Artifact paths:
Root cause:
Operator notes:
Follow-up task:
```

## Operating principle

Do not repair trust failures with narrative. Repair them with explicit source
state, evidence review, deterministic tests, and conservative output.


### Acceptance gate rejects a live artifact

Likely causes:

- The verification artifact has `status: error`.
- No live documents were ingested.
- No source returned usable documents.
- Score or alert generation did not complete.
- Source outcome counts are internally inconsistent.
- `--require-baseline` was used and no baseline is available.

Operator action:

- Treat the run as `rejected`.
- Do not manually override required-check failures.
- Inspect the failed `checks` array in the `accept-live` output.
- Resolve source, evidence, or baseline issues and rerun `verify-live`.
- Preserve the rejected verification artifact with incident notes.


### Review pack generation for incidents

For every rejected live verification, generate a review pack before closing or
escalating the incident:

```bash
python -m app.cli review-live --verification data/runs/live_verifications/<verification-file>.json
```

The review pack should be attached to the incident note because it preserves:

- the acceptance decision
- failed required checks
- source outcome groups
- warnings
- artifact paths
- archive recommendation

A rejected review pack is still useful evidence. Do not delete it simply because
the run was not accepted.


### Live history shows unreviewed usable runs

Warning signs:

- `live-history` returns `status: attention`.
- `unreviewed_usable_run_count` is greater than zero.
- Latest accepted or accepted-degraded run has no review pack.

Operator action:

- Generate review packs for the unreviewed verification artifacts.
- Confirm each accepted or accepted-degraded run has an operator rationale.
- Do not claim go-live readiness until the history warning is resolved.
