# Contributing

Thanks for contributing to Convergence Monitor. This project is a deterministic
public-document convergence monitor, and **determinism is a core value**: the
golden / byte-stability tests must stay green. Treat any change to scoring,
serialization, or output formatting as potentially breaking and verify the
golden tests locally before opening a PR.

## Prerequisites

- Python 3.11 or newer.

## Setup

```bash
pip install -e '.[dev]'
```

`feedparser` is **not** installed by default. It is an optional `[parse]` extra
because its transitive `sgmllib3k` sdist dependency fails to build under modern
setuptools; ingestion falls back to a stdlib RSS/Atom parser when it is absent.
Install the richer parser only if you need it:

```bash
pip install -e '.[parse]'
```

## Local verification

Run these before opening a PR:

```bash
python -m pytest
ruff check .
python -m compileall -q app tests
python -m app.cli validate-config
```

> NOTE: invoke pytest as `python -m pytest`. The bare `pytest` shim may be
> broken in some environments; `python -m pytest` is the reliable form.

A `Makefile` wraps these commands: `make check` runs lint + test + compile +
validate. See also `make install`, `make test`, `make lint`, `make fix`,
`make compile`, `make validate`, and `make clean`.

Pre-commit hooks are available; install them with `pre-commit install` (see
`.pre-commit-config.yaml`).

## Branch and commit conventions

- Work on a feature branch; do not commit directly to the default branch.
- Use Conventional Commit prefixes (`feat:`, `fix:`, `chore:`, `refactor:`,
  `test:`, `docs:`) as reflected in the existing git history.
- Keep commits focused and factual; reference the related PR/issue.

## Roadmap

See `docs/reports/UNICORN_BUILD_PLAN.md` for the roadmap and `docs/README.md`
for the full documentation index.
