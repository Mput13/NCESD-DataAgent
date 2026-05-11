from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.artifacts.workflow_artifacts import (
    CoverageReport,
    DatasetArtifact,
    EvidenceBundleArtifact,
    ExtractionPlan,
    FinalAnswer,
    IntentFrame,
    ResearchDesignArtifact,
    SourceRejectionRecord,
    TraceEvent,
)


RouteName = Literal[
    "Direct lookup",
    "Ambiguous lookup",
    "Comparative query",
    "Research query",
    "No-data check",
]


@dataclass(frozen=True)
class NodeContract:
    name: str
    role: str
    budget: str
    tool_scope: tuple[str, ...]
    emits: tuple[str, ...]


@dataclass(frozen=True)
class RouteBudget:
    name: RouteName
    tool_call_limit: int
    candidate_limit: int
    scout_fanout: int
    critic_passes: int


NODE_CONTRACTS: tuple[NodeContract, ...] = (
    NodeContract(
        name="Supervisor",
        role="Lead DataAgent routing, checkpoint, and trace coordinator",
        budget="2 LLM calls or deterministic classifier fallback",
        tool_scope=("intent_schema", "route_budget"),
        emits=("IntentFrame", "TraceEvent"),
    ),
    NodeContract(
        name="Research Designer",
        role="Expand non-trivial questions into hypotheses, dimensions, and indicators",
        budget="1 structured artifact per complex case",
        tool_scope=("source_card_summary",),
        emits=("ResearchDesignArtifact", "TraceEvent"),
    ),
    NodeContract(
        name="FedStat Scout",
        role="Find FedStat source-card candidates",
        budget="5 candidates",
        tool_scope=("hybrid_retrieval", "fedstat_metadata"),
        emits=("EvidenceBundleArtifact", "TraceEvent"),
    ),
    NodeContract(
        name="World Bank Scout",
        role="Find World Bank source-card candidates",
        budget="5 candidates",
        tool_scope=("hybrid_retrieval", "world_bank_metadata"),
        emits=("EvidenceBundleArtifact", "TraceEvent"),
    ),
    NodeContract(
        name="CKAN Scout",
        role="Bounded CKAN package/resource discovery",
        budget="package_search rows<=5, package_show top<=3",
        tool_scope=("ckan_package_search", "ckan_package_show"),
        emits=("EvidenceBundleArtifact", "TraceEvent"),
    ),
    NodeContract(
        name="Coverage & Schema",
        role="Check real coverage, units, geography, frequency, and schema risk",
        budget="1 preview per selected candidate",
        tool_scope=("fedstat_normalize_preview", "wb_coverage_preview", "ckan_package_show"),
        emits=("CoverageReport", "TraceEvent"),
    ),
    NodeContract(
        name="Extraction Planner",
        role="Create safe DuckDB SQL-first extraction plans",
        budget="1 plan per selected source",
        tool_scope=("run_duckdb_query", "build_dataset_artifact"),
        emits=("ExtractionPlan", "TraceEvent"),
    ),
    NodeContract(
        name="Deterministic Tools",
        role="Execute coverage, extraction, dataset export, and visualization tools",
        budget="No LLM numeric extraction",
        tool_scope=("run_duckdb_query", "export_csv_parquet_manifest"),
        emits=("DatasetArtifact", "TraceEvent"),
    ),
    NodeContract(
        name="Methodology Critic",
        role="Validate units, coverage, no-data honesty, and source-bound evidence",
        budget="1 critic pass for direct routes, 2 for research routes",
        tool_scope=("coverage_report", "dataset_artifact", "source_rejections"),
        emits=("CritiqueReport", "TraceEvent"),
    ),
    NodeContract(
        name="Narrator",
        role="Assemble final source-bound answer without unsupported numeric values",
        budget="1 final artifact",
        tool_scope=("final_answer_template", "methodology_note"),
        emits=("FinalAnswer", "TraceEvent"),
    ),
    NodeContract(
        name="Visualization",
        role="Render a deterministic visualization spec from DatasetArtifact when present",
        budget="1 chart spec; table fallback",
        tool_scope=("render_visualization_from_dataset_artifact",),
        emits=("VisualizationSpec", "TraceEvent"),
    ),
)


