from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ingestion_error_payload(
    *,
    source_id: str,
    message: str,
    error_type: str = "ingestion_error",
) -> dict[str, str]:
    """Create a stable source-ingestion error payload.

    PR 7 keeps this intentionally boring and structured. The payload records the
    failure; it does not interpret significance or hide the failed source.
    """

    return {
        "source_id": source_id,
        "type": error_type,
        "message": message,
    }


def source_health_path(runs_dir: Path | str = Path("data/runs")) -> Path:
    return Path(runs_dir) / "source_health" / "source_health.json"


def load_source_health(runs_dir: Path | str = Path("data/runs")) -> dict[str, Any]:
    path = source_health_path(runs_dir)
    if not path.exists():
        return {"updated_at": None, "sources": {}}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"updated_at": None, "sources": {}}

    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), dict):
        return {"updated_at": None, "sources": {}}

    return payload


def update_source_health(
    *,
    runs_dir: Path | str = Path("data/runs"),
    source_id: str,
    status: str,
    counts: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> Path:
    """Persist the latest health status for a source.

    Health records are deliberately stored outside the run-snapshot root so
    ``runs list`` only returns actual run snapshots.
    """

    now = timestamp or utc_now_iso()
    payload = load_source_health(runs_dir)
    sources = payload.setdefault("sources", {})
    existing = sources.get(source_id, {})

    record: dict[str, Any] = {
        "source_id": source_id,
        "status": status,
        "last_checked_at": now,
        "counts": counts or {},
    }

    if status == "ok":
        record["last_success_at"] = now
        if existing.get("last_failure_at"):
            record["last_failure_at"] = existing["last_failure_at"]
        record["error"] = None
    else:
        record["last_failure_at"] = now
        if existing.get("last_success_at"):
            record["last_success_at"] = existing["last_success_at"]
        record["error"] = error or {
            "source_id": source_id,
            "type": "ingestion_error",
            "message": "Source ingestion failed.",
        }

    sources[source_id] = record
    payload["updated_at"] = now

    path = source_health_path(runs_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
