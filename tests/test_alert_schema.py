from __future__ import annotations

from app.alerts.generator import required_alert_fields


def test_required_alert_schema_fields_are_stable() -> None:
    assert required_alert_fields() == [
        "scenario_id",
        "scenario_name",
        "generated_at",
        "window_days",
        "convergence_score",
        "confidence",
        "source_categories_active",
        "document_count",
        "summary",
        "evidence",
        "warnings",
        "limitations",
    ]
