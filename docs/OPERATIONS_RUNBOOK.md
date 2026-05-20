# Operations Runbook

## Local verification

```bash
python -m app.cli validate-config
python -m app.cli ingest --source all --limit 10
python -m app.cli classify --scenario cbdc_payment_resilience
python -m app.cli score --scenario cbdc_payment_resilience --window 30d
python -m app.cli alert --scenario cbdc_payment_resilience --window 30d --json
python -m app.cli runs health
```

## Live verification

```bash
python -m app.cli verify-live --scenario cbdc_payment_resilience --window 30d
python -m app.cli live-history --scenario cbdc_payment_resilience
```

## Expected degradation model

Single-source failures should be visible and structured. Multi-source failures may produce degraded status. Degraded source availability is an operations signal, not a convergence signal by itself.

## Evidence review

Before publishing external conclusions, review:

- matched terms
- relevance label
- source category
- source health
- duplicate suppression
- excluded and irrelevant documents
- alert limitations

## Incident response

If a feed changes format or starts returning bad payloads:

1. Run `verify-live`.
2. Inspect source health.
3. Add or adjust fallback URL config.
4. Add regression fixture.
5. Keep default tests deterministic.
