# Sprint 1 Execution Plan — Convergence Monitor

## Objective

Build a command-line MVP that ingests trusted public institutional documents, classifies them against one predefined scenario, scores convergence, and emits stable reproducible JSON alerts.

The system does not infer intent, coordination, causation, or inevitability.

It only reports observable public-document convergence.

---

## First Scenario

Scenario ID:

`cbdc_payment_resilience`

Scenario name:

`Cross-border CBDC and payment-system resilience convergence`

Scenario description:

Detect elevated public institutional activity around CBDCs, cross-border payments, settlement infrastructure, programmable money, payment resilience, financial-market infrastructure, and central-bank digital settlement systems.

---

## First Source Set

Maximum first-sprint sources:

1. BIS
2. IMF
3. RBA
4. Federal Reserve
5. ECB

No media.
No social media.
No podcasts.
No market-price feeds.
No WEF.
No extra institutions until Sprint 1 passes.

---

## Required Output

The only production output of Sprint 1 is JSON.

No dashboard.
No Telegram.
No email alerts.
No narrative report.
No prediction engine.

---

## Required CLI Commands

```bash
python -m app.cli validate-config
python -m app.cli ingest --source bis --limit 10
python -m app.cli classify --scenario cbdc_payment_resilience
python -m app.cli score --scenario cbdc_payment_resilience --window 30d
python -m app.cli alert --scenario cbdc_payment_resilience --window 30d --json
```

---

## JSON Alert Requirements

Each alert must contain:

- `scenario_id`
- `scenario_name`
- `generated_at`
- `window_days`
- `convergence_score`
- `confidence`
- `source_categories_active`
- `document_count`
- `summary`
- `evidence`
- `warnings`
- `limitations`

The alert must be reproducible from stored raw/processed documents.

---

## Guardrails

Forbidden during Sprint 1:

- dashboard work
- extra scenarios
- market prediction
- price forecasting
- hidden-intent language
- conspiracy wording
- vague intelligence summaries
- unexplained scores
- non-reproducible alerts

---

## Kill Criteria

Sprint 1 fails if:

1. Alerts cannot explain their evidence.
2. Keyword matches produce mostly irrelevant documents.
3. Scores change without document changes.
4. JSON schema is unstable.
5. The system requires manual interpretation to be useful.
6. The system drifts into narrative speculation.

---

## Definition of Success

Sprint 1 succeeds when:

1. One scenario runs end-to-end from config to JSON alert.
2. At least three source categories can be ingested or fixture-tested.
3. Classification separates central relevance from incidental mentions.
4. Scoring is explainable.
5. Alert JSON is stable.
6. Tests pass.
7. No dashboard exists.

---

## Sprint 1 PR Sequence

### PR 1 — Skeleton and config validation

Goal:

The repo boots, config loads, tests pass, and CLI exists.

Acceptance:

```bash
python -m app.cli validate-config
pytest
```

### PR 2 — Ingestion

Goal:

Fetch documents from one RSS source, normalize metadata, save raw records.

Acceptance:

```bash
python -m app.cli ingest --source bis --limit 10
```

Must save:

- `document_id`
- `source_id`
- `title`
- `url`
- `published_at`
- `content_summary`
- `content_hash`
- `raw_payload`

### PR 3 — Classification

Goal:

Classify documents as central, incidental, excluded, or irrelevant.

Acceptance:

```bash
python -m app.cli classify --scenario cbdc_payment_resilience
```

Must explain:

- matched primary terms
- matched secondary terms
- excluded terms
- relevance label
- reason

### PR 4 — Scoring

Goal:

Calculate an explainable convergence score from classified documents.

Acceptance:

```bash
python -m app.cli score --scenario cbdc_payment_resilience --window 30d
```

Score should consider:

- number of active source categories
- number of central documents
- source trust weights
- recency
- document diversity
- duplication penalties

### PR 5 — JSON alert generation

Goal:

Generate the first stable alert card.

Acceptance:

```bash
python -m app.cli alert --scenario cbdc_payment_resilience --window 30d --json
```

Output shape:

```json
{
  "scenario_id": "cbdc_payment_resilience",
  "scenario_name": "Cross-border CBDC and payment-system resilience convergence",
  "generated_at": "2026-05-19T00:00:00Z",
  "window_days": 30,
  "convergence_score": 7.2,
  "confidence": "medium",
  "source_categories_active": 3,
  "document_count": 12,
  "summary": "Public institutional activity related to CBDC and payment-system resilience is above baseline across multiple independent source categories.",
  "evidence": [
    {
      "source_id": "bis",
      "source_name": "Bank for International Settlements",
      "title": "Example document title",
      "url": "https://example.com",
      "published_at": "2026-05-01",
      "relevance": "central",
      "matched_terms": [
        "cbdc",
        "cross-border payments",
        "settlement infrastructure"
      ],
      "reason": "The scenario is central to the document, not a passing reference."
    }
  ],
  "warnings": [
    "Baseline model is provisional.",
    "Market-price module is disabled.",
    "Narrative interpretation is disabled."
  ],
  "limitations": [
    "This alert reports public-document convergence only.",
    "It does not infer intent, coordination, or future events."
  ]
}
```

---

## Sprint 1 Rule

Build PR 1 only first.

Do not touch ingestion until this works:

```bash
python -m app.cli validate-config
pytest
```

Once PR 1 passes, the project has a real spine. Then every later piece has to attach to that spine instead of drifting.
