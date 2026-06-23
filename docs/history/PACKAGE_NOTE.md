# Convergence Monitor — Technical MVP Package

Package date: 2026-05-19

This archive contains the latest accepted technical MVP state based on Sprint 3 / PR 16.

Accepted build state:

- Sprint 1: config → ingest → classify → score → alert JSON
- Sprint 2: repeatable runs, dedupe, failure handling, evidence control, false-positive fixtures, baseline storage, deterministic alerts, status summary
- Sprint 3: live verification harness, operator runbook, machine-readable acceptance gate, live review packs, live history summary

Primary live-proof command:

```bash
python -m app.cli verify-live --scenario cbdc_payment_resilience --window 30d --limit 5
```

Then run:

```bash
python -m app.cli accept-live --verification <verification_artifact>
python -m app.cli review-live --verification <verification_artifact>
python -m app.cli live-history --scenario cbdc_payment_resilience
```

Known remaining gate:

- Run repeated live-source verification in a real networked environment.
- Run `python -m ruff check app tests` in an environment with ruff installed.

This package is not a dashboard or SaaS product yet. It is an evidence-backed technical MVP entering live proof.
