# Sprint 3 Execution Notes

Sprint 3 focuses on live verification and operational hardening. It does not add
dashboards, predictions, new scenarios, or narrative interpretation.

---

## PR 12 — Live Source Verification Harness

### Objective

Answer whether the Convergence Monitor can run against real configured public
sources, report source messiness honestly, and preserve deterministic downstream
score/alert behavior.

### Built

- `app/live_verification.py`
- `python -m app.cli verify-live --scenario cbdc_payment_resilience --window 30d`
- Per-source live outcome vocabulary:
  - `ok`
  - `empty`
  - `timeout`
  - `parse_error`
  - `network_error`
  - `disabled`
- Operator JSON summary with:
  - source counts by outcome
  - documents ingested from the live pass
  - documents classified
  - score generation status
  - alert generation status
  - baseline availability
  - confidence when a score is generated
  - explicit warnings
- Runtime verification artifact under:
  - `data/runs/live_verifications/`
- `verify_live` run snapshot under:
  - `data/runs/`
- Source-health updates for live checks
- Downstream classify, score, and alert generation only when live documents are available
- Tests for:
  - mixed live source outcomes
  - all-source failure without stable outputs
  - disabled source handling
  - stable alert JSON across repeated live verification runs with different runtime classification timestamps

### Command

```bash
python -m app.cli verify-live --scenario cbdc_payment_resilience --window 30d
```

### Expected Output Shape

```json
{
  "status": "degraded",
  "operation": "verify_live",
  "scenario_id": "cbdc_payment_resilience",
  "scenario_name": "Cross-border CBDC and payment-system resilience convergence",
  "window_days": 30,
  "sources_total": 5,
  "sources_ok": 4,
  "sources_empty": 0,
  "sources_timeout": 0,
  "sources_parse_error": 0,
  "sources_network_error": 1,
  "sources_disabled": 0,
  "documents_ingested": 12,
  "documents_saved": 12,
  "documents_classified": 12,
  "score_generated": true,
  "alert_generated": true,
  "baseline_available": true,
  "confidence": "medium",
  "warnings": [
    "source_network_error:example_source"
  ]
}
```

### Acceptance

```bash
python -m app.cli validate-config
pytest -q
python -m compileall -q app tests
python -m app.cli status --scenario cbdc_payment_resilience --window 30d
```

Manual live check:

```bash
python -m app.cli verify-live --scenario cbdc_payment_resilience --window 30d
```

### Guardrail

PR 12 does not alter scoring rules, weaken deterministic alert tests, infer
convergence from source availability alone, update baselines implicitly, add a
dashboard, add scenarios, or introduce predictions.

### Review Question

Can this system survive real-world source messiness while remaining honest about
evidence quality?

## PR 13 — Operator Runbook + Live Acceptance Gate

### Objective

Answer whether an operator can safely run the system live and know what to do
when sources fail, alerts look weak, or evidence is questionable.

### Built

- `docs/OPERATOR_RUNBOOK.md`
- `docs/LIVE_ACCEPTANCE_CHECKLIST.md`
- `docs/INCIDENT_RESPONSE.md`
- Example live verification outputs:
  - `docs/examples/verification_accepted.json`
  - `docs/examples/verification_degraded.json`
  - `docs/examples/verification_error.json`
- Documentation tests for:
  - required operator docs
  - required operational commands
  - required decision states
  - JSON validity and status consistency of example verification outputs

### Acceptance Gate

Static checks:

```bash
python -m app.cli validate-config
pytest -q
python -m compileall -q app tests
python -m app.cli status --scenario cbdc_payment_resilience --window 30d
```

Live check:

```bash
python -m app.cli verify-live --scenario cbdc_payment_resilience --window 30d
```

Operator decision states:

- `accepted`
- `accepted_degraded`
- `rejected`

### Go-live Criteria

The technical MVP can be considered live-ready when:

