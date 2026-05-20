#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

OUT="${1:-constraints.txt}"

python -m pip install --upgrade pip pip-tools
tmp_file="$(mktemp)"
trap 'rm -f "${tmp_file}"' EXIT

cat > "${tmp_file}" <<'REQ'
-e .[dev]
REQ

pip-compile \
  --resolver=backtracking \
  --generate-hashes \
  --output-file "${OUT}" \
  "${tmp_file}"

printf 'wrote %s\n' "${OUT}"
