#!/usr/bin/env python3
"""Audit source/docs for speculative intent, causation, and prediction language."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
import json
from pathlib import Path
import re
import sys


SCAN_SUFFIXES = {".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json"}
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
    "htmlcov",
    "node_modules",
    "data/raw",
    "data/processed",
    "data/runs",
    "data/live_proof_sessions",
}

ALLOW_NEGATION_RE = re.compile(
    r"\b("
    r"does\s+not|do\s+not|did\s+not|cannot|can\s+not|never|no|not|without|"
    r"doesn't|don't|didn't"
    r")\b",
    re.IGNORECASE,
)

RULES = [
    {
        "id": "hidden-intent",
        "severity": "error",
        "pattern": r"\b(hidden|secret|covert)\s+(intent|agenda|plan|coordination|strategy)\b",
        "message": "Avoid hidden-intent or secret-plan claims.",
    },
    {
        "id": "intent-inference",
        "severity": "error",
        "pattern": r"\b(infer|infers|inferred|inferring|prove|proves|proved|proving)\s+(intent|motive|coordination|causation)\b",
        "message": "Do not claim the system infers or proves intent, motive, coordination, or causation.",
    },
    {
        "id": "prediction-certainty",
        "severity": "error",
        "pattern": r"\b(will|guaranteed|certainly|inevitably|inevitable|definitely)\s+(happen|occur|collapse|fail|trigger|cause|lead\s+to)\b",
        "message": "Avoid certain future-event claims.",
    },
    {
        "id": "predictive-framing",
        "severity": "warning",
        "pattern": r"\b(predicts?|forecast[s]?|foresees?|signals?|proves?|confirms?)\b",
        "message": "Use observable public-document convergence language instead of predictive framing.",
    },
    {
        "id": "causal-overclaim",
        "severity": "warning",
        "pattern": r"\b(caused\s+by|because\s+of\s+coordination|coordinated\s+effort|orchestrated|engineered)\b",
        "message": "Avoid causation or coordination overclaims.",
    },
    {
        "id": "market-trading-framing",
        "severity": "warning",
        "pattern": r"\b(buy\s+signal|sell\s+signal|trade\s+signal|market\s+prediction|price\s+target)\b",
        "message": "Avoid market trading or price prediction framing.",
    },
]


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    column: int
    rule_id: str
    severity: str
    message: str
    excerpt: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument("--format", choices=["text", "markdown", "json"], default="text")
    parser.add_argument(
        "--fail-on",
        choices=["none", "warning", "error"],
        default="error",
        help="Exit nonzero at or above this severity.",
    )
    parser.add_argument("--include-dist", action="store_true", help="Scan dist/build directories too.")
    return parser.parse_args()


def should_skip(path: Path, root: Path, include_dist: bool) -> bool:
    relative = path.relative_to(root).as_posix()
    parts = set(path.relative_to(root).parts)

    if path.suffix not in SCAN_SUFFIXES:
        return True

    for skip in SKIP_DIRS:
        if include_dist and skip in {"build", "dist"}:
            continue
        if relative == skip or relative.startswith(skip + "/"):
            return True

    if parts & {".git", ".venv", "venv", "__pycache__", "node_modules"}:
        return True

    return False


def is_negated(line: str, match_start: int) -> bool:
    window = line[max(0, match_start - 42) : match_start]
    return bool(ALLOW_NEGATION_RE.search(window))


def audit_file(path: Path, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")

    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue

        for rule in RULES:
            for match in re.finditer(rule["pattern"], line, flags=re.IGNORECASE):
                if is_negated(line, match.start()):
                    continue
                findings.append(
                    Finding(
                        path=path.relative_to(root).as_posix(),
                        line=line_no,
                        column=match.start() + 1,
                        rule_id=rule["id"],
                        severity=rule["severity"],
                        message=rule["message"],
                        excerpt=stripped[:240],
                    )
                )
    return findings


def audit(root: Path, include_dist: bool) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and not should_skip(path, root, include_dist):
            findings.extend(audit_file(path, root))
    return findings


def severity_rank(severity: str) -> int:
    return {"none": 99, "warning": 1, "error": 2}[severity]


def should_fail(findings: list[Finding], fail_on: str) -> bool:
    if fail_on == "none":
        return False
    threshold = severity_rank(fail_on)
    return any(severity_rank(finding.severity) >= threshold for finding in findings)


def print_text(findings: list[Finding]) -> None:
    if not findings:
        print("guardrail language audit: passed")
        return

    print(f"guardrail language audit: {len(findings)} finding(s)")
    for finding in findings:
        print(
            f"{finding.path}:{finding.line}:{finding.column}: "
            f"{finding.severity.upper()} {finding.rule_id}: {finding.message}"
        )
        print(f"  {finding.excerpt}")


def print_markdown(findings: list[Finding]) -> None:
    if not findings:
        print("## Guardrail language audit\n\nPassed.")
        return

    print("## Guardrail language audit")
    print()
    print(f"Findings: **{len(findings)}**")
    print()
    print("| Severity | Rule | Location | Excerpt |")
    print("|---|---|---|---|")
    for finding in findings:
        excerpt = finding.excerpt.replace("|", "\\|")
        print(
            f"| {finding.severity} | `{finding.rule_id}` | "
            f"`{finding.path}:{finding.line}:{finding.column}` | {excerpt} |"
        )


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    findings = audit(root, include_dist=args.include_dist)

    if args.format == "json":
        print(json.dumps([asdict(finding) for finding in findings], indent=2, sort_keys=True))
    elif args.format == "markdown":
        print_markdown(findings)
    else:
        print_text(findings)

    return 1 if should_fail(findings, args.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
