#!/usr/bin/env python3
"""Generate local release provenance with git metadata and artifact hashes."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any


DEFAULT_OUTPUT = "dist/release-provenance.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument("--dist-dir", default="dist", help="Distribution artifact directory.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output JSON path.")
    parser.add_argument("--allow-dirty", action="store_true", help="Allow dirty git working tree.")
    return parser.parse_args()


def git(root: Path, *args: str, default: str = "") -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return default


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dirty_lines_excluding_dist(root: Path, dist_dir: Path) -> list[str]:
    raw = git(root, "status", "--porcelain", "--untracked-files=all", default="")
    if not raw:
        return []

    try:
        dist_relative = dist_dir.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        dist_relative = ""

    filtered: list[str] = []
    for line in raw.splitlines():
        path_text = line[3:] if len(line) > 3 else line
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1]
        if dist_relative and (path_text == dist_relative or path_text.startswith(dist_relative + "/")):
            continue
        filtered.append(line)
    return filtered


def artifact_entries(dist_dir: Path) -> list[dict[str, Any]]:
    if not dist_dir.exists():
        return []

    excluded_suffixes = {".sha256"}
    excluded_names = {"release-provenance.json"}
    entries: list[dict[str, Any]] = []

    for path in sorted(dist_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name in excluded_names:
            continue
        if path.suffix in excluded_suffixes:
            continue
        entries.append(
            {
                "name": path.name,
                "path": path.relative_to(dist_dir).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return entries


def write_checksum_files(dist_dir: Path, artifacts: list[dict[str, Any]]) -> None:
    for artifact in artifacts:
        path = dist_dir / artifact["path"]
        checksum_path = path.with_name(path.name + ".sha256")
        checksum_path.write_text(f"{artifact['sha256']}  {path.name}\n", encoding="utf-8")


def build_provenance(root: Path, dist_dir: Path, allow_dirty: bool) -> dict[str, Any]:
    dirty_lines = dirty_lines_excluding_dist(root, dist_dir)
    if dirty_lines and not allow_dirty:
        dirty_preview = "\n".join(dirty_lines[:20])
        raise RuntimeError(
            "git working tree is dirty outside the release dist directory; "
            "commit/stash changes or pass --allow-dirty\n"
            + dirty_preview
        )
    dirty_status = "\n".join(dirty_lines)

    commit = git(root, "rev-parse", "HEAD", default="unknown")
    tag = git(root, "describe", "--tags", "--exact-match", default="")
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD", default="unknown")
    remote = git(root, "config", "--get", "remote.origin.url", default="")
    artifacts = artifact_entries(dist_dir)
    write_checksum_files(dist_dir, artifacts)

    github = {
        "repository": os.environ.get("GITHUB_REPOSITORY", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        "workflow": os.environ.get("GITHUB_WORKFLOW", ""),
        "ref": os.environ.get("GITHUB_REF", ""),
        "sha": os.environ.get("GITHUB_SHA", ""),
        "actor": os.environ.get("GITHUB_ACTOR", ""),
    }

    return {
        "schema_version": "convergence-monitor.phase3.provenance.v1",
        "generated_at": utc_now(),
        "subject": {
            "name": "convergence-monitor",
            "git_commit": commit,
            "git_branch": branch,
            "git_tag": tag,
            "git_remote": remote,
            "git_dirty": bool(dirty_status),
        },
        "builder": {
            "kind": "local-or-github-actions",
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
            "executable": sys.executable,
        },
        "github_actions": github,
        "artifacts": artifacts,
        "materials": [
            {
                "uri": remote or "local-git-repository",
                "digest": {"sha1": commit},
            }
        ],
        "predicate": {
            "build_type": "python-source-wheel-or-local-release",
            "checks": [
                "guardrail_language_audit",
                "dependency_policy_audit",
                "minimal_sbom_generation",
                "artifact_sha256_generation",
            ],
            "limitations": [
                "This JSON is local provenance, not a cryptographic attestation.",
                "Use GitHub artifact attestations for signed build provenance on tagged releases.",
            ],
        },
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    dist_dir = Path(args.dist_dir)
    if not dist_dir.is_absolute():
        dist_dir = root / dist_dir
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output

    dist_dir.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    provenance = build_provenance(root, dist_dir, allow_dirty=args.allow_dirty)
    output.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote provenance: {output}")
    print(f"hashed artifacts: {len(provenance['artifacts'])}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"generate_release_provenance.py: error: {exc}", file=sys.stderr)
        raise SystemExit(1)
