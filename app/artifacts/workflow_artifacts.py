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
    "skipped_no_sources",
    "no_covered_slice",
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


class RetrievalChannelStatus(BaseModel):
    """Per-channel retrieval outcome preserved across scout handoff."""

    channel: Literal["lexical", "dense", "graph", "ckan"]
    status: Literal["ok", "partial", "gated", "error", "empty", "not_run", "skipped"]
    required: bool = False
    selected_count: int = 0
    rejected_count: int = 0
    reason: str | None = None
    error: str | None = None

    model_config = ConfigDict(extra="forbid")


class SourceCandidate(BaseModel):
    """Typed source candidate selected by scouts for coverage inspection."""

    source_candidate_id: str
    source_family: str
    card_id: str
    chunk_id: str | None = None
    dataset_id: str | None = None
    title: str = ""
    score: float = 0.0
    relevance_score: float = 0.0
    retrieval_mode: str = ""
    retrieval_paths: list[str] = Field(default_factory=list)
    evidence_terms: list[str] = Field(default_factory=list)
    match_mode: str | None = None
    provenance_url: str | None = None
    why_matched: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=list)
    resource_count: int | None = None
    promoted_resources: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_provenance: dict[str, Any] = Field(default_factory=dict)
    adapter_name: str | None = None
    extraction_ready: bool = True
    extraction_blockers: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class RejectedSourceCandidate(BaseModel):
    """Typed source candidate rejected before coverage with explicit reasons."""

    source_candidate_id: str
    source_family: str | None = None
    card_id: str | None = None
    chunk_id: str | None = None
    dataset_id: str | None = None
    title: str = ""
    score: float = 0.0
    retrieval_mode: str = ""
    retrieval_paths: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    retrieval_provenance: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class EvidenceBundleArtifact(BaseModel):
    """Compressed source evidence passed between scouts and coverage."""

    selected_for_coverage: list[SourceCandidate] = Field(default_factory=list)
    rejected_candidates: list[RejectedSourceCandidate] = Field(default_factory=list)
    channel_statuses: list[RetrievalChannelStatus] = Field(default_factory=list)
    subgraph_context: dict[str, Any] | None = None
    # Backwards-compatible aliases for UI/narrator/tests during migration.
    selected_sources: list[dict[str, Any]] = Field(default_factory=list)
    rejected_sources: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_status: str = "not_run"
    qdrant_status: str = "unknown"
    dense_status: str = "unknown"

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def populate_typed_candidate_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        values = dict(data)
        if not values.get("selected_for_coverage") and values.get("selected_sources"):
            values["selected_for_coverage"] = [
                _source_candidate_from_legacy(item)
                for item in values.get("selected_sources") or []
            ]
        if not values.get("rejected_candidates") and values.get("rejected_sources"):
            values["rejected_candidates"] = [
                _rejected_candidate_from_legacy(item)
                for item in values.get("rejected_sources") or []
            ]
        return values

    @model_validator(mode="after")
    def sync_legacy_candidate_fields(self) -> EvidenceBundleArtifact:
        if not self.selected_sources and self.selected_for_coverage:
            self.selected_sources = [
                candidate.model_dump(exclude_none=True)
                for candidate in self.selected_for_coverage
            ]
        if not self.rejected_sources and self.rejected_candidates:
            self.rejected_sources = [
                candidate.model_dump(exclude_none=True)
                for candidate in self.rejected_candidates
            ]
        return self


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
    source_candidate_id: str | None = None
    source_family: str | None = None
    retrieval_provenance: dict[str, Any] = Field(default_factory=dict)
    extraction_ready: bool | None = None
    extraction_blockers: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    available_periods: list[str] = Field(default_factory=list)
    available_geographies: list[str] = Field(default_factory=list)
    unit: str | None = None
    frequency: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    gated_reason: str | None = None
    # Slice-level validation fields (Plan B)
    matched_geographies: list[str] = Field(default_factory=list)
    matched_periods: list[str] = Field(default_factory=list)
    requested_slice_rows: int = 0
    extraction_ready: bool = False

    model_config = ConfigDict(extra="forbid")


