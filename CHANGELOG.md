# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Code council report and a companion build plan/roadmap (`docs/reports/CODE_COUNCIL_REPORT.md`, `docs/reports/UNICORN_BUILD_PLAN.md`).
- Customer-facing lead section in the README describing what the project is, who it's for, and its honest current scope.
- Pinned `constraints.txt` for reproducible installs; CI and release now install with `-c constraints.txt`.
- `app/persistence.py`: atomic JSON writes (temp file + `os.replace` + `fsync`), a single canonical-JSON contract, a shared `utc_now_iso()`, and `read_json`/`iter_jsonl` helpers.
- Onboarding scaffolding: `CONTRIBUTING.md`, `Makefile`, `.pre-commit-config.yaml`, and a `docs/README.md` documentation index.
- Console entry point `convergence-monitor` and a `[build-system]` table in `pyproject.toml`.
- Tests covering the real RSS/Atom parser, `parse_datetime` timezone normalization, the persistence helpers, and the new security behaviors (+36 tests).

### Changed
- Convergence score now spans the full documented `0–10` range: component ceilings were rescaled by `10/8` so the `high` band is reachable (the score previously maxed out at `8.0`). Relative component weighting is unchanged.
- `confidence` is now derived from evidence sufficiency (count of distinct contributing documents and agreeing source categories) instead of being a relabeling of the score band, so it carries information independent of the score. See `docs/SCORING_GOVERNANCE.md` for before/after evidence.
- Made `feedparser` an optional `[parse]` extra so the default install no longer fails building its transitive `sgmllib3k` sdist; ingestion falls back to a hardened stdlib RSS/Atom parser when `feedparser` is absent.
- Split the CLI architecture so command behavior no longer all lives in `app/cli.py`, and removed the copied import blocks / blanket `# ruff: noqa: F401` left by the split (248 dead imports removed).
- Moved historical process logs out of the repository root into `docs/history/`.
- Routed all single-object JSON artifact writers through the atomic persistence helper.

### Security
- Parse feed XML with `defusedxml`, blocking XXE / external-entity / billion-laughs attacks on the (now default) stdlib parser path.
- Cap fetched feed payloads at 10 MiB to prevent decompression-bomb / runaway-response resource exhaustion.
- Restrict `Source.id` / `Scenario.id` to `[A-Za-z0-9_-]`, defusing latent path traversal where ids are interpolated into artifact file paths.

### Fixed
- Fixed the critical install break (clean `pip install -e '.[dev]'` now succeeds without environment workarounds).
- Moved the coverage gate into `pyproject.toml` (with branch coverage) so it is reproducible locally, not only in CI.

## [0.1.0]

### Added
- Initial deterministic public-document convergence monitor.
- Core ingestion, classification, and scoring pipeline.
- Live source reliability hardening: fallback source URLs and source-health failure summaries.
- Sentence-level classifier negation handling and negation filters.
- Operational, governance, and release documentation.
