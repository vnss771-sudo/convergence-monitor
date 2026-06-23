# Convergence Monitor — Build Plan to Top-Tier Standard

**Companion to:** `CODE_COUNCIL_REPORT.md`
**Date:** 2026-06-23
**Goal:** Take the project from "disciplined prototype with inverted priorities" to a credible, installable, validated, single-user-ready product without losing its determinism/reproducibility strengths.

---

## Guiding Principles

1. **Credibility floor before features.** It must install, run, and be honestly measured before anything new is added.
2. **The metric is the product.** An uncalibrated 0–10 score with a tautological "confidence" is the biggest credibility risk; fixing it beats any new scenario or dashboard.
3. **Freeze ceremony.** No new governance docs, supply-chain tooling, or acceptance/review-pack machinery until Phases 1–2 land.
4. **Preserve determinism.** Every change keeps golden/byte-stability tests green; any new non-deterministic stage (e.g. semantic classification) is advisory and layered over the deterministic floor.
5. **Each change is verified** (`python -m pytest`, `ruff check .`, `compileall`, `validate-config`) and small enough to review.

### Severity → phase mapping
- **Phase 0 (done):** CRITICAL install fix + hygiene + packaging metadata.
- **Phase 1 (this sprint):** credibility floor — repro, parser tests, hygiene refactors, security S-wins, supply-chain enforcement.
- **Phase 2 (next):** make the measurement honest and validated.
- **Phase 3:** first user + delivery surface.
- **Phase 4:** scale (scenarios, semantic layer) only after the model is validated.

---

## Phase 0 — Stabilize the Build (DONE in Wave 0)

| # | Task | Status | Verify |
|---|---|---|---|
| 0.1 | Move `feedparser` to optional `[parse]` extra; add `[build-system]` table | ✅ | clean `pip install -e '.[dev]'`; tests green |
| 0.2 | Add `[project.scripts]` console entry point `convergence-monitor` | ✅ | `convergence-monitor --help` |
| 0.3 | Add `license` metadata + move `--cov-fail-under` & coverage config into `pyproject.toml`; add `pytest-cov`/`coverage` to `[dev]` | ✅ | `python -m pytest --cov` runs from clean env |
| 0.4 | Remove committed `.bak` files; gitignore `*.bak` | ✅ | `git ls-files | grep .bak` empty |

---

## Phase 1 — Credibility Floor (target: this sprint)

**Exit criteria:** clean install in CI without hacks; real parser exercised; no copy-paste/dead-import debt; security S-wins closed; supply-chain claims enforced. Target grades: Arch B+, Test A−, Security B+, DevEx B.

### 1.1 Reproducible, enforced supply chain *(Effort: S)* — addresses C6
- Generate and **commit `constraints.txt`** (hash-pinned) via `scripts/dev/compile_constraints.sh`.
- Install with `-c constraints.txt` in `ci.yml`, `release.yml`, `release-provenance.yml`, and `pip-audit`.
- **Pin all GitHub Actions to full commit SHAs** (priority: `softprops/action-gh-release`, which has `contents: write`); keep version comments; let Dependabot bump SHAs.
- **Acceptance:** CI installs the pinned set; `pip-audit` audits the shipped set; no floating tags remain.

### 1.2 Real RSS parser & date tests *(Effort: M)* — addresses C5
- Add `tests/test_rss_parsing.py` feeding raw **bytes** through `parse_rss_payload` and `parse_rss_payload_stdlib`: valid RSS 2.0, valid Atom, malformed XML (expect `IngestionError`), empty feed, namespaced tags, missing fields.
- Parametrize `parse_datetime` (`rss_base.py:59-72`): UTC, non-UTC offsets, naive datetimes, garbage → `None`, epoch fallback.
- Add real-`httpx` failure tests (timeout, all-URLs-fail, empty-then-fallback) using a faked transport rather than monkeypatching the function away.
- **Acceptance:** `rss_base.py` coverage ≥ 90%; parser branches exercised with branch coverage on.

