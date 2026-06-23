"""Baseline storage and conservative score comparison.

PR 9 stores historical score observations separately from deterministic scoring.
Baseline comparison is descriptive only: it never changes the convergence score and
never claims a trend, cause, intent, or forecast.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.models import BASELINE_LIMITATIONS, BaselineComparison, ScenarioScoreRecord
from app.persistence import utc_now_iso, write_json_atomic

# Baseline-comparison policy. The reference is a trailing window of prior daily
# observations, excluding the current (latest) day, so "above/below baseline" means
# "relative to recent history" rather than "relative to the running mean of my own
# scores including this one." Directional language is withheld until there is enough
# time-spanning history to be meaningful.
REFERENCE_WINDOW_DAYS = 90
REFERENCE_GATE_DAYS = 28
MIN_REFERENCE_BUCKETS = 8
NEAR_BASELINE_DELTA = 0.5


class BaselineRecord(BaseModel):
    """One stored score observation for a scenario."""

    observation_id: str = Field(min_length=64, max_length=64)
    observed_at: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    window_days: int = Field(ge=1)
    convergence_score: float = Field(ge=0, le=10)
    confidence: Literal["low", "medium", "high"]
    documents_considered: int = Field(ge=0)
    central_documents: int = Field(ge=0)
    incidental_documents: int = Field(ge=0)
    excluded_documents: int = Field(ge=0)
    irrelevant_documents: int = Field(ge=0)
    active_source_categories: int = Field(ge=0)
    score_components: dict[str, float] = Field(default_factory=dict)


class BaselineStore(BaseModel):
    """Human-readable baseline JSON persisted per scenario."""

    status: Literal["baseline_available"] = "baseline_available"
    scenario_id: str = Field(min_length=1)
    updated_at: str | None = None
    observations: list[BaselineRecord] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=lambda: BASELINE_LIMITATIONS.copy())


def baseline_path(
    *,
    scenario_id: str,
    baselines_dir: Path | str = Path("data/baselines"),
) -> Path:
    return Path(baselines_dir) / f"{scenario_id}_baseline.json"


def missing_baseline_comparison(
    *,
    scenario_id: str,
    current_score: float,
) -> BaselineComparison:
    return BaselineComparison(
        status="baseline_unavailable",
        scenario_id=scenario_id,
        current_score=current_score,
        baseline_observation_count=0,
        comparison="not_enough_history",
    )


def score_fingerprint(score: ScenarioScoreRecord) -> str:
    """Build a stable duplicate-suppression key for one score observation.

    ``baseline_comparison`` is intentionally excluded so repeated comparisons do
    not create distinct baseline observations for the same deterministic score.
    """

    payload = score.model_dump(mode="json")
    payload.pop("baseline_comparison", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def score_to_baseline_record(
    score: ScenarioScoreRecord,
    *,
    observed_at: str | None = None,
) -> BaselineRecord:
    return BaselineRecord(
        observation_id=score_fingerprint(score),
        observed_at=observed_at or utc_now_iso(),
        scenario_id=score.scenario_id,
        window_days=score.window_days,
        convergence_score=score.convergence_score,
        confidence=score.confidence,
        documents_considered=score.documents_considered,
        central_documents=score.central_documents,
        incidental_documents=score.incidental_documents,
        excluded_documents=score.excluded_documents,
        irrelevant_documents=score.irrelevant_documents,
        active_source_categories=score.active_source_categories,
        score_components=score.score_components.model_dump(mode="json"),
    )


def load_baseline_store(
    *,
    scenario_id: str,
    baselines_dir: Path | str = Path("data/baselines"),
) -> BaselineStore:
    path = baseline_path(scenario_id=scenario_id, baselines_dir=baselines_dir)
    if not path.exists():
        return BaselineStore(scenario_id=scenario_id)

    store = BaselineStore.model_validate_json(path.read_text(encoding="utf-8"))
    if store.scenario_id != scenario_id:
        raise ValueError(
            f"Baseline scenario mismatch in {path}: "
            f"expected {scenario_id}, got {store.scenario_id}"
        )
    return store


def save_baseline_store(
    store: BaselineStore,
    *,
    baselines_dir: Path | str = Path("data/baselines"),
) -> Path:
    output_path = baseline_path(scenario_id=store.scenario_id, baselines_dir=baselines_dir)
    write_json_atomic(output_path, store.model_dump(mode="json"))
    return output_path


def add_baseline_observation(
    *,
    score: ScenarioScoreRecord,
    baselines_dir: Path | str = Path("data/baselines"),
    observed_at: str | None = None,
) -> tuple[BaselineStore, BaselineRecord, bool, Path]:
    """Add a score observation unless an equivalent observation already exists.

    Returns ``(store, record, created, path)``. ``created`` is false when duplicate
    suppression prevented a second identical observation from being stored.
    """

    store = load_baseline_store(
        scenario_id=score.scenario_id,
        baselines_dir=baselines_dir,
    )
    record = score_to_baseline_record(score, observed_at=observed_at)
    existing_ids = {observation.observation_id for observation in store.observations}
    created = record.observation_id not in existing_ids

    if created:
        store.observations.append(record)
        store.updated_at = record.observed_at
    elif store.updated_at is None and store.observations:
        store.updated_at = store.observations[-1].observed_at

    path = save_baseline_store(store, baselines_dir=baselines_dir)
    return store, record, created, path


def _daily_score_buckets(observations: list[BaselineRecord]) -> dict[date, float]:
    """Collapse observations to one score per calendar day (the last that day).

    Time-normalizing to daily buckets stops ingestion cadence from weighting the
    baseline: two runs on the same day count once, a quiet week counts once. The
    representative is the latest observation that day, tie-broken on observation_id
    so the result is deterministic.
    """

    latest: dict[date, BaselineRecord] = {}
    for observation in observations:
        day = date.fromisoformat(observation.observed_at[:10])
        current = latest.get(day)
        if current is None or (observation.observed_at, observation.observation_id) > (
            current.observed_at,
            current.observation_id,
        ):
            latest[day] = observation
    return {day: record.convergence_score for day, record in latest.items()}


def compare_score_to_baseline(
    *,
    score: ScenarioScoreRecord,
    baselines_dir: Path | str = Path("data/baselines"),
) -> BaselineComparison:
    store = load_baseline_store(
        scenario_id=score.scenario_id,
        baselines_dir=baselines_dir,
    )
    observations = store.observations
    if not observations:
        return missing_baseline_comparison(
            scenario_id=score.scenario_id,
            current_score=score.convergence_score,
        )

    all_scores = [observation.convergence_score for observation in observations]
    descriptive = dict(
        baseline_observation_count=len(observations),
        baseline_latest_score=observations[-1].convergence_score,
        baseline_min_score=min(all_scores),
        baseline_max_score=max(all_scores),
    )

    # Collapse to one observation per calendar day, then build a trailing reference
    # window that excludes the most recent day (treated as "current").
    buckets = _daily_score_buckets(observations)
    as_of_day = max(buckets)
    window_start = as_of_day - timedelta(days=REFERENCE_WINDOW_DAYS)
    reference = {
        day: value
        for day, value in buckets.items()
        if window_start <= day < as_of_day
    }

    reference_spans_enough = (
        bool(reference) and (as_of_day - min(reference)).days >= REFERENCE_GATE_DAYS
    )
    if len(reference) < MIN_REFERENCE_BUCKETS or not reference_spans_enough:
        return BaselineComparison(
            status="baseline_available",
            scenario_id=score.scenario_id,
            current_score=score.convergence_score,
            comparison="not_enough_history",
            **descriptive,
        )

    reference_scores = list(reference.values())
    average_score = round(sum(reference_scores) / len(reference_scores), 1)
    delta = round(score.convergence_score - average_score, 1)

    if abs(delta) < NEAR_BASELINE_DELTA:
        comparison: Literal["near_baseline", "above_baseline", "below_baseline"] = (
            "near_baseline"
        )
    elif delta > 0:
        comparison = "above_baseline"
    else:
        comparison = "below_baseline"

    return BaselineComparison(
        status="baseline_available",
        scenario_id=score.scenario_id,
        current_score=score.convergence_score,
        baseline_average_score=average_score,
        delta_vs_baseline_average=delta,
        comparison=comparison,
        **descriptive,
    )


def baseline_show_payload(
    *,
    scenario_id: str,
    baselines_dir: Path | str = Path("data/baselines"),
) -> dict:
    path = baseline_path(scenario_id=scenario_id, baselines_dir=baselines_dir)
    if not path.exists():
        return {
            "status": "baseline_unavailable",
            "scenario_id": scenario_id,
            "baseline_path": str(path),
            "baseline_observation_count": 0,
            "limitations": BASELINE_LIMITATIONS.copy(),
        }

    store = load_baseline_store(scenario_id=scenario_id, baselines_dir=baselines_dir)
    payload = store.model_dump(mode="json")
    payload["baseline_path"] = str(path)
    payload["baseline_observation_count"] = len(store.observations)
    return payload
