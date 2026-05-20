# PR-Ready Commit Series

## PR 1 — Repo hygiene gate

```text
chore(repo): add phase 2 hygiene audit and artifact contract tests
```

Files:
- `tools/unicorn_repo_audit.py`
- `tests/phase2/test_repo_hygiene_phase2.py`
- docs updates

Acceptance:
- `python tools/unicorn_repo_audit.py --root "$PWD" --markdown`
- `pytest -q tests/phase2/test_repo_hygiene_phase2.py`

## PR 2 — CLI contract tests

```text
test(cli): add phase 2 CLI contract coverage
```

Files:
- `tests/phase2/test_cli_contract_phase2.py`

Acceptance:
- `pytest -q tests/phase2/test_cli_contract_phase2.py`

## PR 3 — Split monolithic CLI

```text
refactor(cli): split Typer commands into command modules
```

Commands:

```bash
python tools/split_cli_commands.py --repo-dir "$PWD" --apply
python -m compileall -q app tests tools
pytest -q
ruff check .
```

Acceptance:
- existing CLI commands keep names and JSON shapes;
- `app/cli.py` is router-only;
- `app/commands/` owns command handlers.

## PR 4 — Operator fixture

```text
test(fixtures): add deterministic operator demo fixture generator
```

Files:
- `tools/generate_operator_fixture.py`
- docs

Acceptance:
- local no-network demo can classify, score, and alert.

## PR 5 — Optional package rename

```text
refactor(package): rename app package to convergence_monitor
```

Commands:

```bash
python tools/rename_app_package.py --repo-dir "$PWD" --apply --compat-shim
python -m compileall -q convergence_monitor app tests tools
pytest -q
ruff check .
```

Acceptance:
- `python -m convergence_monitor.cli validate-config` works;
- temporary `python -m app.cli validate-config` shim works.
