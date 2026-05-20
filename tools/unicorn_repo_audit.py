#!/usr/bin/env python3
"""Product-readiness audit for Convergence Monitor."""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    path: str | None = None


RUNTIME_PREFIXES = (
    "data/raw/",
    "data/processed/",
    "data/runs/",
    "data/live_proof_sessions/",
)

ROOT_ARTIFACT_SUFFIXES = (
    ".zip",
    ".tar",
    ".tar.gz",
    ".tgz",
)

ROOT_ARTIFACT_NAMES = (
    "LIVE_HISTORY_OUTPUT.json",
    "LIVE_PROOF_REPORT.md",
    "LIVE_PROOF_REPORT_TERMUX.md",
)


def git_files(root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def audit_tracked_artifacts(root: Path, files: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for rel in files:
        name = Path(rel).name
        if rel.startswith(RUNTIME_PREFIXES):
            findings.append(
                Finding(
                    severity="error",
                    code="tracked-runtime-data",
                    message="Runtime/generated data should not be tracked.",
                    path=rel,
                )
            )
        if "/" not in rel and (name in ROOT_ARTIFACT_NAMES or name.endswith(ROOT_ARTIFACT_SUFFIXES)):
            findings.append(
                Finding(
                    severity="error",
                    code="tracked-root-artifact",
                    message="Generated proof/release artifacts should not live at repo root.",
                    path=rel,
                )
            )
    return findings


def audit_pyproject(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    text = read_text(root / "pyproject.toml")

    if not text:
        return [Finding("error", "missing-pyproject", "Missing pyproject.toml.")]

    if 'include = ["app*"]' in text or 'include=["app*"]' in text:
        findings.append(
            Finding(
                severity="warning",
                code="generic-package-name",
                message="The package include still targets generic `app*`; plan rename to `convergence_monitor*`.",
                path="pyproject.toml",
            )
        )

    for package in ("typer", "pydantic", "httpx", "feedparser"):
        if package not in text:
            findings.append(
                Finding(
                    severity="warning",
                    code="unexpected-dependency-shape",
                    message=f"Expected dependency not visible: {package}.",
                    path="pyproject.toml",
                )
            )

    if "ruff" not in text:
        findings.append(
            Finding(
                severity="warning",
                code="missing-ruff",
                message="Ruff is not declared in dev dependencies.",
                path="pyproject.toml",
            )
        )

    return findings


def audit_cli(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    cli_path = root / "app" / "cli.py"
    if not cli_path.exists():
        cli_path = root / "convergence_monitor" / "cli.py"

    text = read_text(cli_path)
    if not text:
        return [Finding("warning", "missing-cli", "Could not find CLI entrypoint.")]

    lines = text.splitlines()
    if len(lines) > 500:
        findings.append(
            Finding(
                severity="warning",
                code="large-cli-module",
                message=f"CLI entrypoint has {len(lines)} lines; split command handlers into modules.",
                path=str(cli_path.relative_to(root)),
            )
        )

    try:
        tree = ast.parse(text, filename=str(cli_path))
    except SyntaxError as exc:
        findings.append(
            Finding(
                severity="error",
                code="cli-syntax-error",
                message=str(exc),
                path=str(cli_path.relative_to(root)),
            )
        )
        return findings

    command_count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                deco = ast.unparse(decorator) if hasattr(ast, "unparse") else ""
                if ".command" in deco:
                    command_count += 1

    if command_count >= 8 and len(lines) > 400:
        findings.append(
            Finding(
                severity="info",
                code="cli-split-candidate",
                message=f"Found {command_count} Typer commands in one module.",
                path=str(cli_path.relative_to(root)),
            )
        )

    return findings


def audit_tests(root: Path, files: list[str]) -> list[Finding]:
    test_files = [rel for rel in files if rel.startswith("tests/") and rel.endswith(".py")]
    findings: list[Finding] = []

    if len(test_files) < 10:
        findings.append(
            Finding(
                severity="warning",
                code="low-test-file-count",
                message=f"Only {len(test_files)} tracked test files found.",
                path="tests/",
            )
        )

    if not any("contract" in rel for rel in test_files):
        findings.append(
            Finding(
                severity="info",
                code="missing-contract-tests",
                message="Add CLI/API contract tests to protect refactors.",
                path="tests/",
            )
        )

    return findings


def audit_docs(root: Path, files: list[str]) -> list[Finding]:
    required = {
        "SECURITY.md",
        "docs/OPERATIONS_RUNBOOK_PHASE2.md",
        "docs/SCORING_GOVERNANCE_PHASE2.md",
    }
    existing = set(files)
    findings = []
    for rel in sorted(required - existing):
        findings.append(
            Finding(
                severity="info",
                code="missing-doc",
                message="Recommended operational/governance document is missing.",
                path=rel,
            )
        )
    return findings


def audit(root: Path) -> list[Finding]:
    files = git_files(root)
    findings: list[Finding] = []
    findings.extend(audit_tracked_artifacts(root, files))
    findings.extend(audit_pyproject(root))
    findings.extend(audit_cli(root))
    findings.extend(audit_tests(root, files))
    findings.extend(audit_docs(root, files))
    return findings


def print_markdown(findings: list[Finding]) -> None:
    if not findings:
        print("## Unicorn repo audit\n\nNo findings.")
        return

    print("## Unicorn repo audit\n")
    for severity in ("error", "warning", "info"):
        scoped = [finding for finding in findings if finding.severity == severity]
        if not scoped:
            continue
        print(f"### {severity.upper()}\n")
        for finding in scoped:
            path = f" — `{finding.path}`" if finding.path else ""
            print(f"- **{finding.code}**{path}: {finding.message}")
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--fail-on", choices=("error", "warning", "info"), default="error")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    findings = audit(args.root.resolve())

    if args.json:
        print(json.dumps([asdict(finding) for finding in findings], indent=2))
    else:
        print_markdown(findings)

    severity_rank = {"info": 1, "warning": 2, "error": 3}
    threshold = severity_rank[args.fail_on]
    return 1 if any(severity_rank[finding.severity] >= threshold for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
