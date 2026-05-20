#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  verify_phase3_release.sh --repo-dir PATH [--dist-dir PATH]

Verifies Phase 3 release SBOM, provenance, checksums, dependency policy, and language guardrails.
USAGE
}

REPO_DIR=""
DIST_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-dir)
      REPO_DIR="${2:-}"
      shift 2
      ;;
    --dist-dir)
      DIST_DIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${REPO_DIR}" ]]; then
  echo "--repo-dir is required" >&2
  exit 2
fi

REPO_DIR="$(cd "${REPO_DIR}" && pwd)"
DIST_DIR="${DIST_DIR:-${REPO_DIR}/dist}"

python "${REPO_DIR}/tools/guardrail_language_audit.py" --root "${REPO_DIR}" --format markdown --fail-on error
python "${REPO_DIR}/tools/dependency_policy_audit.py" --root "${REPO_DIR}" --format markdown --fail-on high
python "${REPO_DIR}/tools/verify_supply_chain_artifacts.py" --root "${REPO_DIR}" --dist-dir "${DIST_DIR}"
