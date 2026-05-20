# Termux Support

## Supported path

```bash
pkg update
pkg install python git
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m app.cli validate-config
pytest -q
```

## Ruff caveat

If Ruff wheels are unavailable for the Termux environment, keep Ruff enforced in Linux/GitHub Actions and document the Termux skip clearly.

## Mobile-safe practices

- Use pinned release tags.
- Avoid background daemons unless explicitly needed.
- Keep generated data outside source archives.
- Prefer JSON output for copy/export workflows.
