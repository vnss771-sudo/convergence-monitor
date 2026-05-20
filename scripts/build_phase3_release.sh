#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  build_phase3_release.sh --repo-dir PATH [--dist-dir PATH]

Builds Python distributions when possible, then generates SBOM, provenance, and checksums.
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
mkdir -p "${DIST_DIR}"

cd "${REPO_DIR}"

python tools/guardrail_language_audit.py --root "${REPO_DIR}" --format markdown --fail-on error
python tools/dependency_policy_audit.py --root "${REPO_DIR}" --format markdown --fail-on high

if python -c 'import build' >/dev/null 2>&1; then
  rm -rf "${DIST_DIR:?}/"*
  python -m build --outdir "${DIST_DIR}"
else
  echo "python package 'build' is not installed; skipping wheel/sdist build." >&2
  echo "Install with: python -m pip install build" >&2
fi

python tools/generate_minimal_sbom.py --root "${REPO_DIR}" --output "${DIST_DIR}/convergence-monitor.sbom.cdx.json"
python tools/generate_release_provenance.py --root "${REPO_DIR}" --dist-dir "${DIST_DIR}" --output "${DIST_DIR}/release-provenance.json"
python tools/verify_supply_chain_artifacts.py --root "${REPO_DIR}" --dist-dir "${DIST_DIR}"

echo "Phase 3 release artifacts are in ${DIST_DIR}"
