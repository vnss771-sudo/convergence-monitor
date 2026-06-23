#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

AUDIT_EXTENSIONS = {
    ".md",
    ".txt",
    ".yml",
    ".yaml",
    ".json",
}

EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "ci_fail_logs",
    "htmlcov",
    "node_modules",
    "venv",
    ".venv",
}

# Code, tests, fixtures, and internal operations docs may legitimately contain
# technical terms such as signal, forecast, prediction, and causal examples.
# This audit is for outward-facing / policy-facing wording only.
EXCLUDED_TOP_LEVEL_DIRS = {
    "app",
    "tests",
    "tools",
}

# docs/history/ (archived process logs) and docs/reports/ (internal engineering
# audits and build plans) are not outward-facing/policy-facing copy; they
# legitimately discuss terms like "forecast", "prediction", and "confirm" while
# analyzing the methodology, so the non-speculative guardrail does not apply.
EXCLUDED_PATH_PREFIXES = (
    ("docs", "history"),
    ("docs", "reports"),
)

EXCLUDED_RELATIVE_PATHS = {
    Path("SECURITY.md"),
    Path("tools/guardrail_language_audit.py"),
    Path("docs/GUARDRAIL_LANGUAGE_POLICY.md"),
    Path("docs/ARCHITECTURE_NEXT.md"),
    Path("docs/INCIDENT_RESPONSE.md"),
    Path("docs/OPERATOR_RUNBOOK.md"),
    Path("docs/OPERATIONS_RUNBOOK.md"),
    Path("docs/SCORING_GOVERNANCE_PHASE2.md"),
}


@dataclass(frozen=True)
class Rule:
    rule_id: str
    pattern: re.Pattern[str]
    message: str


RULES = [
    Rule(
        "predictive-framing",
        re.compile(
            r"\b(infer|infers|inferred|inferring|prove|proves|proved|proving)\s+"
            r"(intent|motive|coordination|causation)\b",
            re.IGNORECASE,
        ),
        "Use observable public-document convergence language instead of predictive framing.",
    ),
    Rule(
        "predictive-framing",
        re.compile(
            r"\b(predicts?|forecast[s]?|foresees?|proves?|confirms?)\b",
            re.IGNORECASE,
        ),
        "Use observable public-document convergence language instead of predictive framing.",
    ),
    Rule(
        "causal-overclaim",
        re.compile(
            r"\b(caused\s+by|because\s+of\s+coordination|coordinated\s+effort|orchestrated|engineered)\b",
            re.IGNORECASE,
        ),
        "Avoid causation or coordination overclaims.",
    ),
    Rule(
        "trading-framing",
        re.compile(
            r"\b(buy\s+signal|sell\s+signal|trade\s+signal|market\s+prediction|price\s+target)\b",
            re.IGNORECASE,
        ),
        "Avoid trading or market-prediction language.",
    ),
]


def rel(path: Path) -> Path:
    return path.resolve().relative_to(ROOT)


def is_excluded(path: Path) -> bool:
    try:
        relative = rel(path)
    except ValueError:
        return True

    if relative in EXCLUDED_RELATIVE_PATHS:
        return True

    if any(relative.parts[: len(prefix)] == prefix for prefix in EXCLUDED_PATH_PREFIXES):
        return True

    if relative.parts and relative.parts[0] in EXCLUDED_TOP_LEVEL_DIRS:
        return True

    parts = set(relative.parts)
    return bool(parts & EXCLUDED_DIRS)


def iter_default_files() -> list[Path]:
    roots = [
        ROOT / "docs",
        ROOT / ".github",
    ]

    files: list[Path] = []

    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in AUDIT_EXTENSIONS and not is_excluded(path):
                files.append(path)

    for path in ROOT.glob("*.md"):
        if path.is_file() and not is_excluded(path):
            files.append(path)

    return sorted(set(files))


def iter_arg_files(args: list[str]) -> list[Path]:
    files: list[Path] = []

    for arg in args:
        path = (ROOT / arg).resolve()
        if not path.exists():
            continue

        if path.is_file():
            if path.suffix in AUDIT_EXTENSIONS and not is_excluded(path):
                files.append(path)
            continue

        for child in path.rglob("*"):
            if child.is_file() and child.suffix in AUDIT_EXTENSIONS and not is_excluded(child):
                files.append(child)

    return sorted(set(files))


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def main() -> int:
    files = iter_arg_files(sys.argv[1:]) if len(sys.argv) > 1 else iter_default_files()

    warnings = 0

    for path in files:
        text = read_text(path)
        relative = rel(path)

        for line_no, line in enumerate(text.splitlines(), start=1):
            for rule in RULES:
                for match in rule.pattern.finditer(line):
                    warnings += 1
                    column = match.start() + 1
                    print(
                        f"{relative}:{line_no}:{column}: WARNING {rule.rule_id}: {rule.message}"
                    )

    if warnings:
        print(f"guardrail_language_audit: {warnings} warning(s) found", file=sys.stderr)
        return 1

    print("guardrail_language_audit: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
