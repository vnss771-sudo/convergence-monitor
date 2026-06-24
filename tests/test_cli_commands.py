"""CliRunner tests for the command-body glue (config / classify / alert).

These commands were the least-covered modules (31-37%) - the coverage the global
gate could hide. Here we exercise happy paths and the explicit error exits.
"""

from __future__ import annotations

import json

from app.cli import app
from app.models import load_configs
from app.classification.keyword_matcher import save_classified_documents_jsonl
from app.scoring.convergence import save_score_json, score_documents

SCENARIO_ID = "cbdc_payment_resilience"


# --- config commands ----------------------------------------------------------


def test_validate_config_ok(runner, config_dir):
    result = runner.invoke(app, ["validate-config", "--config-dir", str(config_dir)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["scenario_count"] >= 1


def test_validate_config_missing_dir_errors(runner, tmp_path):
    result = runner.invoke(app, ["validate-config", "--config-dir", str(tmp_path / "nope")])
    assert result.exit_code == 1


def test_list_scenarios_ok(runner, config_dir):
    result = runner.invoke(app, ["list-scenarios", "--config-dir", str(config_dir)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert any(s["id"] == SCENARIO_ID for s in payload["scenarios"])


# --- classify -----------------------------------------------------------------


def test_classify_unknown_scenario_errors(runner, config_dir, tmp_path):
    result = runner.invoke(
        app,
        ["classify", "--scenario", "no_such_scenario", "--config-dir", str(config_dir),
         "--raw-dir", str(tmp_path / "raw"), "--processed-dir", str(tmp_path / "proc"),
         "--runs-dir", str(tmp_path / "runs")],
    )
    assert result.exit_code == 1


def test_classify_empty_raw_dir_succeeds_with_zero(runner, config_dir, tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    result = runner.invoke(
        app,
        ["classify", "--scenario", SCENARIO_ID, "--config-dir", str(config_dir),
         "--raw-dir", str(raw_dir), "--processed-dir", str(tmp_path / "proc"),
         "--runs-dir", str(tmp_path / "runs")],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["documents_read"] == 0
    assert payload["classified"] == 0


# --- alert --------------------------------------------------------------------


def test_alert_requires_json_flag(runner, config_dir, tmp_path):
    result = runner.invoke(
        app,
        ["alert", "--scenario", SCENARIO_ID, "--config-dir", str(config_dir),
         "--processed-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "json" in result.output.lower()


def test_alert_missing_score_errors(runner, config_dir, tmp_path):
    result = runner.invoke(
        app,
        ["alert", "--scenario", SCENARIO_ID, "--json", "--config-dir", str(config_dir),
         "--processed-dir", str(tmp_path)],
    )
    assert result.exit_code == 1


def test_alert_json_happy_path(runner, config_dir, classified_factory, tmp_path):
    processed = tmp_path / "proc"
    processed.mkdir()
    bundle = load_configs(config_dir)
    documents = [
        classified_factory(document_id="d1", source_id="bis",
                            source_category="central_bank_coordination", relevance="central"),
        classified_factory(document_id="d2", source_id="imf", source_name="IMF",
                            source_category="international_finance", relevance="central"),
    ]
    save_classified_documents_jsonl(documents, scenario_id=SCENARIO_ID, processed_dir=processed)
    score = score_documents(documents, bundle=bundle, scenario_id=SCENARIO_ID, window_days=30)
    save_score_json(score, processed_dir=processed)

    result = runner.invoke(
        app,
        ["alert", "--scenario", SCENARIO_ID, "--json", "--config-dir", str(config_dir),
         "--processed-dir", str(processed), "--runs-dir", str(tmp_path / "runs")],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["scenario_id"] == SCENARIO_ID
    assert payload["confidence"] in {"low", "medium", "high"}
    assert (processed / f"{SCENARIO_ID}_alert.json").exists()
