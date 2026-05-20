from __future__ import annotations

import subprocess
from pathlib import Path


RUNTIME_PREFIXES = (
    "data/raw/",
    "data/processed/",
    "data/runs/",
    "data/live_proof_sessions/",
)

ROOT_GENERATED_FILES = {
    "LIVE_HISTORY_OUTPUT.json",
    "LIVE_PROOF_REPORT.md",
    "LIVE_PROOF_REPORT_TERMUX.md",
}


def git_ls_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def test_runtime_data_is_not_tracked() -> None:
    tracked = git_ls_files()
    offenders = [
        path
        for path in tracked
        if path.startswith(RUNTIME_PREFIXES)
        and not path.endswith(".gitkeep")
        and "fixtures" not in Path(path).parts
    ]

    assert offenders == []


def test_generated_root_artifacts_are_not_tracked() -> None:
    tracked = git_ls_files()
    offenders = [
        path
        for path in tracked
        if "/" not in path
        and (path in ROOT_GENERATED_FILES or path.endswith(".zip"))
    ]

    assert offenders == []
