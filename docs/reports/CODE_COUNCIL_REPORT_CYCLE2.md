# Convergence Monitor — Code Council Report, Cycle 2

**Date:** 2026-06-23
**Predecessor:** `CODE_COUNCIL_REPORT.md` (Cycle 1) + `UNICORN_BUILD_PLAN.md`
**Scope:** Fresh five-reviewer audit of `main` *after* Cycle 1 (Phases 0–2) merged in PR #14.
**Method:** Council of 5 re-run against the current code, each verifying the just-merged changes and mapping the remaining frontier.

---

## 1. Where We Are Now

Cycle 1 fixed the credibility floor: clean install, atomic persistence, real parser tests, security hardening, an honest 0–10 score, evidence-based confidence, and onboarding/supply-chain scaffolding. Ground truth on `main`: **119 tests pass, ~85% coverage (branch on), ruff clean, clean install.**

The council confirms the merged work is sound — with **one correctness regression the tests didn't catch** — and that the project's centre of gravity has now shifted from "does it work" to **"is the metric defensible and is there a product."**

### Cycle-2 scorecard (vs Cycle 1)

| Dimension | Cycle 1 | Cycle 2 | Movement |
|---|---|---|---|
| Architecture | B− | **B** | persistence consolidation verified clean |
| Testing | B | **B+** | strong new tests; infra gaps remain |
| Methodology | C+ | **C+** | range/confidence fixed; baseline + weights still weak |
| DevEx / Release | D+ | **B−** | install/packaging/supply-chain hardened |
| Product readiness | (n/a) | **D+** | engineering B+/A−, but still a pipeline, no user |

---

## 2. Consensus Findings (Cycle 2)

### F1 — HIGH (correctness): the explainability invariant is broken
`convergence.py` rounds each `ScoreComponents` field independently *and* rounds the score from the unrounded sum, so `Σ(rounded components) − penalty` can differ from `convergence_score` by up to 0.2 (`app/scoring/convergence.py:271-286`). For a tool whose entire pitch is an auditable, explainable score, the displayed components must reconcile to the displayed score. **Fix this cycle.**

### F2 — HIGH (methodology): the baseline is self-referential
"above/below baseline" compares a score to the running mean of the scenario's *own* past scores, with no exogenous anchor, no minimum-observation gate, and event-count (not time-normalized) observations (`app/scoring/baselines.py:149-190`). Concrete deterministic fix designed: time-bucket observations by day, compare against a fixed trailing window excluding the current point, and **refuse directional language** until a minimum number of buckets spanning a minimum number of days exists. `BaselineComparison` already permits `None` for directional fields — no schema change. **Fix this cycle.**

### F3 — HIGH (testing infra): no `conftest.py`; gameable coverage gate
`make_classified`/`make_hash`/`PROJECT_ROOT` are copy-pasted across 5–9 test files. The single global 80% floor hides command-glue modules at 31–37% behind high-coverage libraries. **Add `conftest.py` this cycle; per-patch coverage is a fast-follow.**

### F4 — HIGH (DevEx): missing LICENSE, floating actions, unpackaged config
`pyproject` declares MIT but there is no `LICENSE` file. All 8 third-party actions float on mutable tags (including jobs with `contents:`/`id-token:`/`attestations: write`). `config/*.yaml` isn't packaged and the runtime loads a relative `Path("config")`, so `pip install` outside the repo fails. **LICENSE this cycle; SHA-pinning and config-packaging are scoped follow-ups.**

### F5 — MEDIUM/known: weights uncalibrated; classifier ceiling; god-functions; no logging/mypy
The component weights remain expert priors (a labeled-eval-set + grid-search calibration plan is specified). The keyword classifier has a real recall ceiling (advisory LLM-over-deterministic second stage proposed). `run_live_verification` still double-writes and `ingest.py` repeats a failure triad 4×. No logging layer, no mypy gate. **Sequenced across this and future cycles.**

---

## 3. What's Verified Clean (no action)
- Atomic write (`write_json_atomic`) is correct: same-dir tmp → `fsync` → `os.replace`, `BaseException` cleanup; the failure-cleanup branch is even tested.
- All single-object JSON writers route through persistence; remaining direct writers are JSONL/hashing (correctly outside the contract). No import cycles.
- `SCORE_SCALE` applied uniformly; `confidence_for_evidence` correctly uses evidence counts, not score magnitude.
- Release pipeline is proven (it has run and published a Release); tags exist.

---

## 4. The Central Recommendation (unchanged in spirit, sharper now)
1. **Make the score correct and the baseline honest** (F1, F2) — the metric is still the product.
2. **Harden the test infrastructure** (F3) so the above can't silently regress.
3. **Then** build the first user-facing slice (static dashboard over the alert JSON) — but only *after* the metric is defensible.

Detailed sequencing and the executed wave are in `BUILD_PLAN_CYCLE2.md`.
