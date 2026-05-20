#!/usr/bin/env python3
"""Generate a minimal CycloneDX-style SBOM from pyproject.toml.

This is a fallback SBOM generator for Termux and lean CI environments. For formal
release evidence, prefer CycloneDX Python in CI and keep this tool as an
offline/verifiability baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tomllib
from typing import Any


CYCLONEDX_SCHEMA = "http://cyclonedx.org/schema/bom-1.5.schema.json"
DEFAULT_OUTPUT = "dist/convergence-monitor.sbom.cdx.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output SBOM JSON path.")
    parser.add_argument("--include-dev", action="store_true", help="Include optional dev dependencies.")
    parser.add_argument("--pretty", action="store_true", default=True, help="Pretty-print JSON.")
    return parser.parse_args()


def read_pyproject(root: Path) -> dict[str, Any]:
    path = root / "pyproject.toml"
    if not path.exists():
        raise FileNotFoundError(f"missing pyproject.toml: {path}")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def split_dependency(spec: str) -> tuple[str, str | None]:
    cleaned = spec.strip()
    if not cleaned:
        return "", None

    cleaned = cleaned.split(";", 1)[0].strip()
    cleaned = cleaned.split("[", 1)[0].strip()

    direct_match = re.match(r"^([A-Za-z0-9_.-]+)\s*@\s*(.+)$", cleaned)
    if direct_match:
        return direct_match.group(1), None

    match = re.match(r"^([A-Za-z0-9_.-]+)\s*(.*)$", cleaned)
    if not match:
        return cleaned, None

    name = match.group(1)
    version_expr = match.group(2).strip()
    pinned_match = re.search(r"==\s*([A-Za-z0-9_.!+*-]+)", version_expr)
    version = pinned_match.group(1) if pinned_match else None
    return name, version


def purl_for(name: str, version: str | None) -> str:
    normalized = normalize_name(name)
    if version:
        return f"pkg:pypi/{normalized}@{version}"
    return f"pkg:pypi/{normalized}"


def component_from_dependency(spec: str, scope: str) -> dict[str, Any] | None:
    name, version = split_dependency(spec)
    if not name:
        return None

    component: dict[str, Any] = {
        "type": "library",
        "bom-ref": f"pkg:pypi/{normalize_name(name)}",
        "name": normalize_name(name),
        "scope": scope,
        "purl": purl_for(name, version),
        "properties": [{"name": "source.specifier", "value": spec}],
    }
    if version:
        component["version"] = version
    return component


def collect_components(pyproject: dict[str, Any], include_dev: bool) -> list[dict[str, Any]]:
    project = pyproject.get("project", {})
    components: list[dict[str, Any]] = []

    for dependency in project.get("dependencies", []) or []:
        component = component_from_dependency(str(dependency), "required")
        if component:
            components.append(component)

    optional = project.get("optional-dependencies", {}) or {}
    for group_name, dependencies in optional.items():
        if group_name != "dev" and not include_dev:
            continue
        for dependency in dependencies:
            component = component_from_dependency(str(dependency), "optional")
            if component:
                component["properties"].append({"name": "optional.group", "value": str(group_name)})
                components.append(component)

    seen: dict[str, dict[str, Any]] = {}
    for component in components:
        seen[component["bom-ref"]] = component
    return sorted(seen.values(), key=lambda item: item["name"])


def collect_source_hashes(root: Path) -> list[dict[str, str]]:
    candidates = [
        root / "pyproject.toml",
        root / "README.md",
        root / "app",
        root / "convergence_monitor",
        root / "config",
        root / "scripts",
    ]
    files: list[Path] = []
    for candidate in candidates:
        if candidate.is_file():
            files.append(candidate)
        elif candidate.is_dir():
            for path in candidate.rglob("*"):
                if path.is_file() and should_hash(path):
                    files.append(path)

    entries = []
    for path in sorted(set(files)):
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
            }
        )
    return entries


def should_hash(path: Path) -> bool:
    ignored_parts = {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
    }
    if any(part in ignored_parts for part in path.parts):
        return False
    return path.suffix in {".py", ".toml", ".yaml", ".yml", ".json", ".md", ".sh"}


def build_bom(root: Path, include_dev: bool) -> dict[str, Any]:
    pyproject = read_pyproject(root)
    project = pyproject.get("project", {})
    name = str(project.get("name", "convergence-monitor"))
    version = str(project.get("version", "0.0.0+unknown"))
    root_ref = f"pkg:pypi/{normalize_name(name)}@{version}"

    components = collect_components(pyproject, include_dev=include_dev)
    dependencies = [{"ref": root_ref, "dependsOn": [component["bom-ref"] for component in components]}]

    return {
        "$schema": CYCLONEDX_SCHEMA,
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{stable_uuid(root, version)}",
        "version": 1,
        "metadata": {
            "timestamp": utc_now(),
            "tools": [
                {
                    "vendor": "convergence-monitor",
                    "name": "generate_minimal_sbom.py",
                    "version": "phase3",
                }
            ],
            "component": {
                "type": "application",
                "bom-ref": root_ref,
                "name": name,
                "version": version,
                "purl": root_ref,
            },
            "properties": [
                {
                    "name": "note",
                    "value": "Minimal SBOM from pyproject.toml; use CycloneDX Python in CI for richer SBOMs.",
                }
            ],
        },
        "components": components,
        "dependencies": dependencies,
        "properties": [
            {"name": "source.file_hash_count", "value": str(len(collect_source_hashes(root)))},
        ],
        "externalReferences": [
            {
                "type": "other",
                "url": "file://SOURCE_HASHES_EMBEDDED_IN_PROPERTIES",
                "comment": "See x-source-hashes extension property.",
            }
        ],
        "x-source-hashes": collect_source_hashes(root),
    }


def stable_uuid(root: Path, version: str) -> str:
    material = f"{root.resolve()}:{version}".encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)

    bom = build_bom(root, include_dev=args.include_dev)
    output.write_text(json.dumps(bom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote SBOM: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"generate_minimal_sbom.py: error: {exc}", file=sys.stderr)
        raise SystemExit(1)
