# CLI Split Migration

## Why

`app/cli.py` is the public entrypoint, but it should not own all command behavior.
A thin router makes the CLI safer to grow and easier to test.

## Command module mapping

| Current function | New module |
|---|---|
| `validate_config` | `app/commands/config.py` |
| `_raw_path`, `_ingest_one_source`, `ingest` | `app/commands/ingest.py` |
| `classify` | `app/commands/classify.py` |
| `score` | `app/commands/score.py` |
| `show_baseline`, `update_baseline` | `app/commands/baselines.py` |
| `verify_live`, `accept_live`, `review_live`, `live_history` | `app/commands/live.py` |
| `scenario_status` | `app/commands/status.py` |
| `alert` | `app/commands/alerts.py` |
| `list_runs`, `source_health` | `app/commands/runs.py` |

## Procedure

```bash
python tools/split_cli_commands.py --repo-dir "$PWD" --dry-run
python tools/split_cli_commands.py --repo-dir "$PWD" --apply
python -m compileall -q app tests tools
pytest -q
ruff check .
```

## Rollback

The splitter writes `app/cli.py.pre-split.bak`.

```bash
mv app/cli.py.pre-split.bak app/cli.py
rm -rf app/commands
```

## Acceptance

- `python -m app.cli --help` works.
- `python -m app.cli validate-config` emits JSON with `status: ok`.
- `python -m app.cli runs --help` includes `list` and `health`.
- Existing tests pass.
