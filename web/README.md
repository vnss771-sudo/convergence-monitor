# Convergence Monitor — Static Dashboard

A minimal, dependency-free dashboard for the `cbdc_payment_resilience` scenario.
It reports **observable public-document convergence from public records** — and
nothing more: no claims about intent, coordination, causation, or future events.

> **Provisional — methodology not yet calibrated.** The score weights are not
> yet validated. Every number on this page is indicative, not authoritative.

## What this is

- A single static page: `index.html` + `styles.css` + `app.js`.
- **No npm, no framework, no build step.** Plain HTML/CSS/JS.
- At load, `app.js` calls `fetch()` for two files and renders them:
  - `data/alert.json` — one alert card (the `AlertRecord` shape produced by
    `python -m app.cli alert`).
  - `data/history.json` — a small array of `{ date, convergence_score,
    confidence }` points for the score-over-time sparkline.

The page renders:

- the convergence score (0–10) as a gauge plus the band (low / medium / high),
- the confidence badge,
- the summary line,
- the **ranked evidence table** (title → source → relevance → matched terms →
  published date → link),
- `warnings[]` and `limitations[]` rendered **verbatim**,
- a pure-SVG sparkline of score over time.

All external strings (titles, terms, URLs) are inserted via `textContent` /
DOM nodes, never as raw HTML.

## How it gets data

The page is fully static and deterministic: the same JSON always renders the
same page. There is no server-side logic and no client-side computation of the
score — `app.js` only reads and displays what the pipeline already produced.

`data/alert.json` is refreshed by the engine. Locally you can regenerate it:

```bash
# from the repo root
python -m app.cli classify --scenario cbdc_payment_resilience
python -m app.cli score    --scenario cbdc_payment_resilience --window 30d
python -m app.cli alert     --scenario cbdc_payment_resilience --window 30d --json
cp data/processed/cbdc_payment_resilience_alert.json web/data/alert.json
```

In CI, the `.github/workflows/dashboard-refresh.yml` workflow does the same on a
nightly schedule (and on manual dispatch), then appends a point to
`history.json` and commits the updated `web/data/`.

### Seed data

`data/alert.json` is seeded with the project's golden fixture so the page
renders out of the box.

`data/history.json` is **hand-made seed data** (~6 points across dates) so the
sparkline has something to draw before the workflow has run. The refresh
workflow appends real `{ date, convergence_score, confidence }` entries over
time.

## Preview locally

The page uses `fetch()`, which browsers block for `file://` URLs. Serve it over
HTTP instead:

```bash
cd web
python -m http.server 8000
# then open http://localhost:8000/
```

Any static file server works; no install is required beyond Python's stdlib.
