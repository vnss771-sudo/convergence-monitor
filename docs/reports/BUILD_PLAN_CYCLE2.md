# Convergence Monitor — Build Plan, Cycle 2

**Companion to:** `CODE_COUNCIL_REPORT_CYCLE2.md`
**Predecessor:** `UNICORN_BUILD_PLAN.md` (Phases 0–4; Phases 0–2 merged in PR #14)
**Date:** 2026-06-23

This plan sequences the work the Cycle-2 council surfaced. Items marked **[executed]**
were implemented and verified in this cycle; the rest are scoped for follow-up.

---

## Wave A — Correctness & honesty (this cycle)

### A1 — Fix the score-additivity invariant **[executed]** *(HIGH, F1)*
Round each component once, then compute `convergence_score` from the **sum of the
already-rounded components minus the rounded penalty**, so `Σ components − penalty
== convergence_score` exactly. Express the alert summary bands (`generator.py`) as
named constants tied to the documented 0–10 score bands. Add a regression test
asserting the invariant and pinning the bands. Golden fixtures regenerated with
before/after governance evidence.

### A2 — Anchor the baseline **[executed]** *(HIGH, F2)*
Time-bucket observations by day (last per day), compare the current score against a
fixed trailing reference window that **excludes** the current point, and gate
directional language behind a minimum bucket count spanning a minimum day span;
emit `not_enough_history` (with descriptive stats, `delta=None`) otherwise. No
schema change. Tests cover the gate, the cadence-normalization, and the directional
path.

### A3 — Add `LICENSE` **[executed]** *(HIGH, F4)*
MIT `LICENSE` file matching the `pyproject` metadata so the published artifact
carries the license it claims.

---

## Wave B — Test infrastructure (this cycle)

### B1 — `tests/conftest.py` **[executed]** *(HIGH, F3)*
Shared `make_classified`, `make_hash`, `make_source`, `project_root`, and
`config_bundle` fixtures; migrate duplicated helpers out of the test modules.

### B2 — Scoring invariant & boundary tests **[executed]** *(MED, testing F3–F5)*
Pin: max basis → 10.0, clamp at both ends, the diversity tiers, the duplication
penalty cap, and the confidence bands at their exact edges (2/2, 3/2, 5/3, 6/3).

### B3 — Property-based tests **[executed]** *(MED, testing F7)*
`hypothesis` for `0 ≤ score ≤ 10` over arbitrary document sets, dedupe tie-break
stability, and `parse_datetime` always returning a valid `…Z` string or `None`.

### B4 — Drop the duplicate CI test run **[executed]** *(LOW, testing F9)*
CI ran the suite twice; keep only the coverage run.

---

## Wave C — Scoped follow-ups (next cycles; some need decisions/tools)

| # | Item | Effort | Why deferred |
|---|---|---|---|
| C1 | SHA-pin all 8 GitHub Actions (`@sha # vX.Y.Z`), Dependabot already manages them | S–M | Needs reliable tag→SHA resolution (gh/API); wrong SHA breaks workflows — do where it can be verified |
| C2 | Package `config/*.yaml` as data + resolve packaged config via `importlib.resources` | L | Changes the repo-relative runtime contract every test/CI relies on; needs a careful dedicated change |
| C3 | Per-patch coverage floor (`diff-cover`) + `CliRunner` tests for `classify`/`alerts`/`config` | M | Lifts the 31–37% command glue; gate change best landed with the new tests |
| C4 | Extract the ingest failure-triad helper; decompose `run_live_verification`, kill double-writes | M | Mechanical, test-covered; maintainability not correctness |
| C5 | Logging layer (`getLogger`, `--verbose`); replace silent `except: continue` with `logger.warning` | S–M | Observability; no behavior change |
| C6 | Non-strict `mypy` gate | M | Annotation coverage is strong; main work is typing `dict[str, Any]` payloads |
| C7 | Doc consolidation: 10 overlapping docs → 4 (runbooks, scoring, architecture, migration) | M | Content merge needs care; propose-only |
| C8 | Weight calibration: labeled eval set + classifier P/R floors + grid-search → `config/scoring_weights.yaml` | L | Needs human labeling; the real validity work |
| C9 | Advisory LLM/semantic second stage over the keyword floor (never overrides the deterministic score) | M–L | Raises recall; must stay advisory + reproducible |

---

## Wave D — Product (after the metric is defensible)

| # | Item | Effort |
|---|---|---|
| D1 | Static Vercel dashboard rendering the existing alert JSON + nightly CI refresh + dated history | S–M |
| D2 | Score-over-time trend view from committed history | S |
| D3 | Second scenario (climate/green-finance) reusing existing sources | M |
| D4 | Email/Telegram weekly digest teasing into the dashboard | S |

**Gate:** do not publish a public dashboard until A1/A2 and a basic calibration note (C8)
land — publishing an uncalibrated headline number is the fastest way to lose the
credibility that is the entire pitch.

---

## Open decisions (owner)
- Confirm **MIT** (now shipped as `LICENSE`) is the intended license.
- Approve the package-rename (`app → convergence_monitor`) before C2, or keep `app`.
- Prioritize calibration (C8) vs. first product surface (D1) for the next cycle.

## Definition of done (per item)
`make check` green; golden/byte-stability tests intact or updated with documented
before/after evidence; each change committed atomically and pushed.
