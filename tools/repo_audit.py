#!/usr/bin/env python3
"""Audit Convergence Monitor repository hygiene and release readiness."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


GENERATED_PATTERNS = (
    "LIVE_HISTORY_OUTPUT.json",
    "LIVE_PROOF_REPORT.md",
    "LIVE_PROOF_REPORT_TERMUX.md",
    "convergence-monitor-live-proof-results",
    "data/raw/",
    "data/processed/",
    "data/runs/",
    "data/live_proof_sessions/",
    "dist/",
    "build/",
    ".pytest_cache/",
    ".ruff_cache/",
)

REQUIRED_FILES = (
    ".gitattributes",
    ".editorconfig",
    "SECURITY.md",
    ".github/dependabot.yml",
    ".github/pull_request_template.md",
    ".github/workflows/ci.yml",
    ".github/workflows/security.yml",
    ".github/workflows/release.yml",
    "scripts/release/build_pinned_source_zip.sh",
    "scripts/release/make_zip_from_existing_repo.sh",
)

FLOATING_DEP_RE = re.compile(r'^\s*"[^"]+>=', re.MULTILINE)
ACTION_USES_RE = re.compile(r"uses:\s*([^@\s]+)@([^\s#]+)")


@dataclass(frozen=True)
class Finding:
    severity: str
    check: str
    message: str
    recommendation: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--markdown", action="store_true")
    return parser.parse_args()


def run_git(root: Path, *args: str) -> tuple[int, str, str]:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def tracked_files(root: Path) -> list[str]:
    code, stdout, _ = run_git(root, "ls-files")
    if code != 0:
        return []
    return [line for line in stdout.splitlines() if line]


def is_dirty(root: Path) -> bool:
    code, stdout, _ = run_git(root, "status", "--porcelain")
    return code == 0 and bool(stdout.strip())


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def add_missing_file_findings(root: Path, findings: list[Finding]) -> None:
    for relative in REQUIRED_FILES:
        if not (root / relative).exists():
            findings.append(
                Finding(
                    "high" if relative.startswith(".github/workflows") else "medium",
                    "required-file",
                    f"Missing {relative}",
                    "Apply the hardening kit or add an equivalent file.",
                )
            )


def add_generated_artifact_findings(files: Iterable[str], findings: list[Finding]) -> None:
    tracked_generated = [
        path
        for path in files
        if any(path == pattern or path.startswith(pattern) or pattern in path for pattern in GENERATED_PATTERNS)
    ]
    if tracked_generated:
        findings.append(
            Finding(
                "high",
                "tracked-generated-artifacts",
                "Generated/runtime artifacts are tracked: " + ", ".join(tracked_generated[:20]),
                "Run scripts/clean_runtime_artifacts.sh --execute, then commit the removals.",
            )
        )


def add_package_findings(root: Path, findings: list[Finding]) -> None:
    pyproject = read_text(root / "pyproject.toml")
    if (root / "app").exists():
        findings.append(
            Finding(
                "medium",
                "generic-package-name",
                "Top-level package is named 'app'.",
                "Rename to convergence_monitor in a dedicated refactor PR.",
            )
        )
    if 'include = ["app*"]' in pyproject:
        findings.append(
            Finding(
                "medium",
                "setuptools-package-include",
                "pyproject.toml packages include app*.",
                "After migration, use include = ['convergence_monitor*'].",
            )
        )


def add_cli_size_findings(root: Path, findings: list[Finding]) -> None:
    cli = root / "app" / "cli.py"
    if not cli.exists():
        return
    lines = cli.read_text(encoding="utf-8").splitlines()
    if len(lines) > 500:
        findings.append(
            Finding(
                "medium",
                "large-cli-module",
                f"app/cli.py has {len(lines)} lines.",
                "Split Typer command handlers into app/commands/*.py while preserving CLI behavior.",
            )
        )


def add_dependency_findings(root: Path, findings: list[Finding]) -> None:
    pyproject = read_text(root / "pyproject.toml")
    if FLOATING_DEP_RE.search(pyproject):
        findings.append(
            Finding(
                "medium",
                "floating-dependency-bounds",
                "pyproject.toml uses lower-bound-only dependencies.",
                "Keep lower bounds for libraries, but generate constraints.txt for releases.",
            )
        )


def add_workflow_findings(root: Path, findings: list[Finding]) -> None:
    workflows_dir = root / ".github" / "workflows"
    if not workflows_dir.exists():
        return

    for workflow in workflows_dir.glob("*.yml"):
        text = read_text(workflow)
        for action, version in ACTION_USES_RE.findall(text):
            if re.fullmatch(r"[0-9a-f]{40}", version):
                continue
            findings.append(
                Finding(
                    "low",
                    "workflow-action-not-sha-pinned",
                    f"{workflow.relative_to(root)} uses {action}@{version}.",
                    "Major-version pins are common; for maximum supply-chain hardening, pin full SHAs with a scheduled updater.",
                )
            )


def audit(root: Path) -> list[Finding]:
    findings: list[Finding] = []

    if not (root / ".git").exists():
        findings.append(
            Finding(
                "critical",
                "not-git-root",
                f"{root} does not look like a git repository root.",
                "Run from the repository root or pass --root.",
            )
        )
        return findings

    if is_dirty(root):
        findings.append(
            Finding(
                "low",
                "dirty-working-tree",
                "Working tree has uncommitted changes.",
                "Review git status before release packaging.",
            )
        )

    files = tracked_files(root)
    add_missing_file_findings(root, findings)
    add_generated_artifact_findings(files, findings)
    add_package_findings(root, findings)
    add_cli_size_findings(root, findings)
    add_dependency_findings(root, findings)
    add_workflow_findings(root, findings)
    return findings


def print_markdown(findings: list[Finding]) -> None:
    if not findings:
        print("# Repo audit\n\nNo findings.")
        return

    print("# Repo audit\n")
    for severity in ("critical", "high", "medium", "low"):
        subset = [finding for finding in findings if finding.severity == severity]
        if not subset:
            continue
        print(f"## {severity.title()}\n")
        for finding in subset:
            print(f"- **{finding.check}**: {finding.message}")
            print(f"  - Fix: {finding.recommendation}")
        print()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    findings = audit(root)

    if args.json_output:
        print(json.dumps([asdict(finding) for finding in findings], indent=2, sort_keys=True))
    else:
        print_markdown(findings)

    return 1 if any(f.severity in {"critical", "high"} for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
