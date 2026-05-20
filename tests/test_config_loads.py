from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.models import load_configs


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_config_loads() -> None:
    bundle = load_configs(PROJECT_ROOT / "config")

    assert len(bundle.scenarios.scenarios) == 1
    assert bundle.scenarios.scenarios[0].id == "cbdc_payment_resilience"

    assert len(bundle.sources.sources) == 5
    assert {source.id for source in bundle.sources.sources} == {
        "bis",
        "imf",
        "rba",
        "federal_reserve",
        "ecb",
    }


def test_config_has_at_least_three_enabled_source_categories() -> None:
    bundle = load_configs(PROJECT_ROOT / "config")
    categories = {source.category for source in bundle.enabled_sources}

    assert len(categories) >= 3


def test_validate_config_cli_returns_ok() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app.cli", "validate-config"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["scenario_count"] == 1
    assert payload["source_count"] == 5
