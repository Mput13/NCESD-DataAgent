from __future__ import annotations

from time import perf_counter

from app.artifacts import ArtifactStore
from app.config import Settings, load_settings
from app.contracts import TraceEvent, WorkflowOutcome, WorkflowResponse
from app.retrieval import SourceCatalog
from app.sources import build_source_adapters
from app.workflow.intent import build_intent


def run_query(query: str, *, settings: Settings | None = None, include_network: bool = False) -> WorkflowResponse:
    settings = settings or load_settings()
    response = WorkflowResponse(
        outcome=WorkflowOutcome.ERROR,
        message="Workflow did not complete.",
    )

    query = query.strip()
    if not query:
        response.outcome = WorkflowOutcome.NEEDS_CLARIFICATION
        response.message = "Query is empty."
        _add_event(response, "input", "needs_clarification", "empty query")
        _persist(settings, response)
        return response

    intent = build_intent(query)
    response.intent = intent
    _add_event(response, "intent", intent.query_kind.value, "query converted to structured intent")

    if intent.query_kind.value == "ambiguous" and intent.clarification_questions:
        response.outcome = WorkflowOutcome.NEEDS_CLARIFICATION
        response.message = "The query is ambiguous and needs clarification."
        _add_event(response, "clarification", "needs_user_input", "; ".join(intent.clarification_questions))
        _persist(settings, response)
        return response

    adapters = build_source_adapters(settings, include_network=include_network)
    catalog = SourceCatalog(adapters)
    _add_event(response, "source_registry", "ready", f"{catalog.adapter_count} source adapter(s) enabled")

    if catalog.adapter_count == 0:
        response.outcome = WorkflowOutcome.NOT_FOUND
        response.message = "No real source adapters are configured. Set FEDSTAT_ROOT, WORLD_BANK_ROOT, or enable CKAN network search."
        _add_event(response, "source_search", "not_found", "no configured source adapters")
        _persist(settings, response)
        return response

    start = perf_counter()
    candidates = catalog.search(query, limit_per_source=settings.max_candidates_per_source)
    duration_ms = int((perf_counter() - start) * 1000)
    _add_event(response, "source_search", "completed", f"{len(candidates)} candidate(s) found", duration_ms)
    response.selected_sources = candidates

    if not candidates:
        response.outcome = WorkflowOutcome.NOT_FOUND
        response.message = "No source candidates were found in the configured real sources."
        _persist(settings, response)
        return response

    response.outcome = WorkflowOutcome.NOT_FOUND
    response.message = (
        "Source candidates were found but coverage validation and deterministic extraction "
        "require the full Phase 2 graph (app.workflow.service.run_user_query)."
    )
    _add_event(response, "coverage", "skipped", f"{len(candidates)} candidate(s) require Phase 2 graph for extraction")
    _persist(settings, response)
    return response


def _add_event(
    response: WorkflowResponse,
    state: str,
    decision: str,
    detail: str = "",
    duration_ms: int | None = None,
) -> None:
    response.trace_events.append(
        TraceEvent(run_id=response.run_id, state=state, decision=decision, detail=detail, duration_ms=duration_ms)
    )


def _persist(settings: Settings, response: WorkflowResponse) -> None:
    ArtifactStore(settings.artifact_root).write_json(response.run_id, "workflow-response.json", response)
