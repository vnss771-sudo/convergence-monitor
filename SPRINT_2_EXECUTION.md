# Sprint 2 Execution Plan — Reliability, Dedupe, and False-Positive Control

## Objective

Make the same alert reproducible, robust, and resistant to false positives across repeated runs.

Sprint 2 is not a feature sprint. It is a trust sprint.

The product should earn trust before it earns a UI.

---

## PR 6 — Run Snapshots + Append/Dedupe Ingestion

### Goal

Each ingest, classify, score, and alert run should be traceable, repeatable, and should not corrupt or inflate previous runs.

### Build

- Append-safe raw JSONL ingestion
- Dedupe by `document_id`
- Dedupe by `content_hash`
- Optional `--replace` flag for controlled rebuilds
- Run snapshots under `data/runs/`
- `python -m app.cli runs list`

### Acceptance

```bash
python -m app.cli ingest --source bis --limit 10
python -m app.cli ingest --source bis --limit 10
python -m app.cli runs list
```

Expected second-run behavior:

```json
{
  "status": "ok",
  "source_id": "bis",
  "fetched": 10,
  "saved": 0,
  "skipped_existing": 10,
  "raw_path": "data/raw/bis.jsonl"
}
```

### Traceability Requirements

Each run snapshot should include:

- `run_id`
- `operation`
- `subject`
- `status`
- `created_at`
- config hashes
- parameters
- inputs
- outputs
- counts

### Guardrails

Still forbidden:

- dashboard
- extra scenarios
- market prediction
- price forecasting
- speculative narrative reports
- hidden-intent language

### Review Question

Can this thing run repeatedly without lying to itself?


---

## PR 7 — Source Failure Handling + Degraded Run Reporting

### Objective

A broken source should not make the system unreliable or ambiguous.

The system must fail clearly without hiding, exaggerating, or corrupting the signal.

### Built

- Structured source error records
- Source health status storage
- Graceful ingest failure snapshots
- Degraded status support for multi-source ingest
- Clear source-attempt, success, and failure counts
- `runs health` CLI

### Acceptance

```bash
python -m app.cli ingest --source broken_fixture --limit 10
python -m app.cli runs list
```

Failure output shape:

```json
{
  "status": "error",
  "operation": "ingest",
  "source_id": "broken_fixture",
  "error": {
    "type": "ingestion_error",
    "message": "..."
  }
}
```

Multi-source degraded output shape:

```json
{
  "status": "degraded",
  "sources_attempted": 5,
  "sources_succeeded": 4,
  "sources_failed": 1
}
```

### Guardrail

No dashboard, no new scenarios, no market prediction, and no speculative interpretation.


---

## PR 8 — Evidence Quality Control + False-Positive Fixtures

### Objective

Prevent weak keyword matches from becoming trusted evidence.

### Built

- Evidence eligibility rules
- Evidence quality flags
- Duplicate evidence suppression by content hash and URL
- Incidental evidence cap
- False-positive fixture documents
- Near-miss / overbroad-match tests
- Alert evidence filtering tightened

### Acceptance

```bash
pytest -q
python -m app.cli classify --scenario cbdc_payment_resilience
python -m app.cli score --scenario cbdc_payment_resilience --window 30d
python -m app.cli alert --scenario cbdc_payment_resilience --window 30d --json
```

Expected behavior:

- central evidence remains eligible
- incidental evidence is limited
- excluded documents never enter evidence
- irrelevant documents never enter evidence
- duplicate evidence stays suppressed
- false-positive fixtures do not inflate the alert

### Guardrail

No scoring redesign, no dashboard, no extra scenario, no speculative interpretation.

### Review Question

Can the system stop weak matches from pretending to be signal?

---

## PR 9 — Baseline Storage

### Objective

Allow the system to compare current signal intensity against stored historical observations without creating false certainty.

### Built

- `app/scoring/baselines.py`
- Scenario baseline JSON storage under `data/baselines/`
- `BaselineRecord`
- `BaselineComparison`
- Explicit `baseline_unavailable` state
- `python -m app.cli baselines show --scenario cbdc_payment_resilience`
- `python -m app.cli baselines update --scenario cbdc_payment_resilience`
- Optional `python -m app.cli score --scenario cbdc_payment_resilience --window 30d --update-baseline`
- Duplicate baseline observation suppression
- Conservative baseline metadata in score JSON
- Tests for missing, available, duplicate, CLI update, and score integration

### Guardrail

Baseline comparison is descriptive only. It does not change the deterministic convergence score and does not infer trend, causation, intent, coordination, or future events.

### Review Question

Can the system compare current signal intensity to stored history without creating false certainty?

---

## PR 10 — Deterministic Alert Reproducibility + Golden Alert Tests

### Objective

The same raw evidence should produce the same stable alert JSON across repeated full pipeline runs.

Runtime timestamps belong in run snapshots, not inside the stable alert body.

### Built

- Alert `generated_at` no longer depends on runtime `classified_at`
- Stable alert timestamp fallback order:
  1. latest `published_at` from included evidence
  2. latest `published_at` from classified documents
  3. deterministic score anchor when exposed by the score schema
  4. `1970-01-01T00:00:00Z`
- UTC canonicalization for stable alert timestamps
- Golden alert fixture:
  - `tests/fixtures/golden_alert_cbdc_payment_resilience.json`
- Reproducibility tests proving alert JSON is unchanged when only `classified_at` changes
- Full CLI rerun test proving classify → score → alert can be repeated with identical saved alert JSON

### Acceptance

```bash
python -m app.cli validate-config
pytest -q
python -m compileall -q app tests
```

Additional behavior verified:

```bash
same raw document
→ classify
→ score
→ alert
→ classify again with a new runtime classified_at
→ score
→ alert
```

Expected result:

- saved alert JSON is identical
- `generated_at` remains anchored to public evidence dates
- run snapshots may still contain runtime timestamps

### Guardrail

No scoring redesign, no dashboard, no new scenario, no predictive narrative, and no runtime timestamp inside the stable alert body.

### Review Question

Can the same raw evidence produce the same alert JSON across repeated full pipeline runs?



---

## PR 11 — Scenario Status Summary

### Objective

Give an operator one read-only command that summarizes whether a scenario pipeline is healthy, reproducible, and evidence-backed without manually opening score JSON, alert JSON, baseline JSON, source health, and run snapshots separately.

### Built

- `app/status.py`
- `python -m app.cli status --scenario cbdc_payment_resilience --window 30d`
- Score artifact summary:
  - score existence
  - convergence score
  - confidence
  - active source categories
  - documents considered
- Alert artifact summary:
  - alert existence
  - stable `generated_at`
  - evidence count
- Baseline summary:
  - baseline status
  - observation count
  - current-score comparison when score JSON exists
- Source-health summary:
  - total enabled sources
  - sources ok
  - sources error
  - sources unknown
  - overall health
- Latest run status for:
  - ingest
  - classify
  - score
  - alert
- Explicit warnings for missing or invalid artifacts and missing/error run snapshots
- Tests for complete status output, missing-artifact output, and unknown-scenario failure

### Acceptance

```bash
python -m app.cli validate-config
pytest -q
python -m compileall -q app tests
```

### Guardrail

The status command is read-only. It does not ingest, classify, score, alert, update baselines, generate narratives, add dashboards, introduce predictions, or create new scenarios.

### Review Question

Can an operator quickly understand whether this scenario pipeline is healthy, reproducible, and evidence-backed?
