#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

python -m app.cli validate-config
python -m compileall -q app tests
ruff check .
pytest -q
