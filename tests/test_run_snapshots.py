from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.runs.snapshots import list_run_snapshots, write_run_snapshot


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_write_and_list_run_snapshot(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    path = write_run_snapshot(
        runs_dir=runs_dir,
        operation="ingest",
        subject="bis",
        status="ok",
        parameters={"limit": 10},
        outputs={"raw_path": "data/raw/bis.jsonl"},
        counts={"saved": 10},
        config_dir=PROJECT_ROOT / "config",
        timestamp="2026-05-19T00:00:00Z",
    )

    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "20260519T000000Z_ingest_bis"
    assert payload["operation"] == "ingest"
    assert payload["status"] == "ok"
    assert payload["config_hashes"]["scenarios_yaml"]

    listed = list_run_snapshots(runs_dir)
    assert len(listed) == 1
    assert listed[0]["run_id"] == "20260519T000000Z_ingest_bis"


def test_runs_list_cli_returns_snapshots(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    write_run_snapshot(
        runs_dir=runs_dir,
        operation="ingest",
        subject="bis",
        status="ok",
        config_dir=PROJECT_ROOT / "config",
        timestamp="2026-05-19T00:00:00Z",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.cli",
            "runs",
            "list",
            "--runs-dir",
            str(runs_dir),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["run_count"] == 1
    assert payload["runs"][0]["operation"] == "ingest"
