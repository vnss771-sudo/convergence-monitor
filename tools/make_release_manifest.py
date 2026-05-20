#!/usr/bin/env python3
"""Create a deterministic SHA-256 manifest for a source tree."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path


EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    ".venv",
    "venv",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".zip",
    ".whl",
    ".gz",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("SOURCE_MANIFEST.json"))
    parser.add_argument("--commit", default="")
    return parser.parse_args()


def should_skip(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in EXCLUDED_DIRS for part in rel.parts):
        return True
    if path.suffix in EXCLUDED_SUFFIXES:
        return True
    if path.name == "SOURCE_MANIFEST.json":
        return True
    return False


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    files = []

    for path in sorted(root.rglob("*")):
        if not path.is_file() or should_skip(path, root):
            continue
        rel = path.relative_to(root).as_posix()
        files.append(
            {
                "path": rel,
                "size_bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )

    payload = {
        "schema_version": 1,
        "generated_at_utc": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "commit": args.commit,
        "file_count": len(files),
        "files": files,
    }

    output = args.output if args.output.is_absolute() else root / args.output
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
