# Convergence Monitor

Public-document convergence monitor for institutional macro-condition scenarios.

Sprint 1 focuses on a command-line JSON alert engine for one scenario:

`cbdc_payment_resilience`

This project reports observable public-document convergence from public records.

## Current status

This branch implements the project spine, trust layers through Sprint 2, and the Sprint 3 live verification harness.

Included:

- package structure
- scenario config
- source config
- Pydantic config models
- `validate-config` CLI command
- RSS ingestion for one configured source at a time
- normalized raw document records
- deterministic document IDs
- deterministic content hashes
- raw JSONL storage under `data/raw/`
- deterministic keyword classification against the locked scenario
- processed classified JSONL storage under `data/processed/`
- relevance labels: `central`, `incidental`, `excluded`, `irrelevant`
- matched-term explanations and deterministic reasons
- deterministic scenario scoring from classified JSONL
- duplicate content-hash penalty
- stable score JSON output under `data/processed/`
- stable JSON alert output under `data/processed/`
- append/dedupe raw JSONL ingestion
- run snapshots under `data/runs/`
- `runs list` CLI
- structured source failure records
- source health records
- degraded multi-source ingest status
- `runs health` CLI
- evidence quality filtering
- duplicate evidence suppression
- incidental evidence caps
- false-positive fixtures under `data/fixtures/false_positives/`
- tests
- baseline storage and comparison metadata
- deterministic alert reproducibility and golden alert tests
- one-command scenario status summary
- live source verification harness

Not included yet:

- dashboard
- Telegram or email alerts
- market-price feeds
- extra scenarios

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## PR 1 acceptance

```bash
python -m app.cli validate-config
pytest -q
```

## PR 2 acceptance

```bash
python -m app.cli ingest --source bis --limit 10
```

Expected output shape:

```json
{
  "status": "ok",
  "source_id": "bis",
  "fetched": 10,
  "saved": 10,
  "raw_path": "data/raw/bis.jsonl"
}
```

Each JSONL record contains:

- `document_id`
- `source_id`
- `source_name`
- `source_category`
- `title`
- `url`
- `published_at`
- `summary`
- `content_hash`
- `ingested_at`
- `raw`

## PR 3 acceptance

```bash
python -m app.cli classify --scenario cbdc_payment_resilience
```

Expected output shape:

```json
{
  "status": "ok",
  "scenario_id": "cbdc_payment_resilience",
  "documents_read": 10,
  "classified": 10,
  "output_path": "data/processed/cbdc_payment_resilience_classified.jsonl",
  "counts": {
    "central": 2,
    "incidental": 4,
    "excluded": 1,
    "irrelevant": 3
  }
}
```

Each classified JSONL record contains:

- `document_id`
- `source_id`
- `source_name`
- `source_category`
- `title`
- `url`
- `published_at`
- `summary`
- `content_hash`
- `scenario_id`
- `scenario_name`
- `relevance`
- `matched_primary_terms`
- `matched_secondary_terms`
- `matched_exclusion_terms`
- `total_match_count`
- `reason`
- `classified_at`

## PR 4 acceptance

```bash
python -m app.cli score --scenario cbdc_payment_resilience --window 30d
```

Expected output shape:

```json
{
  "status": "ok",
  "scenario_id": "cbdc_payment_resilience",
  "window_days": 30,
  "documents_considered": 12,
  "central_documents": 4,
  "incidental_documents": 5,
  "excluded_documents": 1,
  "irrelevant_documents": 2,
  "active_source_categories": 3,
  "convergence_score": 8.5,
  "confidence": "medium",
  "score_components": {
    "central_document_score": 3.75,
    "source_diversity_score": 2.5,
    "trust_weight_score": 1.5,
    "recency_score": 0.75,
    "duplication_penalty": 0.0
  },
  "limitations": [
    "Baseline model is provisional.",
    "Scoring is deterministic and rule-based.",
This project reports observable public-document convergence from public records.
  ]
}
```

The score is saved to:

```text
data/processed/cbdc_payment_resilience_score.json
```

Scoring rules:

- central documents matter most
- incidental documents contribute lightly
- excluded and irrelevant documents do not add score
- source-category diversity increases score
- trusted configured sources increase score
- newer documents receive mild recency credit
- duplicate content hashes cannot inflate the positive score
- duplicate contributing records apply a penalty
- the score spans the full `0.0–10.0` range: component ceilings
  (central `3.75`, diversity `2.5`, trust `2.5`, recency `1.25`) sum to `10.0`
