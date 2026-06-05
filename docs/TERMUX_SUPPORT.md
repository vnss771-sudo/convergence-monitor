# Termux Support

Convergence Monitor runs on Termux (Android) with outbound internet access,
which makes it the natural place to run live signal tests when a cloud
container or restricted environment is unavailable.

## One-time setup

```bash
# 1. Install system packages
pkg update && pkg install python git

# 2. Clone the repo (replace with your fork URL if needed)
git clone https://github.com/vnss771-sudo/convergence-monitor.git
cd convergence-monitor

# 3. Create a virtual environment
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

# 4. Install runtime dependencies
#    feedparser pulls in sgmllib3k which may fail to build on ARM —
#    the project has a stdlib XML fallback so feedparser is optional.
pip install typer pydantic pyyaml httpx python-dateutil

# Try feedparser separately; skip if it fails
pip install feedparser || echo "feedparser unavailable — stdlib RSS parser will be used"

# 5. Validate config and list scenarios
python -m app.cli validate-config
python -m app.cli list-scenarios
```

## Running the live signal test

```bash
# Single verify-live run — fetches all 5 RSS sources and classifies documents
python -m app.cli verify-live --scenario cbdc_payment_resilience --window 30d

# The output JSON includes a verification_path field.
# Copy that path and run the acceptance gate:
python -m app.cli accept-live --verification <verification_path>

# Generate the operator review pack:
python -m app.cli review-live --verification <verification_path>

# Check trend across runs:
python -m app.cli live-history --scenario cbdc_payment_resilience
```

## Multi-run live proof (uses the bundled script)

```bash
# Default: 10 runs, limit 5 articles per source, 30-day window
bash scripts/run_live_proof_termux.sh

# Override parameters
RUNS=3 LIMIT=10 WINDOW=14d bash scripts/run_live_proof_termux.sh
```

Results land in `data/live_proof_sessions/<timestamp>/`.
The `summary.tsv` file shows pass/fail for every run step.

## Reading results

Key fields in the verify-live output:

| Field | What it tells you |
|-------|------------------|
| `status` | `ok` / `degraded` / `error` |
| `sources_ok` | How many feeds were fetched successfully |
| `documents_ingested` | Total articles fetched this run |
| `confidence` | `low` / `medium` / `high` convergence signal |
| `convergence_score` | 0–10 score (check score JSON in processed/) |

## Ruff caveat

Ruff pre-built wheels are unavailable for Android ARM on older Termux
versions. Ruff is enforced in GitHub Actions CI — skip it on Termux:

```bash
# Install without dev extras (no ruff, no pytest)
pip install typer pydantic pyyaml httpx python-dateutil feedparser

# Or install dev deps and ignore ruff failure
pip install pytest
# run tests without ruff
python -m pytest -q
```

## Mobile-safe practices

- Use pinned release tags for reproducibility.
- Keep generated data (`data/`) outside source archives — it is gitignored.
- Prefer `--window 14d` to reduce processing time on slower devices.
- `--limit 5` (default) keeps each fetch fast on mobile data.
- Run `live-history` after each session to track signal trends over time.
