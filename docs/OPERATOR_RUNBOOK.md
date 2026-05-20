# Operator Runbook

## Purpose

This runbook defines how a human operator runs the Convergence Monitor live,
reviews the results, and decides whether a scenario output is accepted,
accepted with degradation, or rejected for investigation.

The operator's job is not to make the system sound certain. The operator's job
is to confirm that the pipeline stayed honest about source availability,
evidence strength, reproducibility, and known gaps.

## Scope

This runbook applies to the current scenario pipeline:

```text
config → ingest → classify → score → alert JSON → status summary → live verification → acceptance gate → review pack
```

It covers operational review only. It does not add dashboards, predictions,
commercial claims, new scenarios, or narrative interpretation.

## Pre-run checks

Run these before relying on any live verification result:

```bash
python -m app.cli validate-config
pytest -q
python -m compileall -q app tests
python -m app.cli status --scenario cbdc_payment_resilience --window 30d
```

Acceptance expectations:

- `validate-config` returns `status: ok`.
- Tests pass in the target environment.
- Compile succeeds.
- `status` returns structured JSON and does not crash.
- Any warnings are reviewed before the live run.

If `ruff` is available in the target environment, run:

```bash
python -m ruff check app tests
```

If `ruff` is unavailable, record that explicitly in the review notes. Do not
treat unavailable lint tooling as a silent pass.

## Live verification command

Run the live verification gate with the scenario and window under review:

```bash
python -m app.cli verify-live --scenario cbdc_payment_resilience --window 30d
```

For constrained environments or smoke checks, a smaller source limit may be used:

```bash
python -m app.cli verify-live --scenario cbdc_payment_resilience --window 30d --limit 1
```

A limit-based smoke check does not replace a full live verification run.

## Machine-readable acceptance gate

After `verify-live` writes a verification artifact, evaluate it with the
read-only acceptance gate:

```bash
python -m app.cli accept-live --verification data/runs/live_verifications/<verification-file>.json
```

Use `--require-baseline` when an established operational scenario must have
stored baseline history before acceptance:

```bash
python -m app.cli accept-live --verification data/runs/live_verifications/<verification-file>.json --require-baseline
```

The command returns one decision:

- `accepted`
- `accepted_degraded`
- `rejected`

The command does not fetch sources, generate score JSON, generate alert JSON,
update baselines, or mutate source health. It only evaluates the verification
artifact and reports required/advisory checks.

## Deterministic review pack

After evaluating acceptance, create an operator review pack:

```bash
python -m app.cli review-live --verification data/runs/live_verifications/<verification-file>.json
```

Use `--require-baseline` when the review pack should reject runs without a stored
baseline:

```bash
python -m app.cli review-live --verification data/runs/live_verifications/<verification-file>.json --require-baseline
```

The review pack groups source outcomes, embeds the acceptance-gate decision,
lists artifact paths, records warnings, and provides archive instructions. It is
also read-only: it does not fetch sources, generate scores, generate alerts,
update baselines, or mutate source health.


## Review the live verification result

Inspect the command output and the written verification artifact.

Required review fields:

- `status`
- `sources_total`
- `sources_ok`
- `sources_empty`
- `sources_timeout`
- `sources_parse_error`
- `sources_network_error`
- `sources_disabled`
- `documents_ingested`
- `documents_classified`
- `score_generated`
- `alert_generated`
- `baseline_available`
- `confidence`
- `warnings`
- `verification_path`
- `run_snapshot_path`

## Decision states

### Accepted

Use `accepted` when:

- The command exits successfully.
- The result status is `ok`.
- At least one relevant document was ingested and classified.
- Score generation completed.
- Alert generation completed when the score warrants an alert artifact.
- Warnings are empty or informational only.
- Source health is not materially degraded.
- Evidence is directly related to the configured scenario.

### Accepted with degradation

Use `accepted_degraded` when:

- The command completes with structured output.
- One or more sources fail, time out, are empty, or are disabled.
- Enough sources and documents remain to support the score honestly.
- The output clearly reports the degraded source state.
- The alert body remains evidence-backed and reproducible.
- The operator records the degraded source names and reason.

A degraded run must not be described as fully healthy.

### Rejected

Use `rejected` when any of the following are true:

- No live documents are ingested.
- All sources fail, time out, or return parse/network errors.
- The result status is `error`.
- Score generation is false because evidence was unavailable.
- Alert generation occurs without supporting evidence.
- Alert JSON changes across reruns when the raw evidence is unchanged.
- Evidence is off-topic or dominated by known false-positive patterns.
- Required artifacts are missing, malformed, or not written.
- The operator cannot explain the warnings.

A rejected run may still be technically correct if it honestly reports failure.
Do not suppress or reinterpret a rejected live result.

## Evidence review

For every accepted or accepted-degraded run, inspect the evidence that flowed into
the alert. Confirm that:

- Evidence text is scenario-relevant.
- Source category coverage is clear.
- Excluded evidence is not needed to support the conclusion.
- False positives remain excluded.
- Weak evidence is not described as strong convergence.
- Confidence is consistent with the evidence count and source diversity.

## Reproducibility review

When the same raw evidence is rerun, the stable alert body should remain
unchanged. Runtime timestamps may change in run snapshots and classified JSONL,
but not inside the stable alert body.

Expected behavior:

```text
same raw evidence
→ classify
→ score
→ alert
→ rerun
→ classify
→ score
→ alert

alert JSON equal: true
classified JSONL equal: false
```

If the alert body changes only because runtime metadata changed, reject the run
and investigate deterministic alert anchoring.

## Baseline review

Baseline comparison is advisory and conservative. It must not alter the
deterministic convergence score.

Review baseline state as follows:

- `baseline_unavailable`: acceptable for a new scenario, but do not claim trend.
- `available`: trend comparison may be reported if observation count is adequate.
- Duplicate baseline observations: should be suppressed.
- Generated baseline files are runtime artifacts and should not be packaged.

## Archiving

For each reviewed live verification, archive or reference:

- command used
- exit code
- verification artifact path
- run snapshot path
- score artifact path, if generated
- alert artifact path, if generated
- baseline state at the time of review
- operator decision: `accepted`, `accepted_degraded`, or `rejected`
- short rationale
- follow-up incident or source ticket, if needed

Runtime artifacts should stay outside release packages unless explicitly included
as documentation examples.

## Operator rule

The system is allowed to say "no reliable live evidence." It is not allowed to
turn missing, failed, or weak evidence into certainty.


## Live history review

After several live verification runs have been accepted, degraded, rejected, or
reviewed, summarize the recent operational state:

```bash
python -m app.cli live-history --scenario cbdc_payment_resilience --runs-dir data/runs
```

Use this command to confirm:

- the latest live run decision
- whether accepted or accepted-degraded runs have review packs
- whether the current usable-run streak is improving
- whether the latest run is rejected
- whether any usable live runs still need operator review

`live-history` is read-only. It must not be used as a replacement for evidence
review; it only shows whether repeated live runs are ready for review,
acceptance, or incident follow-up.
