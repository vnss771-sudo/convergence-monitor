#!/usr/bin/env python3
"""Verify Phase 3 supply-chain artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REQUIRED_SBOM_KEYS = {"bomFormat", "specVersion", "metadata", "components"}
REQUIRED_PROVENANCE_KEYS = {"schema_version", "generated_at", "subject", "builder", "artifacts"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument("--dist-dir", default="dist", help="Distribution artifact directory.")
    parser.add_argument("--sbom", default="convergence-monitor.sbom.cdx.json", help="SBOM filename under dist-dir.")
    parser.add_argument("--provenance", default="release-provenance.json", help="Provenance filename under dist-dir.")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def verify_checksum(path: Path) -> str | None:
    checksum_path = path.with_name(path.name + ".sha256")
    if not checksum_path.exists():
        return f"missing checksum: {checksum_path.name}"

    content = checksum_path.read_text(encoding="utf-8").strip()
    expected = content.split()[0] if content else ""
    actual = sha256_file(path)
    if actual != expected:
        return f"checksum mismatch: {path.name}"
    return None


def verify(root: Path, dist_dir: Path, sbom_name: str, provenance_name: str) -> list[str]:
    errors: list[str] = []

    if not dist_dir.exists():
        return [f"missing dist directory: {dist_dir}"]

    sbom_path = dist_dir / sbom_name
    provenance_path = dist_dir / provenance_name

    if not sbom_path.exists():
        errors.append(f"missing SBOM: {sbom_path}")
    else:
        try:
            sbom = load_json(sbom_path)
            missing = REQUIRED_SBOM_KEYS - set(sbom)
            if missing:
                errors.append(f"SBOM missing keys: {', '.join(sorted(missing))}")
            if sbom.get("bomFormat") != "CycloneDX":
                errors.append("SBOM bomFormat must be CycloneDX")
        except Exception as exc:
            errors.append(f"invalid SBOM JSON: {exc}")

    if not provenance_path.exists():
        errors.append(f"missing provenance: {provenance_path}")
    else:
        try:
            provenance = load_json(provenance_path)
            missing = REQUIRED_PROVENANCE_KEYS - set(provenance)
            if missing:
                errors.append(f"provenance missing keys: {', '.join(sorted(missing))}")
            for artifact in provenance.get("artifacts", []):
                artifact_path = dist_dir / artifact.get("path", "")
                if not artifact_path.exists():
                    errors.append(f"provenance references missing artifact: {artifact.get('path')}")
                    continue
                actual = sha256_file(artifact_path)
                if actual != artifact.get("sha256"):
                    errors.append(f"provenance sha256 mismatch: {artifact.get('path')}")
        except Exception as exc:
            errors.append(f"invalid provenance JSON: {exc}")

    for artifact in sorted(dist_dir.iterdir()):
        if not artifact.is_file():
            continue
        if artifact.suffix == ".sha256" or artifact.name == provenance_name:
            continue
        checksum_error = verify_checksum(artifact)
        if checksum_error:
            errors.append(checksum_error)

    return errors


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    dist_dir = Path(args.dist_dir)
    if not dist_dir.is_absolute():
        dist_dir = root / dist_dir

    errors = verify(root, dist_dir, args.sbom, args.provenance)

    if args.format == "json":
        print(json.dumps({"status": "error" if errors else "ok", "errors": errors}, indent=2))
    elif errors:
        print("supply-chain artifact verification: failed")
        for error in errors:
            print(f"- {error}")
    else:
        print("supply-chain artifact verification: passed")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
