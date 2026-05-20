#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

python -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m app.cli validate-config
pytest -q
