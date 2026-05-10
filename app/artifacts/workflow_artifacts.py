from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


QueryCategory = Literal[
    "simple",
    "comparative",
    "research",
    "derived_metric",
    "ambiguous",
    "no_data",
]

WorkflowStatus = Literal[
    "ok",
    "gated",
    "skipped_with_reason",
    "needs_clarification",
    "no_data",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class IntentFrame(BaseModel):
    """Structured user intent produced before retrieval or extraction."""

    query: str
    category: QueryCategory
    known_fields: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    source_preferences: list[str] = Field(default_factory=list)
    open_reasoning: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ResearchDesignArtifact(BaseModel):
    """Research design with hypotheses, dimensions, indicators, and assumptions."""

    artifact_id: str
    route: str
    hypotheses: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    indicators: list[str] = Field(default_factory=list)
    grouping_policy: str | None = None
    assumptions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class EvidenceBundleArtifact(BaseModel):
    """Compressed source evidence passed between scouts and coverage."""

    selected_sources: list[dict[str, Any]] = Field(default_factory=list)
    rejected_sources: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_status: str = "not_run"
    qdrant_status: str = "unknown"
    dense_status: str = "unknown"

    model_config = ConfigDict(extra="forbid")


class SourceRejectionRecord(BaseModel):
    candidate_id: str
    source_family: str | None = None
    title: str | None = None
    rejection_reason: str
    severity: Literal["low", "medium", "high"] = "medium"
    alternative_used: str | None = None

    model_config = ConfigDict(extra="forbid")


class CoverageReport(BaseModel):
    source_id: str
    status: WorkflowStatus
    checks: list[str] = Field(default_factory=list)
    available_periods: list[str] = Field(default_factory=list)
    available_geographies: list[str] = Field(default_factory=list)
    unit: str | None = None
    frequency: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    gated_reason: str | None = None

    model_config = ConfigDict(extra="forbid")


class ExtractionPlan(BaseModel):
    artifact_id: str
    source_id: str | None = None
    status: WorkflowStatus = "skipped_with_reason"
    operations: list[str] = Field(default_factory=list)
    duckdb_sql: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    output_columns: list[str] = Field(default_factory=list)
    skip_reason: str | None = None

    model_config = ConfigDict(extra="forbid")


class DatasetArtifact(BaseModel):
    artifact_id: str
    status: WorkflowStatus
    source_id: str | None = None
    rows: int | None = None
    columns: list[str] = Field(default_factory=list)
    csv_path: str | None = None
    parquet_path: str | None = None
    manifest_path: str | None = None
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class MethodologyNote(BaseModel):
    artifact_id: str
    notes: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source_bound: bool = True

    model_config = ConfigDict(extra="forbid")


class VisualizationSpec(BaseModel):
    artifact_id: str
    chart_type: str = "table"
    dataset_artifact_id: str | None = None
    encoding: dict[str, Any] = Field(default_factory=dict)
    status: WorkflowStatus = "skipped_with_reason"
    skip_reason: str | None = None

    model_config = ConfigDict(extra="forbid")


class CritiqueReport(BaseModel):
    artifact_id: str
    verdict: Literal[
        "pass",
        "pass_with_warnings",
        "needs_repair",
        "needs_user_clarification",
        "not_found",
    ]
    warnings: list[str] = Field(default_factory=list)
    repair_plan: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class FinalAnswer(BaseModel):
    artifact_id: str
    status: WorkflowStatus
    summary: str
    source_ids: list[str] = Field(default_factory=list)
    dataset_artifact_id: str | None = None
    no_data_reason: str | None = None
    clarification_question: str | None = None

    model_config = ConfigDict(extra="forbid")


class FeedbackArtifact(BaseModel):
    run_id: str
    artifact_id: str
    rating: Literal["positive", "negative", "neutral", "not_set"] = "not_set"
    user_comment: str | None = None
    requested_action: str | None = None
    target_state: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)

    model_config = ConfigDict(extra="forbid")


class TraceEvent(BaseModel):
    """Canonical workflow-owned trace event consumed by graph and UI adapters."""

    run_id: str
    state: str
    agent: str
    input_summary: str | None = None
    tool_calls: list[str] = Field(default_factory=list)
    output_artifact: str | None = None
    decision: str | None = None
    warnings: list[str] = Field(default_factory=list)
    started_at: str = Field(default_factory=utc_now_iso)
    duration_ms: int = 0
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")
