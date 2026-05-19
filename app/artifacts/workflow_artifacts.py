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
    "partial",
    "gated",
    "skipped_with_reason",
    "needs_clarification",
    "no_data",
]

TerminalOutcome = Literal["passed", "needs_clarification", "not_found"]
SourceFamily = Literal["fedstat", "world_bank", "ckan"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class TaskIntent(BaseModel):
    category: Literal[
        "direct_lookup",
        "time_series",
        "comparison",
        "research",
        "derived_metric",
        "metadata_lookup",
        "clarification_needed",
    ]
    user_goal: str
    expected_output: Literal["answer", "table", "chart", "dataset", "methodology", "sources"]

    model_config = ConfigDict(extra="forbid")


class MeasureIntent(BaseModel):
    measure_id: str
    user_phrase: str
    canonical_concept: str
    aliases_ru: list[str] = Field(default_factory=list)
    aliases_en: list[str] = Field(default_factory=list)
    official_terms_ru: list[str] = Field(default_factory=list)
    official_terms_en: list[str] = Field(default_factory=list)
    possible_indicator_names: list[str] = Field(default_factory=list)
    possible_indicator_codes: list[str] = Field(default_factory=list)
    measurement_form: Literal[
        "level",
        "index",
        "rate",
        "share",
        "growth",
        "per_capita",
        "absolute_change",
        "unknown",
    ] = "unknown"
    unit_expectation: str | None = None
    must_not_confuse_with: list[str] = Field(default_factory=list)
    role: Literal["primary", "supporting", "numerator", "denominator", "normalizer", "context"] = "primary"

    model_config = ConfigDict(extra="forbid")


class GeographyIntent(BaseModel):
    name: str
    iso3: str | None = None
    aliases: list[str] = Field(default_factory=list)
    group: str | None = None

    model_config = ConfigDict(extra="forbid")


class PeriodIntent(BaseModel):
    start: str | None = None
    end: str | None = None
    values: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    def expanded_values(self) -> list[str]:
        if self.values:
            return [str(value) for value in self.values]
        if self.start and self.end and self.start.isdigit() and self.end.isdigit():
            start = int(self.start)
            end = int(self.end)
            if start <= end and end - start <= 100:
                return [str(year) for year in range(start, end + 1)]
        return [value for value in [self.start, self.end] if value]


class DimensionIntent(BaseModel):
    geographies: list[GeographyIntent] = Field(default_factory=list)
    period: PeriodIntent | None = None
    frequency: Literal["annual", "quarterly", "monthly", "daily", "unknown"] = "unknown"
    breakdowns: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class OperationIntent(BaseModel):
    wants_time_series: bool = False
    wants_comparison: bool = False
    wants_ranking: bool = False
    wants_growth_rate: bool = False
    wants_share: bool = False
    wants_per_capita: bool = False
    wants_real_terms: bool = False
    wants_nominal_terms: bool = False
    wants_visualization: bool = False

    model_config = ConfigDict(extra="forbid")


class SourceScope(BaseModel):
    requested_sources: list[SourceFamily] = Field(default_factory=list)
    source_constraint: Literal["none", "soft_preference", "hard_only"] = "none"
    source_hints: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class AmbiguityPolicy(BaseModel):
    needs_clarification: bool = False
    blocking_missing_fields: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    non_blocking_assumptions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class UserIntentArtifact(BaseModel):
    """Durable semantic artifact: what the user asked for."""

    original_query: str
    task: TaskIntent
    measures: list[MeasureIntent] = Field(default_factory=list)
    dimensions: DimensionIntent = Field(default_factory=DimensionIntent)
    operations: OperationIntent = Field(default_factory=OperationIntent)
    source_scope: SourceScope = Field(default_factory=SourceScope)
    ambiguity: AmbiguityPolicy = Field(default_factory=AmbiguityPolicy)
    assumptions: list[str] = Field(default_factory=list)
    rejected_interpretations: list[str] = Field(default_factory=list)
    confidence: float = 0.0

    model_config = ConfigDict(extra="forbid")

    def to_intent_frame(self) -> "IntentFrame":
        category_map: dict[str, QueryCategory] = {
            "direct_lookup": "simple",
            "time_series": "comparative",
            "comparison": "comparative",
            "research": "research",
            "derived_metric": "derived_metric",
            "metadata_lookup": "simple",
            "clarification_needed": "ambiguous",
        }
        known_fields: dict[str, Any] = {}
        geographies = [geo.iso3 or geo.name for geo in self.dimensions.geographies]
        if geographies:
            known_fields["countries"] = geographies
            known_fields["geography"] = ", ".join(geographies)
        if self.dimensions.period:
            periods = self.dimensions.period.expanded_values()
            if periods:
                known_fields["periods"] = periods
                known_fields["period"] = f"{periods[0]}-{periods[-1]}" if len(periods) > 1 else periods[0]
        if self.dimensions.frequency != "unknown":
            known_fields["frequency"] = self.dimensions.frequency
        if self.measures:
            known_fields["indicator"] = self.measures[0].canonical_concept
            known_fields["measures"] = [measure.canonical_concept for measure in self.measures]
        return IntentFrame(
            query=self.original_query,
            category=category_map.get(self.task.category, "simple"),
            known_fields=known_fields,
            missing_fields=list(self.ambiguity.blocking_missing_fields),
            needs_clarification=self.ambiguity.needs_clarification,
            source_preferences=list(self.source_scope.requested_sources),
            open_reasoning=["Adapter from canonical UserIntentArtifact"],
        )


class DimensionConstraints(BaseModel):
    geographies: list[str] = Field(default_factory=list)
    geography_group: str | None = None
    periods: list[str] = Field(default_factory=list)
    period_start: int | None = None
    period_end: int | None = None
    frequency: Literal["annual", "quarterly", "monthly", "daily", "unknown"] = "unknown"
    breakdowns: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RetrievalSourceScope(BaseModel):
    requested_sources: list[SourceFamily] = Field(default_factory=list)
    source_constraint: Literal["none", "soft_preference", "hard_only"] = "none"
    source_hints: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_source_scope(cls, scope: SourceScope) -> "RetrievalSourceScope":
        return cls(
            requested_sources=list(scope.requested_sources),
            source_constraint=scope.source_constraint,
            source_hints=list(scope.source_hints),
        )


class SourceBudgetPolicy(BaseModel):
    per_probe_limit: int = 5
    max_total_candidates: int | None = None
    final_source_count: int | None = None

    model_config = ConfigDict(extra="forbid")


class SearchProbe(BaseModel):
    probe_id: str
    text: str
    purpose: Literal[
        "raw_query_fallback",
        "canonical_concept",
        "official_term",
        "alias",
        "source_specific",
        "indicator_code",
        "broad_fallback",
    ]
    measure_id: str | None = None
    language: Literal["ru", "en", "mixed", "code"] = "mixed"
    priority: int = 50
    source_family_hint: SourceFamily | None = None
    basis: str | None = None
    origin: Literal["llm", "mechanical_fallback"] = "llm"

    model_config = ConfigDict(extra="forbid")


class RetrievalInput(BaseModel):
    """Transient search-execution artifact for Source Scouts and trace."""

    original_query: str
    probes: list[SearchProbe] = Field(default_factory=list)
    dimension_constraints: DimensionConstraints = Field(default_factory=DimensionConstraints)
    source_scope: RetrievalSourceScope = Field(default_factory=RetrievalSourceScope)
    budget_policy: SourceBudgetPolicy = Field(default_factory=SourceBudgetPolicy)
    trace_notes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


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
    expanded_indicators: list[dict] = Field(default_factory=list)
    # Each item: {"name_ru": str, "name_en": str, "search_query_ru": str, "search_query_en": str}

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
    partial_note: str | None = None
    # Slice-level validation fields (Plan B)
    matched_geographies: list[str] = Field(default_factory=list)
    matched_periods: list[str] = Field(default_factory=list)
    requested_slice_rows: int = 0
    extraction_ready: bool = False

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
