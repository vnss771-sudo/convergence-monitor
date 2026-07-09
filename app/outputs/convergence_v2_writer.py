"""Produce the v2 convergence_latest_status.json consumed by ASX Sentinel Composite.

This module is intentionally dependency-light: it takes plain Python dicts and
primitives, performs one atomic JSON write, and returns the path written. It does
not import Pydantic models, scoring internals, or CLI machinery so it can be
called from any context including tests and external orchestrators.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "2.0.0"
SOURCE = "convergence_monitor"
GUARDRAIL = (
    "Informational only. Not financial advice. "
    "This does not prove causation, coordination, intent, or prediction."
)

DEFAULT_OUTPUT_PATH = os.environ.get(
    "CONVERGENCE_STATUS_JSON",
    "data/runs/convergence_latest_status.json",
)

# Approximate institutional source name -> trust weight mapping used when
# computing a weighted-average confidence from the matched source list.
# Source IDs that do not appear here fall back to 0.1 (unknown/low-trust).
SOURCE_WEIGHTS: dict[str, float] = {
    # Keys must match the `name` field in config/sources.yaml exactly.
    "Reserve Bank of Australia": 1.00,
    "Bank for International Settlements": 0.90,
    "International Monetary Fund": 0.85,
    "Federal Reserve": 0.75,
    "European Central Bank": 0.75,
}

LEVEL_THRESHOLDS = [
    (70, "critical"),
    (50, "warning"),
    (30, "watch"),
    (0, "ok"),
]


def confidence_to_level(confidence: int) -> str:
    """Map an integer confidence (0-100) to a human-readable convergence level."""
    for threshold, level in LEVEL_THRESHOLDS:
        if confidence >= threshold:
            return level
    return "ok"


def build_convergence_v2_status(
    theme_scores: dict[str, int],
    sources_matched: list[str],
    documents_checked: int,
    top_drivers: list[str],
    confidence: int | None = None,
) -> dict[str, Any]:
    """Build and return the v2 status dict without writing it to disk.

    Parameters
    ----------
    theme_scores:
        Mapping of theme/scenario ID -> integer score (typically 0-10 scaled
        to 0-100 by the caller, but the function accepts any positive integer).
    sources_matched:
        List of source identifiers (names or IDs) that contributed evidence.
        Used to derive a weighted-average confidence when ``confidence`` is None.
    documents_checked:
        Total number of documents examined during the scoring run.
    top_drivers:
        Free-text driver descriptions.  At most the first five are kept.
    confidence:
        Optional override (0-100).  When None the function derives confidence
        from the top theme score and the average SOURCE_WEIGHTS of matched
        sources.
    """
    if not theme_scores:
        return _make_empty_status()

    primary_theme = max(theme_scores, key=lambda t: theme_scores[t])

    if confidence is None:
        weights = [SOURCE_WEIGHTS.get(s, 0.1) for s in sources_matched]
        avg_weight = sum(weights) / len(weights) if weights else 0.0
        max_theme_score = max(theme_scores.values())
        # Scale: theme score treated as 0-10; multiply by 10 to get 0-100,
        # then temper by average source trust weight.
        confidence = min(100, int(max_theme_score * 10 * avg_weight))

    convergence_level = confidence_to_level(confidence)

    return {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE,
        "generated_at": datetime.now(UTC).isoformat(),
        "primary_theme": primary_theme,
        "convergence_level": convergence_level,
        "confidence": confidence,
        "documents_checked": documents_checked,
        "sources_matched": sources_matched,
        "theme_scores": theme_scores,
        "top_drivers": top_drivers[:5],
        "guardrail": GUARDRAIL,
    }


def _make_empty_status() -> dict[str, Any]:
    """Return a well-formed v2 status dict representing an absence of data."""
    return {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE,
        "generated_at": datetime.now(UTC).isoformat(),
        "primary_theme": "unknown",
        "convergence_level": "unknown",
        "confidence": 0,
        "documents_checked": 0,
        "sources_matched": [],
        "theme_scores": {},
        "top_drivers": ["Insufficient data for convergence assessment"],
        "guardrail": GUARDRAIL,
    }


def write_convergence_v2_status(
    status: dict[str, Any],
    path: str = DEFAULT_OUTPUT_PATH,
) -> str:
    """Atomically write *status* as JSON to *path* and return the resolved path.

    The write is atomic: the payload is first serialized to a ``.tmp`` sibling
    file, then ``Path.rename`` moves it into place.  Parent directories are
    created automatically.

    Parameters
    ----------
    status:
        Dict produced by :func:`build_convergence_v2_status`.
    path:
        Destination file path.  Defaults to the value of the
        ``CONVERGENCE_STATUS_JSON`` environment variable, or
        ``data/runs/convergence_latest_status.json`` if unset.

    Returns
    -------
    str
        Absolute (resolved) path of the file that was written.
    """
    out = pathlib.Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, indent=2), encoding="utf-8")
    tmp.rename(out)
    logger.info("convergence_v2_status written to %s", out.resolve())
    return str(out.resolve())
