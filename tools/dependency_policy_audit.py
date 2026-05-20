#!/usr/bin/env python3
"""Audit Python dependency specifications for release reproducibility risks."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
import json
from pathlib import Path
import re
import sys
import tomllib
from typing import Any


@dataclass(frozen=True)
class Finding:
    dependency: str
    group: str
    severity: str
    rule_id: str
    message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument("--format", choices=["text", "markdown", "json"], default="text")
    parser.add_argument(
        "--fail-on",
        choices=["none", "medium", "high"],
        default="high",
        help="Exit nonzero at or above this severity.",
    )
    return parser.parse_args()


def read_pyproject(root: Path) -> dict[str, Any]:
    path = root / "pyproject.toml"
    if not path.exists():
        raise FileNotFoundError(f"missing pyproject.toml: {path}")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def dependency_groups(pyproject: dict[str, Any]) -> dict[str, list[str]]:
    project = pyproject.get("project", {})
    groups: dict[str, list[str]] = {"runtime": [str(dep) for dep in project.get("dependencies", []) or []]}

    for group, deps in (project.get("optional-dependencies", {}) or {}).items():
        groups[f"optional:{group}"] = [str(dep) for dep in deps or []]

    return groups


def has_operator(spec: str, operator: str) -> bool:
    return operator in spec.replace(" ", "")


def is_direct_reference(spec: str) -> bool:
    return " @ " in spec or re.search(r"\s@\s*(git\+|https?://|file:)", spec, flags=re.IGNORECASE) is not None


def has_wildcard(spec: str) -> bool:
    return "*" in spec


def has_prerelease_pin(spec: str) -> bool:
    return re.search(r"(a|b|rc)\d+\b", spec, flags=re.IGNORECASE) is not None


def audit_dependency(spec: str, group: str) -> list[Finding]:
    findings: list[Finding] = []
    compact = spec.replace(" ", "")

    if is_direct_reference(spec):
        findings.append(
            Finding(
                dependency=spec,
                group=group,
                severity="high",
                rule_id="direct-reference",
                message="Direct URL/path dependencies reduce reproducibility and should be reviewed.",
            )
        )

    if has_wildcard(spec):
        findings.append(
            Finding(
                dependency=spec,
                group=group,
                severity="high",
                rule_id="wildcard-version",
                message="Wildcard dependency versions are not release-stable.",
            )
        )

    if "==" not in compact:
        findings.append(
            Finding(
                dependency=spec,
                group=group,
                severity="medium",
                rule_id="not-fully-pinned",
                message="Release builds should use a generated constraints file with exact versions.",
            )
        )

    if ">=" in compact and "<" not in compact:
        findings.append(
            Finding(
                dependency=spec,
                group=group,
                severity="medium",
                rule_id="no-upper-bound",
                message="Lower-bound-only specs can break unexpectedly as upstream packages change.",
            )
        )

    if has_prerelease_pin(spec):
        findings.append(
            Finding(
                dependency=spec,
                group=group,
                severity="medium",
                rule_id="pre-release",
                message="Pre-release dependency versions should be intentional and documented.",
            )
        )

    return findings


def audit(root: Path) -> list[Finding]:
    pyproject = read_pyproject(root)
    findings: list[Finding] = []
    for group, dependencies in dependency_groups(pyproject).items():
        for spec in dependencies:
            findings.extend(audit_dependency(spec, group))
    return findings


def severity_rank(severity: str) -> int:
    return {"none": 99, "medium": 1, "high": 2}[severity]


def should_fail(findings: list[Finding], fail_on: str) -> bool:
    if fail_on == "none":
        return False
    threshold = severity_rank(fail_on)
    return any(severity_rank(finding.severity) >= threshold for finding in findings)


def print_text(findings: list[Finding]) -> None:
    if not findings:
        print("dependency policy audit: passed")
        return
    print(f"dependency policy audit: {len(findings)} finding(s)")
    for finding in findings:
        print(
            f"{finding.severity.upper()} {finding.rule_id} [{finding.group}] "
            f"{finding.dependency}: {finding.message}"
        )


def print_markdown(findings: list[Finding]) -> None:
    if not findings:
        print("## Dependency policy audit\n\nPassed.")
        return
    print("## Dependency policy audit")
    print()
    print(f"Findings: **{len(findings)}**")
    print()
    print("| Severity | Rule | Group | Dependency | Message |")
    print("|---|---|---|---|---|")
    for finding in findings:
        dep = finding.dependency.replace("|", "\\|")
        msg = finding.message.replace("|", "\\|")
        print(f"| {finding.severity} | `{finding.rule_id}` | `{finding.group}` | `{dep}` | {msg} |")


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    findings = audit(root)

    if args.format == "json":
        print(json.dumps([asdict(finding) for finding in findings], indent=2, sort_keys=True))
    elif args.format == "markdown":
        print_markdown(findings)
    else:
        print_text(findings)

    return 1 if should_fail(findings, args.fail_on) else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"dependency_policy_audit.py: error: {exc}", file=sys.stderr)
        raise SystemExit(1)