QUERY_BUDGETS: dict[RouteName, RouteBudget] = {
    "Direct lookup": RouteBudget("Direct lookup", 4, 3, 1, 1),
    "Ambiguous lookup": RouteBudget("Ambiguous lookup", 3, 3, 1, 0),
    "Comparative query": RouteBudget("Comparative query", 8, 5, 2, 1),
    "Research query": RouteBudget("Research query", 12, 7, 3, 2),
    "No-data check": RouteBudget("No-data check", 8, 5, 3, 1),
}


class GraphState(BaseModel):
    """Typed state passed through the runnable Phase 1 graph slice."""

    run_id: str
    case_id: str | None = None
    query: str
    route: RouteName = "Direct lookup"
    intent: IntentFrame | None = None
    research_design: ResearchDesignArtifact | None = None
    evidence: EvidenceBundleArtifact = Field(default_factory=EvidenceBundleArtifact)
    coverage_report: CoverageReport | None = None
    extraction_plan: ExtractionPlan | None = None
    dataset_artifact: DatasetArtifact | None = None
    source_rejections: list[SourceRejectionRecord] = Field(default_factory=list)
    final_answer: FinalAnswer | None = None
    trace_events: list[TraceEvent] = Field(default_factory=list)
    qdrant_status: str = "unknown"
    status: Literal["ok", "gated", "needs_clarification", "no_data"] = "ok"
    no_data_reason: str | None = None

    model_config = ConfigDict(extra="forbid")


def route_from_category(category: str, *, needs_clarification: bool = False) -> RouteName:
    if needs_clarification or category == "ambiguous":
        return "Ambiguous lookup"
    if category == "comparative":
        return "Comparative query"
    if category in {"research", "derived_metric"}:
        return "Research query"
    if category == "no_data":
        return "No-data check"
    return "Direct lookup"


def build_initial_state(query: str, *, case_id: str | None = None) -> GraphState:
    run_id = f"phase1-{uuid4().hex[:12]}"
    return GraphState(
        run_id=run_id,
        case_id=case_id,
        query=query,
        trace_events=[
            TraceEvent(
                run_id=run_id,
                state="received",
                agent="Supervisor",
                input_summary=query,
                decision="start_triage",
            )
        ],
    )


def append_trace(
    state: GraphState,
    *,
    state_name: str,
    agent: str,
    decision: str,
    tool_calls: list[str] | None = None,
    output_artifact: str | None = None,
    warnings: list[str] | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    state.trace_events.append(
        TraceEvent(
            run_id=state.run_id,
            state=state_name,
            agent=agent,
            tool_calls=tool_calls or [],
            output_artifact=output_artifact,
            decision=decision,
            warnings=warnings or [],
            payload=payload or {},
        )
    )


class Phase1GraphCheckpoint:
    """Diagnostic checkpoint graph for Phase 1.

    Validates state and records a trace event. Full LangGraph node wiring is Phase 2 work
    (see .planning/phases/02-*).
    """

    def invoke(self, state: GraphState) -> GraphState:
        if state.route not in QUERY_BUDGETS:
            raise ValueError(f"Unknown query route for Phase 1 checkpoint: {state.route}")
        append_trace(
            state,
            state_name="checkpoint",
            agent="Supervisor",
            decision="Phase 1 narrow runnable graph checkpoint passed",
            payload={"budget": QUERY_BUDGETS[state.route].__dict__},
        )
        return state


def build_checkpoint_graph() -> Phase1GraphCheckpoint:
    """Return the diagnostic Phase 1 checkpoint graph object."""

    return Phase1GraphCheckpoint()
