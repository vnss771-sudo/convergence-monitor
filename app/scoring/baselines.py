"""Baseline storage and conservative score comparison.

PR 9 stores historical score observations separately from deterministic scoring.
Baseline comparison is descriptive only: it never changes the convergence score and
never claims a trend, cause, intent, or forecast.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.models import ScenarioScoreRecord
from app.runs.snapshots import utc_now_iso


BASELINE_LIMITATIONS = [
    "Baseline comparison is descriptive only.",
    "It does not change the deterministic convergence score.",
    "It does not infer causation, intent, coordination, or future events.",
]


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


class BaselineComparison(BaseModel):
    """Conservative comparison of a current score against stored history."""

    status: Literal["baseline_unavailable", "baseline_available"]
    scenario_id: str = Field(min_length=1)
    current_score: float = Field(ge=0, le=10)
    baseline_observation_count: int = Field(ge=0)
    baseline_average_score: float | None = None
    baseline_latest_score: float | None = None
    baseline_min_score: float | None = None
    baseline_max_score: float | None = None
    delta_vs_baseline_average: float | None = None
    comparison: Literal[
        "not_enough_history",
        "near_baseline",
        "above_baseline",
        "below_baseline",
    ] = "not_enough_history"
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
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            store.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
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

    scores = [observation.convergence_score for observation in observations]
    average_score = round(sum(scores) / len(scores), 1)
    delta = round(score.convergence_score - average_score, 1)

    if abs(delta) < 0.5:
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
        baseline_observation_count=len(observations),
        baseline_average_score=average_score,
        baseline_latest_score=observations[-1].convergence_score,
        baseline_min_score=min(scores),
        baseline_max_score=max(scores),
        delta_vs_baseline_average=delta,
        comparison=comparison,
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
