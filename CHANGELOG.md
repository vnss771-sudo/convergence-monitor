# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Code council report and a companion build plan/roadmap (`docs/reports/CODE_COUNCIL_REPORT.md`, `docs/reports/UNICORN_BUILD_PLAN.md`).
- Package migration tooling for renaming `app` to `convergence_monitor`.
- Phase 3 release packaging and supply-chain hardening (release provenance and inspectable release evidence).

### Changed
- Split the CLI architecture so command behavior no longer all lives in `app/cli.py`.
- Bumped pinned GitHub Actions (`checkout`, `setup-python`, `upload-artifact`, `codeql-action`).
- Applied code-quality improvements drawn from the analysis report.

### Fixed
- Fixed a critical install break.
- Made `feedparser` an optional `[parse]` extra so the default install no longer fails on its transitive `sgmllib3k` sdist; ingestion falls back to a stdlib RSS/Atom parser when `feedparser` is absent.
- Corrected the release source-zip output path.
- Removed unused imports flagged by Ruff.

## [0.1.0]

### Added
- Initial deterministic public-document convergence monitor.
- Core ingestion, classification, and scoring pipeline.
- Live source reliability hardening: fallback source URLs and source-health failure summaries.
- Sentence-level classifier negation handling and negation filters.
- Operational, governance, and release documentation.
