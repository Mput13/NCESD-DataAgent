from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl, field_validator


class WorkflowOutcome(StrEnum):
    PASSED = "passed"
    NEEDS_CLARIFICATION = "needs_clarification"
    NOT_FOUND = "not_found"
    ERROR = "error"


class QueryKind(StrEnum):
    DIRECT_LOOKUP = "direct_lookup"
    COMPARISON = "comparison"
    RESEARCH = "research"
    DERIVED_METRIC = "derived_metric"
    AMBIGUOUS = "ambiguous"
    NO_DATA_CHECK = "no_data_check"


class SourceFamily(StrEnum):
    FEDSTAT = "fedstat"
    WORLD_BANK = "world_bank"
    CKAN = "ckan"


class MatchMode(StrEnum):
    EXACT = "exact"
    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    PROXY = "proxy"
    CKAN_DISCOVERY = "ckan_discovery"
    METHODOLOGY_MATCH = "methodology_match"


class TraceEvent(BaseModel):
    run_id: str
    state: str
    decision: str
    detail: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: int | None = None
    warnings: list[str] = Field(default_factory=list)


class IntentFrame(BaseModel):
    original_query: str
    query_kind: QueryKind
    geography: list[str] = Field(default_factory=list)
    indicators: list[str] = Field(default_factory=list)
    period: str | None = None
    units: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)


class SourceCandidate(BaseModel):
    source_id: str
    source_family: SourceFamily
    title: str
    indicator_id: str | None = None
    indicator_name: str | None = None
    unit: str | None = None
    period: str | None = None
    geography: list[str] = Field(default_factory=list)
    dimensions: dict[str, Any] = Field(default_factory=dict)
    local_path: Path | None = None
    provenance_url: HttpUrl | None = None
    match_mode: MatchMode
    why_matched: str
    limitations: list[str] = Field(default_factory=list)

    @field_validator("source_id", "title", "why_matched")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class CoverageReport(BaseModel):
    candidate: SourceCandidate
    status: Literal["enough", "not_enough", "unknown"]
    available_periods: list[str] = Field(default_factory=list)
    available_geographies: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExtractionPlan(BaseModel):
    candidate: SourceCandidate
    operations: list[str]
    output_grain: str
    deterministic_only: bool = True


class DatasetArtifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: f"dataset-{uuid4().hex[:12]}")
    source_id: str
    rows: int
    columns: list[str]
    path: Path | None = None
    records_preview: list[dict[str, Any]] = Field(default_factory=list)
    provenance: list[SourceCandidate] = Field(default_factory=list)


class WorkflowResponse(BaseModel):
    run_id: str = Field(default_factory=lambda: f"run-{uuid4().hex[:12]}")
    outcome: WorkflowOutcome
    message: str
    intent: IntentFrame | None = None
    selected_sources: list[SourceCandidate] = Field(default_factory=list)
    coverage_reports: list[CoverageReport] = Field(default_factory=list)
    dataset_artifacts: list[DatasetArtifact] = Field(default_factory=list)
    trace_events: list[TraceEvent] = Field(default_factory=list)


class SourceAdapter(BaseModel):
    family: SourceFamily

    def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]:
        raise NotImplementedError

    def coverage(self, candidate: SourceCandidate, intent: IntentFrame) -> CoverageReport:
        raise NotImplementedError

