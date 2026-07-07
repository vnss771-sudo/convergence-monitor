"""Direct Python pipeline runner — bypasses the CLI for daemon use.

Runs: ingest → classify → score → build v2 status dict.
Returns a ready-to-write convergence_latest_status.json dict.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.classification.keyword_matcher import (
    classify_documents,
    load_raw_documents,
    save_classified_documents_jsonl,
)
from app.commands.ingest import _ingest_one_source
from app.models import load_configs
from app.outputs.convergence_v2_writer import build_convergence_v2_status
from app.scoring.convergence import (
    load_classified_documents,
    parse_window_days,
    save_score_json,
    score_documents,
)

logger = logging.getLogger(__name__)

# Directories — can be overridden via env vars in daemon.py
CONFIG_DIR = Path("config")
RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
RUNS_DIR = Path("data/runs")
BASELINES_DIR = Path("data/baselines")


def run_pipeline(
    *,
    config_dir: Path = CONFIG_DIR,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
    runs_dir: Path = RUNS_DIR,
    ingest_limit: int = 20,
    window: str = "30d",
    status_path: Path | None = None,  # accepted but unused here; writing is the caller's job
) -> dict[str, Any]:
    """Run the full ingest → classify → score → export pipeline.

    Returns the convergence v2 status dict ready for writing to JSON.
    Never raises — errors are caught and reflected in a degraded status.
    """
    bundle = _load_configs(config_dir)
    if bundle is None:
        return _error_status("Config loading failed")

    # ── 1. Ingest ──────────────────────────────────────────────────────────
    total_saved = 0
    for source_config in bundle.enabled_sources:
        try:
            result = _ingest_one_source(
                source_config=source_config,
                limit=ingest_limit,
                raw_dir=raw_dir,
                runs_dir=runs_dir,
                config_dir=config_dir,
                replace=False,
            )
            total_saved += result.get("saved", 0)
            if result["status"] == "ok":
                logger.info("Ingested %s: saved=%d", source_config.id, result.get("saved", 0))
            else:
                logger.warning("Ingest degraded for %s: %s", source_config.id, result.get("error"))
        except Exception as exc:
            logger.warning("Ingest exception for %s: %s", source_config.id, exc)

    # ── 2. Classify + 3. Score ─────────────────────────────────────────────
    window_days = parse_window_days(window)
    scenario_scores: dict[str, float] = {}
    sources_matched: list[str] = []
    total_docs = 0

    for scenario_cfg in bundle.scenarios.scenarios:
        try:
            raw_docs = load_raw_documents(raw_dir)
            classified = classify_documents(raw_docs, scenario_cfg)
            save_classified_documents_jsonl(
                classified,
                scenario_id=scenario_cfg.id,
                processed_dir=processed_dir,
            )

            classified_docs = load_classified_documents(
                scenario_id=scenario_cfg.id,
                processed_dir=processed_dir,
            )
            score_record = score_documents(
                classified_docs,
                bundle=bundle,
                scenario_id=scenario_cfg.id,
                window_days=window_days,
            )
            save_score_json(score_record, processed_dir=processed_dir)

            scenario_scores[scenario_cfg.id] = score_record.convergence_score
            total_docs += score_record.documents_considered
            logger.info(
                "Scored %s: %.2f (docs=%d)",
                scenario_cfg.id,
                score_record.convergence_score,
                score_record.documents_considered,
            )
        except Exception as exc:
            logger.warning("Score exception for %s: %s", scenario_cfg.id, exc)
            scenario_scores[scenario_cfg.id] = 0.0

    # ── 4. Derive sources from processed score files ───────────────────────
    sources_matched = _derive_sources(processed_dir, bundle)

    # ── 5. Build drivers from top-scoring scenarios ────────────────────────
    top_drivers = _build_drivers(scenario_scores)

    # ── 6. Build theme scores (int 0-10 per scenario) ─────────────────────
    theme_scores = {k: min(10, max(0, round(v))) for k, v in scenario_scores.items()}

    return build_convergence_v2_status(
        theme_scores=theme_scores,
        sources_matched=sources_matched,
        documents_checked=total_docs,
        top_drivers=top_drivers,
    )


# ── Helpers ────────────────────────────────────────────────────────────────

def _load_configs(config_dir: Path) -> Any | None:
    try:
        return load_configs(config_dir)
    except Exception as exc:
        logger.error("Failed to load configs from %s: %s", config_dir, exc)
        return None


def _derive_sources(processed_dir: Path, bundle: Any) -> list[str]:
    """Return source names that contributed data (have non-empty raw files)."""
    raw_dir = RAW_DIR
    matched: list[str] = []
    for source in bundle.enabled_sources:
        raw_path = raw_dir / f"{source.id}.jsonl"
        if raw_path.exists() and raw_path.stat().st_size > 10:
            matched.append(source.name)
    return matched[:6]


def _build_drivers(scores: dict[str, float]) -> list[str]:
    """Build human-readable driver strings from scenario scores."""
    _LABELS: dict[str, str] = {
        "cbdc_payment_resilience": "CBDC and payment-system resilience language elevated",
        "financial_stability": "Financial-stability language elevated across official sources",
        "inflation_persistence": "Inflation-persistence language remains elevated",
        "energy_security": "Energy-security language increasing in official documents",
        "china_slowdown": "China economic-slowdown language present in monitored sources",
        "housing_stress": "Housing-stress language detected in official documents",
        "credit_stress": "Credit-stress language elevated across monitored sources",
    }
    drivers: list[str] = []
    for scenario_id, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        if score >= 2.0:
            label = _LABELS.get(scenario_id, f"{scenario_id.replace('_', ' ').title()} language elevated")
            drivers.append(label)
    if not drivers:
        drivers.append("No significant convergence themes detected in current window")
    return drivers[:5]


def _error_status(reason: str) -> dict[str, Any]:
    from app.outputs.convergence_v2_writer import _make_empty_status
    status = _make_empty_status()
    status["top_drivers"] = [f"Pipeline error: {reason}"]
    return status