### 1.3 Persistence + timestamp + logging abstractions *(Effort: M)* — addresses C4
- New `app/persistence.py`: `write_json_atomic(path, obj)` (tmp + `os.replace`), `read_json`, `iter_jsonl`, all using the existing `sort_keys=True, ensure_ascii=False` contract. Route all ~9 writers/readers through it.
- Consolidate the 4 duplicate `utc_now_iso()` into `persistence.py` (or `app/timeutil.py`).
- Introduce `logging` (configurable handler); keep JSON-on-stdout as the machine contract, log internal steps/source failures.
- **Acceptance:** no module writes JSON directly; golden + byte-stability tests still green; interrupted-write test shows no partial artifact.

### 1.4 Purge CLI-split debt *(Effort: S)* — addresses C4
- Replace each `app/commands/*.py` god-import block with only the symbols it uses; delete the blanket `# ruff: noqa: F401`.
- Fix or retire `tools/split_cli_commands.py` so it can't regenerate the mess.
- **Acceptance:** `ruff check .` clean with no per-file noqa; tests green.

### 1.5 Security S-wins *(Effort: S)* — addresses §3.3
- `fetch_rss_payload`: stream with a **byte cap** (abort past N MB) and set a redirect cap; reject non-`https`/private-IP redirect targets. Update mocks to a faked transport so unit tests still bypass the network.
- Use `defusedxml` for the stdlib XML fallback path.
- Add `^[A-Za-z0-9_-]+$` validator on `Source.id`/`Scenario.id` (defense-in-depth for path construction). **Note:** verify against test fixtures first — some tests use ids with `?`/`=`; adjust those tests or scope the validator to config-loaded models only.
- **Acceptance:** decompression-bomb and redirect tests pass; config still validates.

### 1.6 Decompose god-functions *(Effort: M)* — addresses C4
- Extract `_verify_sources()` and `_run_pipeline()` from `run_live_verification`; build the full payload before a **single** artifact write (remove the double-write in `live_verification.py` and `live_review.py`).
- Extract `_record_ingest_failure(...)` to collapse the ~5 repeated snapshot+health+error blocks in `commands/ingest.py`.
- **Acceptance:** modules shrink; behavior identical (snapshot/health tests green).

