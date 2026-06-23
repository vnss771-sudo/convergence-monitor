.PHONY: install test lint fix compile validate check clean

# Wraps scripts/dev/* where they exist; otherwise calls the underlying commands.

install:
	pip install -e '.[dev]'

test:
	python -m pytest

lint:
	ruff check .

fix:
	ruff check --fix . && ruff format .

compile:
	python -m compileall -q app tests

validate:
	python -m app.cli validate-config

# Mirrors scripts/dev/check.sh (lint + test + compile + validate).
check: lint compile validate test

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov dist build
	rm -f .coverage coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name '*.egg-info' -prune -exec rm -rf {} +