- score bands describe the score level only:
  - `0.0–2.9` = `low`
  - `3.0–6.9` = `medium`
  - `7.0–10.0` = `high`

`confidence` is **separate from the score band**. It measures how much evidence
supports the score — the number of distinct (deduplicated) contributing documents
and how many institution categories agree — not the score's magnitude. A high
score from a single document is reported as `low` confidence; a moderate score
corroborated across many independent sources is not. Bands:

- `high`: at least 6 contributing documents across at least 3 source categories
- `medium`: at least 3 contributing documents across at least 2 source categories
- `low`: otherwise

## Sprint guardrail

No dashboard, no extra scenarios, no market convergence assessment, no final alert card before PR 5, and no hidden-intent language during Sprint 1.


## PR 5 acceptance

```bash
python -m app.cli alert --scenario cbdc_payment_resilience --window 30d --json
```

The alert is saved to:

```text
data/processed/cbdc_payment_resilience_alert.json
```

The alert reports public-document convergence only and includes:

- scenario ID and name
- generated timestamp derived from stored classified records
- convergence score
- confidence
- document count
- ranked evidence
- warnings
- limitations

## PR 6 acceptance

Repeated ingestion should not duplicate raw records:

```bash
python -m app.cli ingest --source bis --limit 10
python -m app.cli ingest --source bis --limit 10
python -m app.cli runs list
```

Second-run output should show `saved: 0` and `skipped_existing: 10` when the same records are fetched again.

Run snapshots are written to:

```text
data/runs/
```

Each snapshot includes:

- `run_id`
- operation
- subject
- status
- created timestamp
- config hashes
- parameters
- inputs
- outputs
- counts


## PR 7 acceptance

Single-source failures should return structured JSON and write a failure snapshot:

```bash
python -m app.cli ingest --source broken_fixture --limit 10
python -m app.cli runs list
```

Expected failure shape:

```json
{
  "status": "error",
  "operation": "ingest",
  "source_id": "broken_fixture",
  "error": {
    "source_id": "broken_fixture",
    "type": "ingestion_error",
    "message": "..."
  },
  "fetched": 0,
  "saved": 0,
  "skipped_existing": 0
}
```

Multi-source ingestion can now report degraded status without hiding source failures:

```bash
python -m app.cli ingest --source all --limit 10
```

Expected degraded shape:

```json
{
  "status": "degraded",
  "operation": "ingest",
  "sources_attempted": 5,
  "sources_succeeded": 4,
  "sources_failed": 1
}
```

Latest source health can be inspected with:

```bash
python -m app.cli runs health
```

PR 7 does not add scenarios, dashboards, convergence assessments, or narrative analysis.

## Full local verification

```bash
python -m app.cli validate-config
pytest -q
python -m compileall -q app tests
ruff check .
```


## PR 8 acceptance

```bash
pytest -q
python -m app.cli classify --scenario cbdc_payment_resilience
python -m app.cli score --scenario cbdc_payment_resilience --window 30d
python -m app.cli alert --scenario cbdc_payment_resilience --window 30d --json
```

PR 8 adds evidence quality controls only:

- central evidence remains eligible
- incidental evidence is capped
- excluded documents never become positive evidence
- irrelevant documents never become positive evidence
- duplicate content hashes and duplicate URLs are suppressed
- evidence items include `quality_flags`
- false-positive fixtures must not inflate the alert

Still not included:

- dashboard
- new scenarios
- market convergence assessment
- scoring redesign
- speculative narrative interpretation


## PR 12 acceptance

```bash
python -m app.cli verify-live --scenario cbdc_payment_resilience --window 30d
```

The live verification command writes a runtime verification artifact under
`data/runs/live_verifications/` and reports source outcomes without changing
scoring rules or inferring convergence from source availability alone.


## PR 16 acceptance

```bash
python -m app.cli live-history --scenario cbdc_payment_resilience
```

The live-history command reads existing runtime artifacts only. It summarizes
recent `verify-live` results, acceptance decisions, review-pack coverage, the
latest live state, and warnings for rejected or unreviewed usable runs.

It does not fetch sources, generate scores, generate alerts, update baselines,
add scenarios, dashboards, convergence assessments, or narrative interpretation.
