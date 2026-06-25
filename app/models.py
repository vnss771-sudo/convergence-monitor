from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, HttpUrl, ValidationError, field_validator, model_validator

# Source and scenario ids are interpolated into on-disk artifact file paths
# (e.g. f"{source_id}.jsonl", f"{scenario_id}_score.json"). Restricting them to a
# safe character set keeps a misconfigured config file from writing outside the
# intended data directories.
_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_safe_id(value: str) -> str:
    if not _SAFE_ID_PATTERN.fullmatch(value):
        raise ValueError(
            "id must contain only letters, digits, underscores, or hyphens "
            f"(got {value!r})"
        )
    return value


class RelevanceRules(BaseModel):
    central_min_primary_matches: int = Field(ge=1)
    central_min_total_matches: int = Field(ge=1)
    incidental_min_total_matches: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> "RelevanceRules":
        if self.central_min_total_matches < self.central_min_primary_matches:
            raise ValueError(
                "central_min_total_matches must be greater than or equal to "
                "central_min_primary_matches"
            )
        if self.central_min_total_matches < self.incidental_min_total_matches:
            raise ValueError(
                "central_min_total_matches must be greater than or equal to "
                "incidental_min_total_matches"
            )
        return self


class Scenario(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    primary_terms: list[str] = Field(min_length=1)
    secondary_terms: list[str] = Field(min_length=1)
    exclusion_terms: list[str] = Field(default_factory=list)
    relevance_rules: RelevanceRules

    _validate_id = field_validator("id")(_validate_safe_id)

    @field_validator("primary_terms", "secondary_terms", "exclusion_terms")
    @classmethod
    def normalize_terms(cls, terms: list[str]) -> list[str]:
        cleaned = [term.strip().lower() for term in terms if term and term.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("terms must be unique within each term list")
        return cleaned


class ScenariosConfig(BaseModel):
    scenarios: list[Scenario] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_scenario_ids(self) -> "ScenariosConfig":
        ids = [scenario.id for scenario in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("scenario ids must be unique")
        return self


class Source(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    type: Literal["rss"]
    enabled: bool = True
    trust_weight: float = Field(gt=0, le=1)
    url: HttpUrl
    fallback_urls: list[HttpUrl] = Field(default_factory=list)
    timeout_seconds: float = Field(default=20.0, gt=0, le=120)

    _validate_id = field_validator("id")(_validate_safe_id)


class SourcesConfig(BaseModel):
    sources: list[Source] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_source_ids(self) -> "SourcesConfig":
        ids = [source.id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("source ids must be unique")
        return self


class ConfigBundle(BaseModel):
    scenarios: ScenariosConfig
    sources: SourcesConfig

    @property
    def enabled_sources(self) -> list[Source]:
        return [source for source in self.sources.sources if source.enabled]

    def get_source(self, source_id: str) -> Source:
        for source in self.sources.sources:
            if source.id == source_id:
                return source
        raise KeyError(f"Unknown source_id: {source_id}")

    def get_scenario(self, scenario_id: str) -> Scenario:
        for scenario in self.scenarios.scenarios:
            if scenario.id == scenario_id:
                return scenario
        raise KeyError(f"Unknown scenario_id: {scenario_id}")


class DocumentRecord(BaseModel):
    """Normalized raw document record produced by RSS ingestion.

    This is intentionally pre-classification. No relevance, score, alert, or narrative
    interpretation belongs in this model.
    """

    schema_version: str = Field(default="raw.v1")
    document_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    source_category: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    published_at: str | None = None
    summary: str = ""
    content_hash: str = Field(min_length=64, max_length=64)
    ingested_at: str = Field(min_length=1)
    raw: dict[str, Any] = Field(default_factory=dict)


class IngestionSaveResult(BaseModel):
    """Append/dedupe write result for raw JSONL ingestion."""

    raw_path: str = Field(min_length=1)
    fetched: int = Field(ge=0)
    saved: int = Field(ge=0)
    skipped_existing: int = Field(ge=0)
    saved_document_ids: list[str] = Field(default_factory=list)
    skipped_document_ids: list[str] = Field(default_factory=list)


class ClassifiedDocumentRecord(BaseModel):
    """Processed document record produced by deterministic PR 3 classification.

    This remains pre-scoring and pre-alert. It explains relevance only; it does not
    assign convergence scores, confidence bands, or narrative interpretation.
    """

    schema_version: str = Field(default="classified.v1")
    document_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    source_category: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    published_at: str | None = None
    summary: str = ""
    content_hash: str = Field(min_length=64, max_length=64)
    scenario_id: str = Field(min_length=1)
    scenario_name: str = Field(min_length=1)
    relevance: Literal["central", "incidental", "excluded", "irrelevant"]
    matched_primary_terms: list[str] = Field(default_factory=list)
    matched_secondary_terms: list[str] = Field(default_factory=list)
    matched_exclusion_terms: list[str] = Field(default_factory=list)
    total_match_count: int = Field(ge=0)
    reason: str = Field(min_length=1)
    classified_at: str = Field(min_length=1)



class ScoreComponents(BaseModel):
    """Explainable PR 4 score components.

    Components are deterministic and bounded. They are not an alert and do not
    imply intent, coordination, causation, or future events.
    """

    # Ceilings are the historical basis (3/2/2/1/2) scaled by 10/8 onto the 0–10
    # convergence range (see app/scoring/convergence.py:SCORE_SCALE), expressed as
    # their one-decimal display maxima so a rounded component never trips the bound
    # (e.g. 3.0*1.25 = 3.75 displays as 3.8).
    central_document_score: float = Field(ge=0, le=3.8)
    source_diversity_score: float = Field(ge=0, le=2.5)
    trust_weight_score: float = Field(ge=0, le=2.5)
    recency_score: float = Field(ge=0, le=1.3)
    duplication_penalty: float = Field(ge=0, le=2.5)


BASELINE_LIMITATIONS: list[str] = [
    "Baseline comparison is descriptive only.",
    "It does not change the deterministic convergence score.",
    "It does not infer causation, intent, coordination, or future events.",
]


class BaselineComparison(BaseModel):
    """Conservative comparison of a current score against stored history.

    Descriptive only — never changes the deterministic convergence score and never
    infers causation, intent, coordination, or future events.
    """

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


class ScenarioScoreRecord(BaseModel):
    """Scenario-level scoring output produced by PR 4.

    This is the only PR 4 production artifact. It is deliberately pre-alert:
    no final alert card, no narrative speculation, and no prediction language.
    PR 9 adds baseline comparison as metadata only; it never changes the
    deterministic convergence score.
    """

    schema_version: str = Field(default="score.v1")
    status: Literal["ok"]
    scenario_id: str = Field(min_length=1)
    window_days: int = Field(ge=1)
    documents_considered: int = Field(ge=0)
    central_documents: int = Field(ge=0)
    incidental_documents: int = Field(ge=0)
    excluded_documents: int = Field(ge=0)
    irrelevant_documents: int = Field(ge=0)
    active_source_categories: int = Field(ge=0)
    convergence_score: float = Field(ge=0, le=10)
    confidence: Literal["low", "medium", "high"]
    score_components: ScoreComponents
    baseline_comparison: BaselineComparison
    limitations: list[str] = Field(min_length=1)


class AlertEvidenceItem(BaseModel):
    """Evidence item included in the stable JSON alert card.

    ``quality_flags`` explains why evidence was eligible while keeping weak or
    incidental matches analytically bounded.
    """

    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    source_category: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    published_at: str | None = None
    relevance: Literal["central", "incidental"]
    matched_terms: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)
    quality_flags: list[str] = Field(default_factory=list)


class AlertRecord(BaseModel):
    """Stable JSON alert card produced after scoring.

    This model is intentionally conservative. It reports public-document
    convergence only and does not infer intent, coordination, causation, or
    future events.
    """

    schema_version: str = Field(default="alert.v1")
    scenario_id: str = Field(min_length=1)
    scenario_name: str = Field(min_length=1)
    generated_at: str = Field(min_length=1)
    window_days: int = Field(ge=1)
    convergence_score: float = Field(ge=0, le=10)
    confidence: Literal["low", "medium", "high"]
    source_categories_active: int = Field(ge=0)
    document_count: int = Field(ge=0)
    summary: str = Field(min_length=1)
    evidence: list[AlertEvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)


def load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {path}")

    return data


def load_configs(config_dir: Path | str = "config") -> ConfigBundle:
    config_path = Path(config_dir)
    scenarios = ScenariosConfig.model_validate(load_yaml(config_path / "scenarios.yaml"))
    sources = SourcesConfig.model_validate(load_yaml(config_path / "sources.yaml"))
    return ConfigBundle(scenarios=scenarios, sources=sources)


def config_summary(bundle: ConfigBundle) -> dict[str, int]:
    return {
        "scenario_count": len(bundle.scenarios.scenarios),
        "source_count": len(bundle.sources.sources),
        "enabled_source_count": len(bundle.enabled_sources),
        "source_category_count": len({source.category for source in bundle.enabled_sources}),
    }


def format_validation_error(error: ValidationError) -> str:
    return "\n".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
        for item in error.errors()
    )
