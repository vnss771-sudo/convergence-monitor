# Documentation Index

This directory holds the project's design, operations, governance, and release
documentation. Files are grouped by purpose below. Some topics currently have
more than one document; those are flagged under
[Consolidation candidates (TODO)](#consolidation-candidates-todo) for a human to
review and merge later — they are intentionally **not** merged here.

## Architecture

- [ARCHITECTURE_NEXT.md](ARCHITECTURE_NEXT.md) — Current and near-term shape of the system and its core areas.
- [PHASE2_ARCHITECTURE.md](PHASE2_ARCHITECTURE.md) — Target architecture for the Phase 2 work.

## Operations / Runbooks

- [OPERATOR_RUNBOOK.md](OPERATOR_RUNBOOK.md) — How a human operator runs the monitor live.
- [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md) — Local verification and operational commands.
- [OPERATIONS_RUNBOOK_PHASE2.md](OPERATIONS_RUNBOOK_PHASE2.md) — Phase 2 daily local check procedures.
- [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md) — Responding to live verification, source health, and scoring incidents.
- [LIVE_ACCEPTANCE_CHECKLIST.md](LIVE_ACCEPTANCE_CHECKLIST.md) — Gate for accepting, rejecting, or escalating a live run.
- [TERMUX_SUPPORT.md](TERMUX_SUPPORT.md) — Running the monitor (and live signal tests) on Termux/Android.

## Scoring & Governance

- [SCORING_GOVERNANCE.md](SCORING_GOVERNANCE.md) — Principles governing the deterministic convergence score.
- [SCORING_GOVERNANCE_PHASE2.md](SCORING_GOVERNANCE_PHASE2.md) — Phase 2 scoring rules.
- [GUARDRAIL_LANGUAGE_POLICY.md](GUARDRAIL_LANGUAGE_POLICY.md) — Language guardrails (no claims of intent, causation, prediction).

## Supply Chain & Release

- [SUPPLY_CHAIN.md](SUPPLY_CHAIN.md) — Supply-chain integrity and inspectable release evidence.
- [RELEASE_ENGINEERING.md](RELEASE_ENGINEERING.md) — Release goals and engineering process.
- [RELEASE_PROVENANCE.md](RELEASE_PROVENANCE.md) — Release provenance artifact generation.
- [DEPENDENCY_POLICY.md](DEPENDENCY_POLICY.md) — Runtime dependency declaration and lock/constraints policy.

## Migration

- [CLI_SPLIT_MIGRATION.md](CLI_SPLIT_MIGRATION.md) — Splitting command behavior out of `app/cli.py`.
- [MIGRATION_APP_TO_CONVERGENCE_MONITOR.md](MIGRATION_APP_TO_CONVERGENCE_MONITOR.md) — Rationale for renaming the `app` package.
- [PACKAGE_RENAME_MIGRATION.md](PACKAGE_RENAME_MIGRATION.md) — Steps to rename the import package to `convergence_monitor`.

## Reports

- [reports/CODE_COUNCIL_REPORT.md](reports/CODE_COUNCIL_REPORT.md) — Comprehensive code-council review of the codebase.
- [reports/UNICORN_BUILD_PLAN.md](reports/UNICORN_BUILD_PLAN.md) — Roadmap / build plan to top-tier standard (companion to the council report).

## Examples

- [examples/](examples/) — Sample verification outputs (`verification_accepted.json`, `verification_degraded.json`, `verification_error.json`).

## History

Historical process logs preserved for the record (moved here via `git mv`):

- [history/SPRINT_1_EXECUTION.md](history/SPRINT_1_EXECUTION.md)
- [history/SPRINT_2_EXECUTION.md](history/SPRINT_2_EXECUTION.md)
- [history/SPRINT_3_EXECUTION.md](history/SPRINT_3_EXECUTION.md)
- [history/PR17_LIVE_SOURCE_HARDENING_NOTE.md](history/PR17_LIVE_SOURCE_HARDENING_NOTE.md)
- [history/PR_COMMIT_SERIES.md](history/PR_COMMIT_SERIES.md)
- [history/PACKAGE_NOTE.md](history/PACKAGE_NOTE.md)
- [history/PHASE2_MANIFEST.json](history/PHASE2_MANIFEST.json)

## Consolidation candidates (TODO)

The following topics have multiple overlapping documents. A human should review
and consolidate them; their content has intentionally **not** been merged.

- **Runbooks** — three operational runbooks cover overlapping ground:
  - `OPERATIONS_RUNBOOK.md`
  - `OPERATIONS_RUNBOOK_PHASE2.md`
  - `OPERATOR_RUNBOOK.md`
- **Scoring governance** — two documents:
  - `SCORING_GOVERNANCE.md`
  - `SCORING_GOVERNANCE_PHASE2.md`
- **Architecture** — two documents:
  - `ARCHITECTURE_NEXT.md`
  - `PHASE2_ARCHITECTURE.md`
- **Package/CLI migration** — three related migration notes that may be partly superseded:
  - `MIGRATION_APP_TO_CONVERGENCE_MONITOR.md`
  - `PACKAGE_RENAME_MIGRATION.md`
  - `CLI_SPLIT_MIGRATION.md`
