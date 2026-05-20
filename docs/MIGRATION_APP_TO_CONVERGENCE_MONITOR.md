# Migration: `app` to `convergence_monitor`

## Why

`app` is generic and collision-prone. `convergence_monitor` is clearer for imports, stack traces, packaging, and future distribution.

## Safe migration path

1. Finish repo hygiene and release hardening first.
2. Create a dedicated branch.
3. Run:

```bash
python tools/rename_app_package.py --root "$PWD"
```

4. Review dry-run output.
5. Execute:

```bash
python tools/rename_app_package.py --root "$PWD" --execute
```

6. Validate:

```bash
python -m convergence_monitor.cli validate-config
python -m compileall -q convergence_monitor tests
pytest -q
ruff check .
```

## Compatibility shim

Keep temporary compatibility if needed:

```python
# app/cli.py
from convergence_monitor.cli import app

if __name__ == "__main__":
    app()
```

Remove the shim in the next minor release.