### 1.7 Docs & repo hygiene *(Effort: L)* — addresses C3, §3.5
- Move historical process logs out of root (`SPRINT_*_EXECUTION.md`, `PR17_*.md`, `PR_COMMIT_SERIES.md`, `PHASE2_MANIFEST.json`, `PACKAGE_NOTE.md`) into `docs/history/`.
- Consolidate duplicates: one runbook, one architecture doc, one scoring-governance doc (merge the PhaseN variants).
- Add `docs/README.md` index; add `CHANGELOG.md`, `CONTRIBUTING.md`, and a `Makefile` wrapping `scripts/dev/*`; add `.pre-commit-config.yaml` (ruff).
- **Decision required:** add a `LICENSE` (owner's legal choice — recommend MIT or Apache-2.0; see Open Decisions).
- **Decision required:** resolve `app` vs `convergence-monitor` package naming — either run `tools/rename_app_package.py` or formally keep `app` and delete the rename tool + 2 migration docs.

### 1.8 Tag the first release *(Effort: S)*
- Add `__version__` via `importlib.metadata`; write `CHANGELOG.md`; tag `v0.1.0` so the release pipeline fires for the first time end-to-end.

---

## Phase 2 — Make the Measurement Honest (target: next sprint)

**Exit criteria:** the score's range, confidence, and weights are defensible and documented. Target grade: Product B.

### 2.1 Fix the score range *(Effort: S)* — addresses C2
- Decide: **rescale** component ceilings to span a true 0–10, **or** re-document the attainable range and bands. Recommend rescaling so "high" is reachable and the published 0–10 is honest.
- Update README, SCORING_GOVERNANCE, and golden fixtures together (governance requires before/after evidence).

### 2.2 Replace tautological confidence *(Effort: M)* — addresses C2
- Derive `confidence` from real signals: contributing-document volume, source-category agreement, recency spread, and baseline observation count. Document the derivation. Keep it deterministic.

### 2.3 Build a labeled evaluation set & calibrate *(Effort: L)* — addresses C2
- Hand-label a small relevance/convergence set; compute precision/recall for the classifier; calibrate component weights against it; publish the calibration and a sensitivity note. This converts the metric from arbitrary to defensible — the single highest-value work item in the whole plan.

### 2.4 Anchor the baseline *(Effort: M)* — addresses C2
- Replace the self-referential baseline (mean of own past scores) with a fixed reference window or seasonal expectation, or drop directional "above/below baseline" language.

---

## Phase 3 — First User & Delivery Surface (target: following sprint)

**Exit criteria:** a real person receives output they act on. Target: a product, not a pipeline.

### 3.1 Define the user and the decision *(Effort: S, no code)*
- One page of customer discovery: who reads this (policy analyst / macro desk / journalist), and what action a "7.2 / high" triggers. **Highest-leverage non-code item in the plan** — gates everything below.

### 3.2 A delivery surface *(Effort: S→M)*
- Pick one: a static dashboard rendering the existing alert JSON, **or** an email/Telegram digest. The alert schema already exists (`app/alerts/generator.py`), so this is mostly presentation.

### 3.3 Continuous-coverage delivery *(Effort: S)*
- Wire the nightly verification output into the delivery surface so the user sees a live trend, not files in `data/processed/`.

---

## Phase 4 — Scale (only after Phase 2 lands)

| # | Task | Effort | Notes |
|---|---|---|---|
| 4.1 | Expand source set; make diversity score continuous (not 3-bucket); document trust-weight rationale | M | addresses coverage saturation |
| 4.2 | Semantic classification layer (embeddings or LLM) over the keyword floor | M→L | advisory only; keep deterministic keyword layer as auditable baseline; the biggest precision/recall improvement |
| 4.3 | Second & third scenarios + multi-scenario portfolio view | M | architecture is already scenario-parameterized; validates generalization. Do **after** 2.3 so you don't multiply an uncalibrated model |
| 4.4 | Add `mypy` / type-check gate; branch coverage; per-patch coverage floor (`diff-cover`) | M | quality ratchet |

---

## Sequencing & Rationale

```
Phase 0 (done) ─► Phase 1 (floor) ─► Phase 2 (honest metric) ─► Phase 3 (user) ─► Phase 4 (scale)
                     │                    │
                     └─ unblocks CI       └─ the metric IS the product
```

- Phase 1 is mostly **S/M** and removes the embarrassing failure modes (broken install, untested parser, dead code, unenforced supply-chain claims).
- Phase 2 is where the real intellectual work is; it is deliberately *after* the floor so calibration runs against a clean, installable, tested base.
- Phases 3–4 are explicitly gated on a validated metric and a defined user — the report's central finding is that these were attempted (governance, ops scaffolding) *before* the floor and the metric, which inverted priorities.

---

## Open Decisions (need owner input)

1. **License:** which license for the `LICENSE` file? (Recommend MIT for max reuse, or Apache-2.0 for patent grant.)
2. **Package naming:** run the `app → convergence_monitor` rename, or formally keep `app`?
3. **Score range:** rescale components to a true 0–10, or re-document the real 0–8 range?
4. **Scope of this engagement:** should the agent proceed to implement Phase 1 now, or stop at the report + Phase 0 fixes for review?

---

## Definition of Done (per phase)

- All tests green via `python -m pytest`; `ruff check .` clean; `compileall` clean; `validate-config` clean.
- Coverage gate met (and raised where targeted).
- Golden + byte-stability + false-positive tests unchanged or updated with documented before/after evidence.
- Each change committed atomically with a descriptive message and pushed to the working branch.