- static checks pass in the target environment
- real live verification runs produce structured artifacts
- source failures are explicit and understandable
- at least one accepted or accepted-degraded run contains real public-source evidence
- rejected runs have clear incident notes
- stable alert JSON remains reproducible for unchanged evidence
- baseline state is explicit and does not alter deterministic score
- an operator can explain the latest status output without inspecting code

### Guardrail

PR 13 is documentation and acceptance-gate hardening only. It does not add a
dashboard, predictions, new scenarios, narrative interpretation, source changes,
or scoring-rule changes.

### Review Question

Can an operator safely run this system live and know what to do when sources
fail, alerts look weak, or evidence is questionable?


## PR 14 — Machine-Readable Live Acceptance Gate

### Objective

Turn the PR 13 operator checklist into a read-only CLI gate that evaluates one
`verify-live` artifact and returns an auditable decision.

### Built

- `app/live_acceptance.py`
- `python -m app.cli accept-live --verification <verification-artifact>`
- Optional stricter baseline gate:
  - `python -m app.cli accept-live --verification <verification-artifact> --require-baseline`
- Acceptance decisions:
  - `accepted`
  - `accepted_degraded`
  - `rejected`
- Required checks for:
  - artifact operation
  - usable verification status
  - live document ingestion
  - live document classification
  - score generation
  - alert generation
  - at least one usable source
  - internally consistent source counts
  - absence of critical warnings
- Advisory checks for:
  - source degradation
  - degraded verification status
  - baseline availability
  - non-empty warnings
- Tests for:
  - clean accepted artifact
  - degraded accepted artifact
  - rejected error artifact
  - optional baseline requirement
  - inconsistent source counts

### Command

```bash
python -m app.cli accept-live --verification docs/examples/verification_accepted.json
```

### Expected Output Shape

```json
{
  "status": "ok",
  "operation": "accept_live",
  "decision": "accepted",
  "verification_path": "docs/examples/verification_accepted.json",
  "scenario_id": "cbdc_payment_resilience",
  "window_days": 30,
  "verification_status": "ok",
  "documents_ingested": 14,
  "documents_classified": 14,
  "score_generated": true,
  "alert_generated": true,
  "baseline_available": true,
  "sources_total": 5,
  "sources_ok": 5,
  "source_failure_count": 0,
  "warnings": [],
  "checks": [],
  "operator_actions": []
}
```

### Acceptance Gate

```bash
python -m app.cli validate-config
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
python -m compileall -q app tests
python -m app.cli status --scenario cbdc_payment_resilience --window 30d
python -m app.cli accept-live --verification docs/examples/verification_accepted.json
python -m app.cli accept-live --verification docs/examples/verification_degraded.json
python -m app.cli accept-live --verification docs/examples/verification_error.json
```

The first two acceptance examples exit zero. The error example exits non-zero
with `decision: rejected`.

### Guardrail

PR 14 is read-only acceptance hardening. It does not fetch sources, generate
scores, generate alerts, update baselines, change source configuration, add
scenarios, add dashboards, add predictions, or alter scoring rules.

### Review Question

Can a live verification artifact be accepted, degraded, or rejected consistently
without relying on undocumented human judgment?


## PR 15 — Live Evidence Review Pack

### Objective

Create a deterministic, read-only review artifact that an operator can archive
or attach to an incident after running the live acceptance gate.

### Built

- `app/live_review.py`
- `python -m app.cli review-live --verification <verification-artifact>`
- Optional stricter baseline review:
  - `python -m app.cli review-live --verification <verification-artifact> --require-baseline`
- Optional output directory:
  - `--output-dir data/runs/live_reviews`
- Review pack sections:
  - acceptance decision and checks from the PR 14 gate
  - scenario and live-verification summary
  - grouped source outcomes
  - raw, verification, run-snapshot, score, alert, and classified artifact paths when available
  - warnings
  - operator review questions
  - archive recommendation

### Command

```bash
python -m app.cli review-live --verification docs/examples/verification_accepted.json
```