class ExtractionPlan(BaseModel):
    artifact_id: str
    source_id: str | None = None
    source_family: str | None = None
    adapter_name: str | None = None
    source_candidate_ids: list[str] = Field(default_factory=list)
    coverage_report_ids: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    compile_mode: Literal["deterministic", "llm", "gated", "compatibility_fallback"] = "deterministic"
    status: WorkflowStatus = "skipped_with_reason"
    operations: list[str] = Field(default_factory=list)
    duckdb_sql: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    output_columns: list[str] = Field(default_factory=list)
    skip_reason: str | None = None

    model_config = ConfigDict(extra="forbid")


def _source_candidate_from_legacy(item: Any) -> dict[str, Any]:
    source = dict(item or {}) if isinstance(item, dict) else {}
    card_id = str(source.get("card_id") or source.get("dataset_id") or source.get("source_id") or "unknown")
    family = str(source.get("source_family") or source.get("family") or "unknown")
    retrieval_provenance = dict(source.get("retrieval_provenance") or {})
    for key in ("fusion_modes", "fusion_ranks", "fusion_raw_scores", "retrieval_paths"):
        if key in source and key not in retrieval_provenance:
            retrieval_provenance[key] = source.get(key)
    paths = source.get("retrieval_paths") or retrieval_provenance.get("fusion_modes") or []
    evidence_terms = source.get("evidence_terms") or source.get("evidence_keywords") or []
    blockers = list(source.get("extraction_blockers") or [])
    return {
        "source_candidate_id": str(source.get("source_candidate_id") or card_id),
        "source_family": family,
        "card_id": card_id,
        "chunk_id": source.get("chunk_id"),
        "dataset_id": source.get("dataset_id") or source.get("source_id"),
        "title": str(source.get("title") or ""),
        "score": float(source.get("score") or 0.0),
        "relevance_score": float(source.get("relevance_score") or 0.0),
        "retrieval_mode": str(source.get("retrieval_mode") or ""),
        "retrieval_paths": [str(path) for path in paths],
        "evidence_terms": [str(term) for term in evidence_terms],
        "match_mode": source.get("match_mode"),
        "provenance_url": source.get("provenance_url"),
        "why_matched": str(source.get("why_matched") or ""),
        "risk_flags": [str(flag) for flag in source.get("risk_flags") or []],
        "formats": [str(fmt) for fmt in source.get("formats") or []],
        "resource_count": source.get("resource_count"),
        "promoted_resources": list(source.get("promoted_resources") or []),
        "retrieval_provenance": retrieval_provenance,
        "adapter_name": source.get("adapter_name") or _adapter_for_family(family),
        "extraction_ready": bool(source.get("extraction_ready", not blockers)),
        "extraction_blockers": blockers,
        "metadata": dict(source.get("metadata") or {}),
    }


def _rejected_candidate_from_legacy(item: Any) -> dict[str, Any]:
    source = dict(item or {}) if isinstance(item, dict) else {}
    card_id = source.get("card_id") or source.get("dataset_id") or source.get("source_id")
    retrieval_provenance = dict(source.get("retrieval_provenance") or {})
    for key in ("fusion_modes", "fusion_ranks", "fusion_raw_scores", "retrieval_paths"):
        if key in source and key not in retrieval_provenance:
            retrieval_provenance[key] = source.get(key)
    paths = source.get("retrieval_paths") or retrieval_provenance.get("fusion_modes") or []
    return {
        "source_candidate_id": str(source.get("source_candidate_id") or card_id or "unknown"),
        "source_family": source.get("source_family"),
        "card_id": card_id,
        "chunk_id": source.get("chunk_id"),
        "dataset_id": source.get("dataset_id") or source.get("source_id"),
        "title": str(source.get("title") or ""),
        "score": float(source.get("score") or 0.0),
        "retrieval_mode": str(source.get("retrieval_mode") or ""),
        "retrieval_paths": [str(path) for path in paths],
        "rejection_reasons": [str(reason) for reason in source.get("rejection_reasons") or []],
        "retrieval_provenance": retrieval_provenance,
        "metadata": dict(source.get("metadata") or {}),
    }


def _adapter_for_family(source_family: str) -> str | None:
    family = source_family.strip().lower()
    return {
        "fedstat": "extract_fedstat_dataset",
        "world_bank": "extract_world_bank_dataset",
        "worldbank": "extract_world_bank_dataset",
        "ckan": "extract_ckan_dataset",
    }.get(family)


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
