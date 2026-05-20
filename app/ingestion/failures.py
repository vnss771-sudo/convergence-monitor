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


def summarize_source_health_payload(
    payload: dict[str, Any],
    *,
    expected_source_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Summarize source health without hiding failing source details."""
    sources = payload.get("sources", {})
    expected_ids = expected_source_ids or sorted(sources)

    sources_ok = 0
    sources_error = 0
    sources_unknown = 0
    failed_sources: list[dict[str, Any]] = []
    failure_types: dict[str, int] = {}

    for source_id in expected_ids:
        record = sources.get(source_id)
        status = record.get("status") if isinstance(record, dict) else None

        if status == "ok":
            sources_ok += 1
            continue

        if status is None:
            sources_unknown += 1
            continue

        sources_error += 1
        error = record.get("error") or {}
        error_type = str(error.get("type") or "unknown_error")
        failure_types[error_type] = failure_types.get(error_type, 0) + 1
        failed_sources.append(
            {
                "source_id": source_id,
                "status": status,
                "error_type": error_type,
                "message": str(error.get("message") or ""),
                "last_checked_at": record.get("last_checked_at"),
                "last_success_at": record.get("last_success_at"),
                "last_failure_at": record.get("last_failure_at"),
            }
        )

    if not expected_ids:
        overall = "unavailable"
    elif sources_error:
        overall = "degraded" if sources_ok or sources_unknown else "error"
    elif sources_unknown:
        overall = "unknown"
    else:
        overall = "ok"

    return {
        "sources_total": len(expected_ids),
        "sources_ok": sources_ok,
        "sources_error": sources_error,
        "sources_unknown": sources_unknown,
        "overall": overall,
        "failure_types": failure_types,
        "failed_sources": failed_sources,
    }
