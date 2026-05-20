#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/clean_runtime_artifacts.sh [--dry-run|--execute]

Removes generated runtime/release artifacts that should not be tracked.
Default: --dry-run
USAGE
}

MODE="dry-run"
while (($#)); do
  case "$1" in
    --dry-run)
      MODE="dry-run"
      shift
      ;;
    --execute)
      MODE="execute"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'error: unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

targets=(
  "LIVE_HISTORY_OUTPUT.json"
  "LIVE_PROOF_REPORT.md"
  "LIVE_PROOF_REPORT_TERMUX.md"
  "convergence-monitor-live-proof-results.zip"
  "convergence-monitor-live-proof-results-v2.zip"
  "convergence-monitor-live-proof-results-termux.zip"
  "SOURCE_MANIFEST.json"
  "data/raw"
  "data/processed"
  "data/runs"
  "data/live_proof_sessions"
  "dist"
  "build"
  ".coverage"
  ".pytest_cache"
  ".ruff_cache"
  ".mypy_cache"
)

for target in "${targets[@]}"; do
  if [[ -e "${target}" ]]; then
    if [[ "${MODE}" == "execute" ]]; then
      git rm -r --cached --ignore-unmatch "${target}" >/dev/null 2>&1 || true
      rm -rf -- "${target}"
      printf 'removed: %s\n' "${target}"
    else
      printf 'would remove: %s\n' "${target}"
    fi
  fi
done

if [[ "${MODE}" == "dry-run" ]]; then
  printf '\nRun with --execute after reviewing the list.\n'
fi
