#!/usr/bin/env bash
set -u

SCENARIO="${SCENARIO:-cbdc_payment_resilience}"
WINDOW="${WINDOW:-30d}"
LIMIT="${LIMIT:-5}"
RUNS="${RUNS:-10}"

SESSION_ID="$(date -u +%Y%m%dT%H%M%SZ)"
SESSION_DIR="data/live_proof_sessions/${SESSION_ID}"
SUMMARY_PATH="${SESSION_DIR}/summary.tsv"

mkdir -p "${SESSION_DIR}"

echo "Convergence Monitor live proof"
echo "Session: ${SESSION_DIR}"
echo "Scenario: ${SCENARIO}"
echo "Window: ${WINDOW}"
echo "Limit: ${LIMIT}"
echo "Runs: ${RUNS}"
echo

echo "Installing dev dependencies..."
pip install -e ".[dev]" > "${SESSION_DIR}/pip_install_dev.log" 2>&1
PIP_RC=$?

echo "Running Ruff..."
python -m ruff check app tests > "${SESSION_DIR}/ruff_check.log" 2>&1
RUFF_RC=$?

echo "pip_install_rc=${PIP_RC}" > "${SESSION_DIR}/gate_status.txt"
echo "ruff_rc=${RUFF_RC}" >> "${SESSION_DIR}/gate_status.txt"

printf 'run\tverify_rc\taccept_rc\treview_rc\thistory_rc\tverification_artifact\n' > "${SUMMARY_PATH}"

for run in $(seq 1 "${RUNS}"); do
  echo
  echo "Live run ${run}/${RUNS}"

  VERIFY_OUT="${SESSION_DIR}/run_${run}_verify.json"
  ACCEPT_OUT="${SESSION_DIR}/run_${run}_accept.json"
  REVIEW_OUT="${SESSION_DIR}/run_${run}_review.json"
  HISTORY_OUT="${SESSION_DIR}/run_${run}_history.json"

  python -m app.cli verify-live \
    --scenario "${SCENARIO}" \
    --window "${WINDOW}" \
    --limit "${LIMIT}" > "${VERIFY_OUT}" 2> "${SESSION_DIR}/run_${run}_verify.stderr"
  VERIFY_RC=$?

  VERIFICATION_ARTIFACT="$(python - "${VERIFY_OUT}" <<'PY'
import json, sys
from pathlib import Path

try:
    data = json.loads(Path(sys.argv[1]).read_text())
    print(data.get("verification_path", ""))
except Exception:
    print("")
PY
)"

  if [ -n "${VERIFICATION_ARTIFACT}" ]; then
    python -m app.cli accept-live --verification "${VERIFICATION_ARTIFACT}" > "${ACCEPT_OUT}" 2> "${SESSION_DIR}/run_${run}_accept.stderr"
    ACCEPT_RC=$?

    python -m app.cli review-live --verification "${VERIFICATION_ARTIFACT}" > "${REVIEW_OUT}" 2> "${SESSION_DIR}/run_${run}_review.stderr"
    REVIEW_RC=$?
  else
    ACCEPT_RC=99
    REVIEW_RC=99
    echo '{"status":"error","message":"verification artifact missing"}' > "${ACCEPT_OUT}"
    echo '{"status":"error","message":"verification artifact missing"}' > "${REVIEW_OUT}"
  fi

  python -m app.cli live-history --scenario "${SCENARIO}" > "${HISTORY_OUT}" 2> "${SESSION_DIR}/run_${run}_history.stderr"
  HISTORY_RC=$?

  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "${run}" "${VERIFY_RC}" "${ACCEPT_RC}" "${REVIEW_RC}" "${HISTORY_RC}" "${VERIFICATION_ARTIFACT}" >> "${SUMMARY_PATH}"
done

echo
echo "Live proof complete."
echo "Session directory: ${SESSION_DIR}"
echo "Summary file: ${SUMMARY_PATH}"
