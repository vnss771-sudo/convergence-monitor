# Package Rename Migration

## Goal

Rename the import package from generic `app` to `convergence_monitor`.

The PyPI/project name can remain `convergence-monitor`; the import package should be specific.

## Recommended sequence

1. Land repo hygiene.
2. Land CLI split.
3. Run full tests.
4. Rename package in a dedicated PR.
5. Keep a temporary compatibility shim for one release.

## Commands

```bash
python tools/rename_app_package.py --repo-dir "$PWD" --dry-run
python tools/rename_app_package.py --repo-dir "$PWD" --apply --compat-shim
python -m compileall -q convergence_monitor app tests tools
pytest -q
ruff check .
```

## After rename

Update operator docs from:

```bash
python -m app.cli validate-config
```

to:

```bash
python -m convergence_monitor.cli validate-config
```

Keep `python -m app.cli` working through the shim until the next breaking release.