### Expected Output Shape

```json
{
  "status": "ok",
  "operation": "live_review_pack",
  "decision": "accepted",
  "generated_at": "2026-05-19T00:00:00Z",
  "summary": {
    "scenario_id": "cbdc_payment_resilience",
    "verification_status": "ok",
    "documents_ingested": 14,
    "score_generated": true,
    "alert_generated": true
  },
  "source_summary": {
    "sources_total": 5,
    "sources_ok": 5,
    "groups": {}
  },
  "artifact_paths": {
    "verification_path": "docs/examples/verification_accepted.json",
    "run_snapshot_path": "data/runs/verify_live_cbdc_payment_resilience_20260519T000000Z_30d.json"
  },
  "archive_recommendation": {
    "action": "archive_as_accepted"
  },
  "review_pack_path": "data/runs/live_reviews/20260519T000000Z_live_review_cbdc_payment_resilience_30d.json"
}
```

### Acceptance Gate

```bash
python -m app.cli validate-config
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
python -m compileall -q app tests
python -m app.cli status --scenario cbdc_payment_resilience --window 30d
python -m app.cli review-live --verification docs/examples/verification_accepted.json --output-dir /tmp/live_reviews
python -m app.cli review-live --verification docs/examples/verification_degraded.json --output-dir /tmp/live_reviews
python -m app.cli review-live --verification docs/examples/verification_error.json --output-dir /tmp/live_reviews
```

Unlike `accept-live`, `review-live` writes a pack for rejected runs too, because
rejected runs still need to be archived as incident evidence.

### Guardrail

PR 15 is read-only review hardening. It does not fetch sources, generate scores,
generate alerts, update baselines, change source configuration, add scenarios,
add dashboards, add predictions, or alter scoring rules.

### Review Question

Can an operator produce a consistent evidence package for accepted, degraded,
and rejected live runs without relying on ad hoc notes?


## PR 16 — Live Run History Summary

### Objective

Give operators a read-only view across repeated live verification runs so they
can see whether the latest state is review-ready, degraded, or blocked without
opening every verification and review artifact manually.

### Built

- `app/live_history.py`
- `python -m app.cli live-history --scenario cbdc_payment_resilience`
- Optional stricter baseline evaluation:
  - `--require-baseline`
- Optional artifact location:
  - `--runs-dir data/runs`
- Optional recent-run limit:
  - `--limit 10`
- History summary sections:
  - latest live run
  - acceptance decision counts
  - verification status counts
  - review-pack coverage
  - current usable-run streak
  - unreviewed usable-run warnings
  - rejected latest-run warnings

### Command

```bash
python -m app.cli live-history --scenario cbdc_payment_resilience --runs-dir data/runs
```

### Expected Output Shape

```json
{
  "status": "ok",
  "operation": "live_history",
  "scenario_id": "cbdc_payment_resilience",
  "runs_available": 3,
  "runs_considered": 3,
  "review_packs_found": 2,
  "usable_run_count": 2,
  "rejected_run_count": 1,
  "unreviewed_usable_run_count": 0,
  "current_usable_streak": 2,
  "decision_counts": {
    "accepted": 1,
    "accepted_degraded": 1,
    "rejected": 1
  },
  "latest": {
    "decision": "accepted",
    "verification_status": "ok",
    "review_pack_exists": true
  },
  "warnings": []
}
```

### Acceptance Gate

```bash
python -m app.cli validate-config
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
python -m compileall -q app tests
python -m app.cli status --scenario cbdc_payment_resilience --window 30d
python -m app.cli live-history --scenario cbdc_payment_resilience
```

### Guardrail

PR 16 is read-only operational history. It does not fetch sources, generate
scores, generate alerts, update baselines, change source configuration, add
scenarios, add dashboards, add predictions, or alter scoring rules.

### Review Question

Can an operator understand repeated live-verification readiness and review
coverage without manually opening every artifact?
