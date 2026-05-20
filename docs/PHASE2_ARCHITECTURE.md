# Phase 2 Architecture

## Target shape

```text
convergence-monitor/
  app/                         # current package; rename later
    cli.py                     # thin Typer router only
    commands/
      alerts.py
      baselines.py
      classify.py
      config.py
      ingest.py
      live.py
      runs.py
      score.py
      status.py
    ingestion/
    classification/
    scoring/
    alerts/
    runs/
  config/
  docs/
  scripts/
  tests/
  tools/
```

## Product principles

1. Public-document convergence only.
2. Deterministic output first.
3. No hidden intent, causation, coordination, prediction, or inevitability claims.
4. Runtime artifacts are not source.
5. CLI commands are product contracts.
6. Live verification is operational evidence, not scoring evidence by itself.

## Phase 2 boundaries

Phase 2 hardens the engineering surface. It does not expand the domain model.

Included:
- CLI command modularization.
- Package rename readiness.
- Repo hygiene enforcement.
- Operator fixtures.
- Contract tests.
- Audit tools.

Not included:
- dashboards;
- extra scenarios;
- market feeds;
- narrative inference;
- speculative analytics.
