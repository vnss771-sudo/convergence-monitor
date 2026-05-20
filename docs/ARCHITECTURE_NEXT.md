# Architecture Next

## Current shape

Convergence Monitor is a deterministic public-document convergence monitor. The current public repository exposes these core areas:

- `app/ingestion`
- `app/classification`
- `app/scoring`
- `app/alerts`
- `app/runs`
- `app/live_verification.py`
- `app/live_history.py`
- `app/status.py`
- `app/cli.py`

The next architecture target is not a rewrite. It is a staged hardening path.

## Target package layout

```text
convergence_monitor/
  __init__.py
  cli.py
  commands/
    __init__.py
    alert.py
    classify.py
    config.py
    ingest.py
    live.py
    runs.py
    score.py
    status.py
  config/
    __init__.py
    loader.py
    models.py
  ingestion/
  classification/
  scoring/
  alerts/
  runs/
  live/
  storage/
  time.py
  errors.py
```

## Boundaries

### CLI layer

The CLI layer should parse arguments, call application services, and render JSON/text. It should not own scoring, ingestion, source health, or evidence semantics.

### Domain layer

The domain layer owns deterministic behavior:

- scenario config validation
- source config validation
- classifier rules
- score components
- evidence eligibility
- alert output schema
- baseline comparison

### Storage layer

The storage layer owns paths, JSONL read/write, snapshots, dedupe, and atomic writes.

### Live layer

The live layer owns network-facing checks and must remain isolated from deterministic fixture tests.

## Refactor sequence

1. Add `app/commands/` and move one command at a time.
2. Keep `python -m app.cli ...` stable during the split.
3. Add tests around CLI JSON output before each move.
4. Rename `app` to `convergence_monitor` only after command split stabilises.
5. Keep compatibility shim if needed:

```python
# app/cli.py
from convergence_monitor.cli import app

if __name__ == "__main__":
    app()
```

## Non-negotiable guardrails

- No hidden-intent language.
- No causation claims.
- No market prediction claims.
- No live-source availability affecting deterministic convergence score by itself.
- No generated runtime artifacts in source releases.
