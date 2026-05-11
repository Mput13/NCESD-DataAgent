"""Phase 2 LangGraph workflow graph.

build_phase2_graph() returns a compiled LangGraph StateGraph with nodes for the
full Phase 2 architecture-stack workflow through deterministic extraction, with
explicit finalization_pending at the end.

Node names:
- supervisor
- intent_analyst
- research_designer
- source_scouts
- coverage_schema
- extraction_planner
- deterministic_tools
- finalization_pending

Routing:
- Ambiguous intent -> finalization_pending (pending_reason=needs_clarification_finalization_pending)
- No selected sources -> finalization_pending (pending_reason=not_found_finalization_pending)
- Otherwise: coverage_schema -> extraction_planner -> deterministic_tools -> finalization_pending
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.artifacts.workflow_artifacts import (
    EvidenceBundleArtifact,
    TraceEvent,
)
from app.workflow.state import (
    Phase2State,
    analyze_intent,
    design_research,
    new_run_id,
)

# ---------------------------------------------------------------------------
# Runtime helpers
# ---------------------------------------------------------------------------


def _llm_is_ready() -> bool:
    """Return True if Yandex credentials are configured in the environment."""
    from app.llm.yandex_ai_studio import qwen_credential_gate
    return qwen_credential_gate()["status"] == "ready"


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------


def _node_supervisor(state: Phase2State) -> Phase2State:
    """Supervisor: triage query complexity and decide routing budget.

    Calls Qwen to classify query as simple/complex/research/no_data and sets
    _supervisor_route in state so _route_after_intent can use it.
    Simple/direct queries skip Research Designer (direct path per ARCHITECTURE_STACK.md).
    """
    from pydantic import BaseModel

    run_id = state.get("run_id") or new_run_id()
    query = str(state.get("query") or "")
    live_llm = bool(state.get("_live_llm_required") or _llm_is_ready())
    trace_events = list(state.get("trace_events") or [])
    component_statuses = dict(state.get("component_statuses") or {})

    supervisor_route = "research"  # default: full research path

    if live_llm:
        try:
            from app.llm.yandex_ai_studio import YandexAIStudioClient, qwen_credential_gate

            gate = qwen_credential_gate()
            if gate["status"] != "gated_skip":
                class _TriageSchema(BaseModel):
                    route: str = "research"  # direct | research | no_data
                    reasoning: str = ""

                client = YandexAIStudioClient()
                result = client.structured_chat(
                    [
                        {
                            "role": "system",
                            "content": (
                                "Ты — супервизор DataAgent. Определи тип запроса:\n"
                                "- direct: простой прямой поиск одного показателя для одной страны/периода\n"
                                "- research: сравнение, исследование, производная метрика, несколько источников\n"
                                "- no_data: запрос явно о данных, которых нет или не может быть\n"
                                "Отвечай только в формате JSON."
                            ),
                        },
                        {"role": "user", "content": f"Запрос: {query}"},
                    ],
                    schema=_TriageSchema,
                    temperature=0.0,
                    max_tokens=128,
                )
                if result.route in ("direct", "research", "no_data"):
                    supervisor_route = result.route
        except Exception as exc:
            trace_events.append(
                TraceEvent(
                    run_id=run_id,
                    state="supervisor",
                    agent="Supervisor",
                    decision="triage_llm_failed_using_research_default",
                    warnings=[str(exc)],
                    payload={"error": str(exc)},
                )
            )

    trace_events.append(
        TraceEvent(
            run_id=run_id,
            state="supervisor",
            agent="Supervisor",
            input_summary=query[:200],
            decision=supervisor_route,
            payload={"run_id": run_id, "route": supervisor_route},
        )
    )
    component_statuses["supervisor"] = "ok"

    return {
        **state,
        "run_id": run_id,
        "_supervisor_route": supervisor_route,  # type: ignore[typeddict-unknown-key]
        "trace_events": trace_events,
        "component_statuses": component_statuses,
        "finalization_pending": False,
    }


def _node_intent_analyst(state: Phase2State) -> Phase2State:
    """Intent Analyst: classify and structure the user query."""
    run_id = str(state.get("run_id") or "")
    query = str(state.get("query") or "")
    live_llm = bool(state.get("_live_llm_required") or _llm_is_ready())
    trace_events = list(state.get("trace_events") or [])
    component_statuses = dict(state.get("component_statuses") or {})

    try:
        intent = analyze_intent(query, live_llm_required=live_llm)
        status = "ok"
    except Exception as exc:
        # LLM unavailable — gate this run, do not silently fall back to keyword matching
        trace_events.append(
            TraceEvent(
                run_id=run_id,
                state="intent_analyst",
                agent="Intent Analyst",
                decision="gated",
                warnings=[str(exc)],
                payload={"error": str(exc)},
            )
        )
        component_statuses["intent_analyst"] = "gated"
        return {
            **state,
            "intent": None,
            "finalization_pending": True,
            "pending_reason": f"intent_llm_gated:{exc}",
            "trace_events": trace_events,
            "component_statuses": component_statuses,
        }

    trace_events.append(
        TraceEvent(
            run_id=run_id,
            state="intent_analyst",
            agent="Intent Analyst",
            output_artifact="IntentFrame",
            decision=status,
            payload={
                "category": intent.category,
                "needs_clarification": intent.needs_clarification,
                "status": status,
            },
        )
    )
    component_statuses["intent_analyst"] = status

    return {
        **state,
        "intent": intent,
        "trace_events": trace_events,
        "component_statuses": component_statuses,
    }


def _node_research_designer(state: Phase2State) -> Phase2State:
    """Research Designer: expand complex intent into design structure."""
    run_id = str(state.get("run_id") or "")
    intent = state.get("intent")
    live_llm = bool(state.get("_live_llm_required") or _llm_is_ready())
    trace_events = list(state.get("trace_events") or [])
    component_statuses = dict(state.get("component_statuses") or {})

    if intent is None:
        component_statuses["research_designer"] = "skipped_no_intent"
        return {**state, "trace_events": trace_events, "component_statuses": component_statuses}

    try:
        design = design_research(intent, live_llm_required=live_llm)
        status = "ok"
    except Exception as exc:
        # LLM unavailable — gate this run
        trace_events.append(
            TraceEvent(
                run_id=run_id,
                state="research_designer",
                agent="Research Designer",
                decision="gated",
                warnings=[str(exc)],
                payload={"error": str(exc)},
            )
        )
        component_statuses["research_designer"] = "gated"
        return {
            **state,
            "research_design": None,
            "finalization_pending": True,
            "pending_reason": f"research_designer_llm_gated:{exc}",
            "trace_events": trace_events,
            "component_statuses": component_statuses,
        }

    trace_events.append(
        TraceEvent(
            run_id=run_id,
            state="research_designer",
            agent="Research Designer",
            output_artifact=design.artifact_id,
            decision=status,
            payload={
                "artifact_id": design.artifact_id,
                "hypotheses_count": len(design.hypotheses),
                "status": status,
            },
        )
    )
    component_statuses["research_designer"] = status

    return {
        **state,
        "research_design": design,
        "trace_events": trace_events,
        "component_statuses": component_statuses,
    }


def _node_source_scouts(state: Phase2State) -> Phase2State:
    """Source Scouts: run retrieval across FedStat, World Bank, and CKAN."""
    run_id = str(state.get("run_id") or "")
    query = str(state.get("query") or "")
    intent = state.get("intent")
    trace_events = list(state.get("trace_events") or [])
    component_statuses = dict(state.get("component_statuses") or {})

    expected_sources = list(intent.source_preferences if intent else [])
    index_manifest_path = Path(
        str(state.get("_index_manifest_path") or
            ".planning/phases/01-data-architecture-research/embedding-index-manifest.json")
    )

    evidence = EvidenceBundleArtifact(
        retrieval_status="gated",
        qdrant_status="unknown",
    )
    status = "ok"

    if index_manifest_path.exists():
        try:
            from app.workflow.nodes.scouts import run_source_scouts
            evidence = run_source_scouts(
                query,
                expected_sources=expected_sources,
                index_manifest_path=index_manifest_path,
            )
            status = "ok" if evidence.selected_sources else "no_candidate"
        except Exception as exc:
            evidence = EvidenceBundleArtifact(
                retrieval_status="gated",
                qdrant_status="error",
            )
            status = "gated"
            trace_events.append(
                TraceEvent(
                    run_id=run_id,
                    state="source_scouts",
                    agent="Source Scouts",
                    decision="gated",
                    warnings=[str(exc)],
                    payload={"error": str(exc)},
                )
            )
    else:
        status = "gated_no_index"

    trace_events.append(
        TraceEvent(
            run_id=run_id,
            state="source_scouts",
            agent="FedStat Scout, World Bank Scout, CKAN Scout",
            output_artifact="EvidenceBundleArtifact",
            decision=status,
            payload={
                "selected_count": len(evidence.selected_sources),
                "rejected_count": len(evidence.rejected_sources),
                "qdrant_status": evidence.qdrant_status,
                "status": status,
            },
        )
    )
    component_statuses["source_scouts"] = status

    return {
        **state,
        "evidence": evidence,
        "trace_events": trace_events,
        "component_statuses": component_statuses,
    }


def _node_coverage_schema(state: Phase2State) -> Phase2State:
    """Coverage & Schema: check real coverage for selected sources."""
    run_id = str(state.get("run_id") or "")
    evidence = state.get("evidence") or EvidenceBundleArtifact()
    intent = state.get("intent")
    trace_events = list(state.get("trace_events") or [])
    component_statuses = dict(state.get("component_statuses") or {})

    intent_fields: dict[str, Any] = dict(intent.known_fields if intent else {})
    coverage_reports = list(state.get("coverage_reports") or [])

    if not evidence.selected_sources:
        status = "skipped_no_sources"
    else:
        live_llm = bool(state.get("_live_llm_required") or _llm_is_ready())
        try:
            from app.workflow.nodes.coverage import run_coverage_preview
            new_reports = run_coverage_preview(
                evidence, intent_fields=intent_fields, live_llm_required=live_llm
            )
            coverage_reports.extend(new_reports)
            status = "ok"
        except Exception as exc:
            status = "gated"
            trace_events.append(
                TraceEvent(
                    run_id=run_id,
                    state="coverage_schema",
                    agent="Coverage & Schema",
                    decision="gated",
                    warnings=[str(exc)],
                    payload={"error": str(exc)},
                )
            )

    trace_events.append(
        TraceEvent(
            run_id=run_id,
            state="coverage_schema",
            agent="Coverage & Schema",
            output_artifact="CoverageReport",
            decision=status,
            payload={
                "report_count": len(coverage_reports),
                "status": status,
            },
        )
    )
    component_statuses["coverage_schema"] = status

    return {
        **state,
        "coverage_reports": coverage_reports,
        "trace_events": trace_events,
        "component_statuses": component_statuses,
    }


def _node_extraction_planner(state: Phase2State) -> Phase2State:
    """Extraction Planner: build a safe allowlist-constrained extraction plan."""
    run_id = str(state.get("run_id") or "")
    intent = state.get("intent")
    coverage_reports = list(state.get("coverage_reports") or [])
    trace_events = list(state.get("trace_events") or [])
    component_statuses = dict(state.get("component_statuses") or {})

    live_llm = bool(state.get("_live_llm_required") or _llm_is_ready())
    try:
        from app.workflow.nodes.extraction_planner import build_extraction_plan
        extraction_plan = build_extraction_plan(
            intent, coverage_reports, live_llm_required=live_llm  # type: ignore[arg-type]
        )
        status = extraction_plan.status
    except Exception as exc:
        from app.artifacts.workflow_artifacts import ExtractionPlan
        from uuid import uuid4
        extraction_plan = ExtractionPlan(
            artifact_id=f"extraction-plan-{uuid4().hex[:8]}",
            status="skipped_with_reason",
            operations=[],
            skip_reason=f"planner_error:{exc}",
        )
        status = "gated"
        trace_events.append(
            TraceEvent(
                run_id=run_id,
                state="extraction_planner",
                agent="Extraction Planner",
                decision="gated",
                warnings=[str(exc)],
                payload={"error": str(exc)},
            )
        )

    trace_events.append(
        TraceEvent(
            run_id=run_id,
            state="extraction_planner",
            agent="Extraction Planner",
            output_artifact=extraction_plan.artifact_id,
            decision=status,
            payload={
                "plan_id": extraction_plan.artifact_id,
                "operations": extraction_plan.operations,
                "status": status,
            },
        )
    )
    component_statuses["extraction_planner"] = status

    return {
        **state,
        "extraction_plan": extraction_plan,
        "trace_events": trace_events,
        "component_statuses": component_statuses,
    }


def _node_deterministic_tools(state: Phase2State) -> Phase2State:
    """Deterministic Tools: execute extraction plan and persist artifacts."""
    from app.workflow.nodes.deterministic_tools import run_deterministic_tools

    output_dir = Path(
        str(state.get("_artifact_dir") or ".planning/phases/02-jury-mvp/workflow-runs")
    ) / str(state.get("run_id") or "unknown")

    return run_deterministic_tools(state, output_dir=output_dir)  # type: ignore[return-value]


def _node_finalization_pending(state: Phase2State) -> Phase2State:
    """Finalization pending: mark state as awaiting plan 02-06 finalization."""
    run_id = str(state.get("run_id") or "")
    trace_events = list(state.get("trace_events") or [])
    component_statuses = dict(state.get("component_statuses") or {})

    pending_reason = str(state.get("pending_reason") or "awaiting_plan_02_06_finalization")

    trace_events.append(
        TraceEvent(
            run_id=run_id,
            state="finalization_pending",
            agent="Supervisor",
            decision="finalization_pending",
            payload={
                "pending_reason": pending_reason,
                "dataset_artifacts": len(state.get("dataset_artifacts") or []),
                "script_artifacts": len(state.get("script_artifacts") or []),
            },
        )
    )
    component_statuses["finalization"] = "pending"

    return {
        **state,
        "finalization_pending": True,
        "pending_reason": pending_reason,
        "trace_events": trace_events,
        "component_statuses": component_statuses,
    }


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------


def _route_after_intent(state: Phase2State) -> str:
    """Route after intent analysis.

    - needs_clarification -> finalization_pending
    - finalization_pending already set (LLM gated) -> finalization_pending
    - supervisor_route=direct -> source_scouts (skip Research Designer)
    - otherwise -> research_designer
    """
    if state.get("finalization_pending"):
        return "finalization_pending_gated"
    intent = state.get("intent")
    if intent and intent.needs_clarification:
        return "finalization_pending_clarification"
    supervisor_route = state.get("_supervisor_route", "research")  # type: ignore[call-overload]
    if supervisor_route == "direct":
        return "source_scouts_direct"
    return "research_designer"


def _route_after_scouts(state: Phase2State) -> str:
    """Route after source scouts: no sources -> finalization_pending, else coverage."""
    evidence = state.get("evidence") or EvidenceBundleArtifact()
    if not evidence.selected_sources:
        return "finalization_pending_not_found"
    return "coverage_schema"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_phase2_graph():
    """Build and compile the Phase 2 LangGraph StateGraph.

    Returns a compiled graph with nodes:
    supervisor -> intent_analyst -> [research_designer or finalization_pending]
    -> source_scouts -> [coverage_schema or finalization_pending]
    -> extraction_planner -> deterministic_tools -> finalization_pending

    Type annotation omitted to avoid import issues; callers receive a compiled
    LangGraph object that supports .invoke(state) -> state.
    """
    builder = StateGraph(Phase2State)

    # Add all nodes
    builder.add_node("supervisor", _node_supervisor)
    builder.add_node("intent_analyst", _node_intent_analyst)
    builder.add_node("research_designer", _node_research_designer)
    builder.add_node("source_scouts", _node_source_scouts)
    builder.add_node("coverage_schema", _node_coverage_schema)
    builder.add_node("extraction_planner", _node_extraction_planner)
    builder.add_node("deterministic_tools", _node_deterministic_tools)
    builder.add_node("finalization_pending", _node_finalization_pending)

    # Entry point
    builder.add_edge(START, "supervisor")
    builder.add_edge("supervisor", "intent_analyst")

    # Conditional routing after intent analysis
    builder.add_conditional_edges(
        "intent_analyst",
        _route_after_intent,
        {
            "research_designer": "research_designer",
            "source_scouts_direct": "source_scouts",   # direct path: skip Research Designer
            "finalization_pending_clarification": "finalization_pending",
            "finalization_pending_gated": "finalization_pending",
        },
    )

    # Research designer -> source scouts
    builder.add_edge("research_designer", "source_scouts")

    # Conditional routing after scouts
    builder.add_conditional_edges(
        "source_scouts",
        _route_after_scouts,
        {
            "coverage_schema": "coverage_schema",
            "finalization_pending_not_found": "finalization_pending",
        },
    )

    # Main extraction path
    builder.add_edge("coverage_schema", "extraction_planner")
    builder.add_edge("extraction_planner", "deterministic_tools")
    builder.add_edge("deterministic_tools", "finalization_pending")

    # Finalization is terminal
    builder.add_edge("finalization_pending", END)

    return builder.compile()
