#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ruff check . --fix
pytest -q
