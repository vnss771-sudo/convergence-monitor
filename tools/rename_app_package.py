#!/usr/bin/env python3
"""Dry-run or execute the app -> convergence_monitor package rename."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


TEXT_SUFFIXES = {
    ".py",
    ".toml",
    ".md",
    ".yml",
    ".yaml",
    ".json",
    ".sh",
    ".txt",
}

REPLACEMENTS = (
    ("python -m app.cli", "python -m convergence_monitor.cli"),
    ("from app.", "from convergence_monitor."),
    ("import app.", "import convergence_monitor."),
    ('include = ["app*"]', 'include = ["convergence_monitor*"]'),
    ("app/cli.py", "convergence_monitor/cli.py"),
    ("app/", "convergence_monitor/"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def should_edit(path: Path) -> bool:
    if ".git" in path.parts:
        return False
    if path.suffix not in TEXT_SUFFIXES:
        return False
    return path.is_file()


def transform(text: str) -> str:
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    return text


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    old_dir = root / "app"
    new_dir = root / "convergence_monitor"

    changes: list[str] = []

    if not old_dir.exists():
        raise SystemExit(f"missing package directory: {old_dir}")
    if new_dir.exists():
        raise SystemExit(f"target already exists: {new_dir}")

    changes.append("move app/ -> convergence_monitor/")

    edited_files: list[Path] = []
    for path in root.rglob("*"):
        if not should_edit(path):
            continue
        original = path.read_text(encoding="utf-8")
        updated = transform(original)
        if updated != original:
            edited_files.append(path)
            changes.append(f"edit {path.relative_to(root)}")

    print("\n".join(changes))

    if not args.execute:
        print("\nDry run only. Re-run with --execute to apply.")
        return 0

    shutil.move(str(old_dir), str(new_dir))

    for path in edited_files:
        target = path
        try:
            relative_to_old = path.relative_to(old_dir)
            target = new_dir / relative_to_old
        except ValueError:
            pass
        original = target.read_text(encoding="utf-8")
        target.write_text(transform(original), encoding="utf-8")

    print("\nApplied package rename. Run pytest and ruff now.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
