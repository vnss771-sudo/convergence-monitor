# Operations Runbook — Phase 2

## Daily local check

```bash
python -m app.cli validate-config
python -m app.cli ingest --source all --limit 10
python -m app.cli classify --scenario cbdc_payment_resilience
python -m app.cli score --scenario cbdc_payment_resilience --window 30d
python -m app.cli alert --scenario cbdc_payment_resilience --window 30d --json
python -m app.cli status --scenario cbdc_payment_resilience --window 30d
```

## Live verification check

```bash
python -m app.cli verify-live --scenario cbdc_payment_resilience --window 30d --limit 10
python -m app.cli live-history --scenario cbdc_payment_resilience
```

## Demo without network

```bash
python tools/generate_operator_fixture.py --output-dir data/raw
python -m app.cli classify --scenario cbdc_payment_resilience
python -m app.cli score --scenario cbdc_payment_resilience --window 30d
python -m app.cli alert --scenario cbdc_payment_resilience --window 30d --json
```

## Red flags

- A root-level `*.zip` appears in `git status`.
- `data/raw`, `data/processed`, or `data/runs` appears in tracked files.
- Alert text implies intent, causation, coordination, prediction, or inevitability.
- Scoring changes without fixture deltas.
- CLI output stops being valid JSON for JSON-contract commands.
