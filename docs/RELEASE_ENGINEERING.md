# Release Engineering

## Release goals

A source release must be:

- pinned to a tag or full commit SHA
- reproducible from tracked files
- free of runtime evidence artifacts
- accompanied by SHA-256 checksums
- validated by config, compile, lint, and tests

## Build from existing repo

```bash
bash scripts/release/make_zip_from_existing_repo.sh \
  --repo-dir "$PWD" \
  --ref v0.1.0-mvp-rc \
  --expected-commit <full-sha> \
  --output dist/convergence-monitor-source.zip
```

## Build from fresh clone

```bash
bash scripts/release/build_pinned_source_zip.sh \
  --ref v0.1.0-mvp-rc \
  --expected-commit <full-sha> \
  --output dist/convergence-monitor-source.zip
```

## Release checklist

```bash
git status --short
python -m app.cli validate-config
python -m compileall -q app tests
pytest -q
ruff check .
python tools/repo_audit.py --root . --markdown
bash scripts/clean_runtime_artifacts.sh --dry-run
```

## Tagging

```bash
git tag -a v0.1.1 -m "v0.1.1"
git push origin v0.1.1
```

## Artifact policy

Do not commit:

- `data/raw/`
- `data/processed/`
- `data/runs/`
- live proof reports
- live proof zip files
- local coverage/cache directories
- generated source zips
