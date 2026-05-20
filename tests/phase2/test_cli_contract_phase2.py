from __future__ import annotations

import json

from typer.testing import CliRunner

from app.cli import app


def test_validate_config_emits_stable_json_contract() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["validate-config"])

    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    assert payload["status"] == "ok"
    assert payload["scenario_count"] >= 1
    assert payload["source_count"] >= 1


def test_top_level_help_keeps_core_commands_visible() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0, result.output

    for command in (
        "validate-config",
        "ingest",
        "classify",
        "score",
        "alert",
        "status",
        "verify-live",
        "runs",
        "baselines",
    ):
        assert command in result.output


def test_runs_help_keeps_health_and_list_visible() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["runs", "--help"])

    assert result.exit_code == 0, result.output
    assert "health" in result.output
    assert "list" in result.output
