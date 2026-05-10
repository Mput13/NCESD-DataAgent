from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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

TerminalOutcome = Literal["passed", "needs_clarification", "not_found"]


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
    records: list[dict[str, Any]] = Field(default_factory=list)
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
    status: Literal["recorded", "rerun", "fix_requested"] = "recorded"
    fix_request_reason: str | None = None
    path: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)

    model_config = ConfigDict(extra="forbid")


class FeedbackAction(BaseModel):
    """Frontend action the user can take to repair or rate a workflow response."""

    action_id: str
    label: str
    action_type: Literal["rate", "clarify", "request_fix", "retry", "download"]
    target_artifact_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class ScriptArtifact(BaseModel):
    """Generated deterministic extraction script and its execution context."""

    artifact_id: str
    language: Literal["python", "sql", "bash"] = "python"
    path: str | None = None
    script_path: str | None = None
    content: str | None = None
    entrypoint: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    source_dataset_artifact_id: str | None = None
    dataset_artifact_id: str | None = None
    sha256: str | None = None
    downloadable: bool = True
    download_filename: str | None = None
    display_name: str | None = None
    mime_type: str = "text/x-python"
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class NoDataExplanationArtifact(BaseModel):
    """Evidence showing why a trusted-source search ended in not_found."""

    artifact_id: str
    checked_sources: list[dict[str, Any]] = Field(default_factory=list)
    rejected_sources: list[dict[str, Any]] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    search_strategy: str
    alternatives: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class WorkflowResponse(BaseModel):
    """Shared Phase 2 frontend/eval/CLI response contract."""

    run_id: str
    final_outcome: TerminalOutcome
    message: str
    answer_blocks: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    selected_sources: list[dict[str, Any]] = Field(default_factory=list)
    rejected_sources: list[dict[str, Any]] = Field(default_factory=list)
    coverage: list[CoverageReport] = Field(default_factory=list)
    extraction_plan: ExtractionPlan | None = None
    dataset_artifacts: list[DatasetArtifact] = Field(default_factory=list)
    script_artifacts: list[ScriptArtifact] = Field(default_factory=list)
    visualization: VisualizationSpec | None = None
    trace_events: list[TraceEvent] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    not_found_evidence: NoDataExplanationArtifact | None = None
    feedback_actions: list[FeedbackAction] = Field(default_factory=list)
    component_statuses: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_terminal_outcome_requirements(self) -> WorkflowResponse:
        if self.final_outcome == "passed":
            if not self.dataset_artifacts:
                raise ValueError("passed WorkflowResponse requires at least one dataset artifact")
            if not self.script_artifacts:
                raise ValueError("passed WorkflowResponse requires at least one script artifact")
        if self.final_outcome == "needs_clarification" and not self.clarification_questions:
            raise ValueError("needs_clarification WorkflowResponse requires clarification questions")
        if self.final_outcome == "not_found" and self.not_found_evidence is None:
            raise ValueError("not_found WorkflowResponse requires not_found_evidence")
        return self


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
