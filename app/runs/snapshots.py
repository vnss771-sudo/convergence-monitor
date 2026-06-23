from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.persistence import utc_now_iso, write_json_atomic

__all__ = ["utc_now_iso", "write_json_atomic"]  # re-exported for existing importers


def safe_timestamp(value: str) -> str:
    return value.replace("-", "").replace(":", "").replace("+00:00", "Z")


def stable_hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return stable_hash_bytes(path.read_bytes())


def config_hashes(config_dir: Path | str = Path("config")) -> dict[str, str | None]:
    base = Path(config_dir)
    return {
        "scenarios_yaml": file_sha256(base / "scenarios.yaml"),
        "sources_yaml": file_sha256(base / "sources.yaml"),
    }


def make_run_id(
    *,
    operation: str,
    subject: str,
    timestamp: str | None = None,
    window_days: int | None = None,
) -> str:
    created_at = timestamp or utc_now_iso()
    suffix = f"_{window_days}d" if window_days is not None else ""
    return f"{safe_timestamp(created_at)}_{operation}_{subject}{suffix}"


def write_run_snapshot(
    *,
    runs_dir: Path | str = Path("data/runs"),
    operation: str,
    subject: str,
    status: str,
    parameters: dict[str, Any] | None = None,
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
    counts: dict[str, Any] | None = None,
    config_dir: Path | str = Path("config"),
    error: dict[str, Any] | None = None,
    timestamp: str | None = None,
    window_days: int | None = None,
) -> Path:
    created_at = timestamp or utc_now_iso()
    run_id = make_run_id(
        operation=operation,
        subject=subject,
        timestamp=created_at,
        window_days=window_days,
    )
    output_dir = Path(runs_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{run_id}.json"

    payload: dict[str, Any] = {
        "run_id": run_id,
        "operation": operation,
        "subject": subject,
        "status": status,
        "created_at": created_at,
        "config_hashes": config_hashes(config_dir),
        "parameters": parameters or {},
        "inputs": inputs or {},
        "outputs": outputs or {},
        "counts": counts or {},
    }
    if error is not None:
        payload["error"] = error

    write_json_atomic(output_path, payload)
    return output_path


def load_run_snapshot(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def list_run_snapshots(runs_dir: Path | str = Path("data/runs")) -> list[dict[str, Any]]:
    base = Path(runs_dir)
    if not base.exists():
        return []

    snapshots: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json")):
        try:
            payload = load_run_snapshot(path)
        except json.JSONDecodeError:
            continue
        payload["_path"] = str(path)
        snapshots.append(payload)

    return sorted(
        snapshots,
        key=lambda item: (str(item.get("created_at", "")), str(item.get("run_id", ""))),
    )
