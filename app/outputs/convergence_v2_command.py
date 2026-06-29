"""Typer CLI command: export convergence status in v2 format for ASX Sentinel Composite.

Usage
-----
    convergence-monitor export-v2
    convergence-monitor export-v2 --output /tmp/status.json
    convergence-monitor export-v2 --confidence 65

The command reads all per-scenario score JSON files written by ``score``
(``data/processed/{scenario_id}_score.json``) and aggregates them into a single
v2 payload.  It does not re-run scoring; it translates what is already on disk.

``app.persistence`` does not expose ``load_latest_run_data``; this module
provides ``_load_latest_run_data`` as a local stub that assembles an equivalent
payload from the standard score artifacts.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import typer

from app.outputs.convergence_v2_writer import (
    DEFAULT_OUTPUT_PATH,
    build_convergence_v2_status,
    write_convergence_v2_status,
)

logger = logging.getLogger(__name__)

app = typer.Typer(
    add_completion=False,
    help="Export convergence status in v2 format for ASX Sentinel Composite.",
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_score_json(path: Path) -> dict[str, Any] | None:
    """Load a single score JSON file, returning None on any parse error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Skipping %s: %s", path, exc)
        return None


def _load_latest_run_data(
    processed_dir: Path = Path("data/processed"),
) -> dict[str, Any] | None:
    """Aggregate all per-scenario score JSON files into a single run-data dict.

    This is a local stub that substitutes for a ``load_latest_run_data``
    function that does not exist in ``app.persistence``.  It reads every
    ``*_score.json`` file from *processed_dir*, collects the scenario scores,
    active source categories, and documents considered, then returns a dict
    shaped to match what :func:`build_convergence_v2_status` expects:

    .. code-block:: python

        {
            "theme_scores":     {scenario_id: int(convergence_score * 10), ...},
            "sources_matched":  [str, ...],   # unique source categories
            "documents_checked": int,
            "top_drivers":      [str, ...],
        }

    Returns ``None`` when *processed_dir* contains no ``*_score.json`` files.
    """
    base = Path(processed_dir)
    score_files = sorted(base.glob("*_score.json"))
    if not score_files:
        return None

    theme_scores: dict[str, int] = {}
    source_category_set: set[str] = set()
    total_documents = 0
    top_drivers: list[str] = []

    for score_path in score_files:
        data = _load_score_json(score_path)
        if data is None:
            continue

        scenario_id: str = data.get("scenario_id", score_path.stem.removesuffix("_score"))
        raw_score: float = data.get("convergence_score", 0.0)
        # Normalise 0-10 float score to 0-100 integer for the v2 theme_scores map.
        theme_scores[scenario_id] = min(100, int(round(raw_score * 10)))

        active_cats: int = data.get("active_source_categories", 0)
        # We don't have per-category names in the score record, so use the
        # active_source_categories count as a proxy label when > 0.
        if active_cats > 0:
            source_category_set.add(f"{active_cats}_source_categories")

        total_documents += data.get("documents_considered", 0)

        # Build human-readable driver lines from score components when present.
        components: dict[str, Any] = data.get("score_components", {})
        if components and scenario_id not in [d.split(":")[0] for d in top_drivers]:
            convergence_score = data.get("convergence_score", raw_score)
            confidence_label = data.get("confidence", "low")
            central = data.get("central_documents", 0)
            incidental = data.get("incidental_documents", 0)
            driver = (
                f"{scenario_id}: score={convergence_score}/10 "
                f"confidence={confidence_label} "
                f"central={central} incidental={incidental}"
            )
            top_drivers.append(driver)

    if not theme_scores:
        return None

    if not top_drivers:
        top_drivers = ["Convergence data available"]

    return {
        "theme_scores": theme_scores,
        "sources_matched": sorted(source_category_set),
        "documents_checked": total_documents,
        "top_drivers": top_drivers,
    }


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

@app.command("export-v2")
def export_v2(
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help=(
            "Output path for convergence_latest_status.json.  "
            f"Defaults to CONVERGENCE_STATUS_JSON env var or '{DEFAULT_OUTPUT_PATH}'."
        ),
    ),
    confidence: int = typer.Option(
        None,
        "--confidence",
        min=0,
        max=100,
        help="Override the derived confidence value (0-100).",
    ),
    processed_dir: Path = typer.Option(
        Path("data/processed"),
        "--processed-dir",
        help="Directory containing per-scenario *_score.json files.",
    ),
) -> None:
    """Export the latest convergence assessment as v2 JSON for ASX Sentinel Composite.

    Reads per-scenario score JSON files produced by 'convergence-monitor score'
    and aggregates them into a single convergence_latest_status.json.
    """
    try:
        run_data = _load_latest_run_data(processed_dir=processed_dir)
        if run_data is None:
            typer.echo(
                f"No score JSON files found in '{processed_dir}'. "
                "Run 'convergence-monitor score' first.",
                err=True,
            )
            raise typer.Exit(1)

        theme_scores: dict[str, int] = run_data.get("theme_scores", {})
        sources: list[str] = run_data.get(
            "sources_matched", run_data.get("sources", [])
        )
        docs: int = run_data.get(
            "documents_checked", run_data.get("total_documents", 0)
        )
        drivers: list[str] = run_data.get(
            "top_drivers", run_data.get("drivers", ["Convergence data available"])
        )

        status = build_convergence_v2_status(
            theme_scores=theme_scores,
            sources_matched=sources,
            documents_checked=docs,
            top_drivers=drivers,
            confidence=confidence,
        )

        destination: str = output if output is not None else DEFAULT_OUTPUT_PATH
        written = write_convergence_v2_status(status, destination)

        typer.echo(f"Convergence v2 status written to {written}")
        typer.echo(f"  Level:         {status['convergence_level']}")
        typer.echo(f"  Confidence:    {status['confidence']}%")
        typer.echo(f"  Primary theme: {status['primary_theme']}")
        typer.echo(f"  Themes scored: {len(theme_scores)}")
        typer.echo(f"  Docs checked:  {docs}")

    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        logger.exception("export-v2 failed")
        raise typer.Exit(1) from exc
