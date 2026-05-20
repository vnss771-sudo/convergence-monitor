from __future__ import annotations

from app.ingestion.failures import summarize_source_health_payload


def test_summarize_source_health_payload_reports_failure_types() -> None:
    payload = {
        "updated_at": "2026-05-20T00:00:00Z",
        "sources": {
            "bis": {
                "source_id": "bis",
                "status": "ok",
                "last_checked_at": "2026-05-20T00:00:00Z",
                "counts": {"fetched": 2},
                "error": None,
            },
            "imf": {
                "source_id": "imf",
                "status": "error",
                "last_checked_at": "2026-05-20T00:01:00Z",
                "last_failure_at": "2026-05-20T00:01:00Z",
                "counts": {"fetched": 0},
                "error": {
                    "source_id": "imf",
                    "type": "empty_feed",
                    "message": "RSS source returned no feed entries.",
                },
            },
        },
    }

    summary = summarize_source_health_payload(
        payload,
        expected_source_ids=["bis", "imf", "ecb"],
    )

    assert summary["overall"] == "degraded"
    assert summary["sources_total"] == 3
    assert summary["sources_ok"] == 1
    assert summary["sources_error"] == 1
    assert summary["sources_unknown"] == 1
    assert summary["failure_types"] == {"empty_feed": 1}
    assert summary["failed_sources"] == [
        {
            "source_id": "imf",
            "status": "error",
            "error_type": "empty_feed",
            "message": "RSS source returned no feed entries.",
            "last_checked_at": "2026-05-20T00:01:00Z",
            "last_success_at": None,
            "last_failure_at": "2026-05-20T00:01:00Z",
        }
    ]
