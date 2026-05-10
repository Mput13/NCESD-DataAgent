"""Phase 2 workflow service API.

Provides:
- WorkflowRunConfig: runtime paths and live-call gates
- run_user_query_to_pending_finalization: executes the graph through
  extraction and returns Phase2State with finalization_pending=True
- run_user_query: full pipeline including critic, visualization, narrator
- continue_user_query: loads pending clarification state, merges answer, reruns

Streamlit, evals, and CLI callers use service.py, not graph.py directly.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.artifacts.workflow_artifacts import WorkflowResponse
from app.workflow.state import Phase2State, new_run_id


class WorkflowRunConfig(BaseModel):
    """Runtime paths and live-call gates for the shared Phase 2 workflow API."""

    goldens_path: Path
    phase1_index_manifest: Path
    phase1_source_catalog_manifest: Path
    artifact_dir: Path
    live_llm_required: bool = True
    live_embeddings_required: bool = True
    case_id: str | None = None

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def default(cls) -> WorkflowRunConfig:
        return cls(
            goldens_path=Path(".planning/phases/01-data-architecture-research/golden-cases.yaml"),
            phase1_index_manifest=Path(
                ".planning/phases/01-data-architecture-research/embedding-index-manifest.json"
            ),
            phase1_source_catalog_manifest=Path(
                ".planning/phases/01-data-architecture-research/source-catalog-manifest.json"
            ),
            artifact_dir=Path(".planning/phases/02-jury-mvp/workflow-runs"),
        )


def run_user_query_to_pending_finalization(
    query: str,
    *,
    run_config: WorkflowRunConfig | None = None,
) -> Phase2State:
    """Execute the Phase 2 graph through extraction and return finalization_pending state.

    This is the primary entrypoint for Streamlit, evals, and CLI prior to plan 02-06.
    Always sets finalization_pending=True — plan 02-06 will add critic/visualization/narrator
    and turn this into a final WorkflowResponse.

    run_config controls live LLM/embeddings gating and artifact paths.
    """
    config = run_config or WorkflowRunConfig.default()

    # Build initial state
    run_id = new_run_id()
    if config.case_id:
        run_id = f"{run_id}-{config.case_id}"

    initial_state: Phase2State = {
        "run_id": run_id,
        "query": query,
        "intent": None,
        "research_design": None,
        "evidence": None,  # type: ignore[typeddict-item]
        "coverage_reports": [],
        "extraction_plan": None,
        "dataset_artifacts": [],
        "script_artifacts": [],
        "final_outcome": None,
        "finalization_pending": False,
        "pending_reason": None,
        "trace_events": [],
        "component_statuses": {},
        # Internal runtime flags (prefixed with _ to signal non-public)
        "_live_llm_required": config.live_llm_required,  # type: ignore[typeddict-unknown-key]
        "_live_embeddings_required": config.live_embeddings_required,  # type: ignore[typeddict-unknown-key]
        "_artifact_dir": str(config.artifact_dir),  # type: ignore[typeddict-unknown-key]
        "_index_manifest_path": str(config.phase1_index_manifest),  # type: ignore[typeddict-unknown-key]
        "_case_id": config.case_id,  # type: ignore[typeddict-unknown-key]
    }

    # Build and invoke the graph
    from app.workflow.graph import build_phase2_graph

    graph = build_phase2_graph()

    try:
        final_state: Phase2State = graph.invoke(initial_state)
    except Exception as exc:
        # On unexpected graph failures, return a minimal finalization_pending state
        return {
            **initial_state,
            "finalization_pending": True,
            "pending_reason": f"graph_error:{exc}",
            "component_statuses": {"graph": f"error:{exc}"},
        }

    # Write state artifact to artifact_dir if requested
    _write_state_artifact(final_state, config=config)

    return final_state


def _write_state_artifact(state: Phase2State, *, config: WorkflowRunConfig) -> None:
    """Persist state JSON to the artifact directory for eval and debug inspection."""
    try:
        run_id = str(state.get("run_id") or "unknown")
        artifact_dir = Path(str(config.artifact_dir)) / run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)

        state_file = artifact_dir / "phase2-state.json"

        # Serialize: handle Pydantic objects
        def _default(obj: Any) -> Any:
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            if hasattr(obj, "__dict__"):
                return obj.__dict__
            return str(obj)

        # Build serializable version, filtering internal _ keys
        serializable = {
            k: v for k, v in state.items()
            if not str(k).startswith("_")
        }

        state_file.write_text(
            json.dumps(serializable, ensure_ascii=False, indent=2, default=_default),
            encoding="utf-8",
        )
    except Exception:
        pass  # State artifact write failures are non-fatal


def run_user_query(
    query: str,
    *,
    run_config: WorkflowRunConfig | None = None,
) -> WorkflowResponse:
    """Single user-query API for Streamlit, evals, and CLI callers.

    Executes the full Phase 2 pipeline:
    1. Graph through extraction (via run_user_query_to_pending_finalization)
    2. Methodology Critic (critic.py)
    3. Visualization (visualization.py)
    4. Narrator (narrator.py)

    Returns complete WorkflowResponse with valid terminal outcome:
    passed | needs_clarification | not_found
    """
    config = run_config or WorkflowRunConfig.default()

    # Step 1: Run graph through extraction
    state = run_user_query_to_pending_finalization(query, run_config=config)

    # Step 2-4: Finalization — critic, visualization, narrator
    response = _finalize_state(state, config=config)

    # Persist the pending clarification state for continue_user_query
    _write_pending_clarification_state(state, response, config=config)

    return response


def _finalize_state(
    state: Phase2State,
    *,
    config: WorkflowRunConfig,
) -> WorkflowResponse:
    """Run critic -> visualization -> narrator on a finalization_pending state."""
    from app.workflow.nodes.critic import derive_final_outcome, run_methodology_critic
    from app.workflow.nodes.visualization import build_visualization
    from app.workflow.nodes.narrator import build_workflow_response

    live_llm = bool(state.get("_live_llm_required", config.live_llm_required))
    dataset_artifacts = list(state.get("dataset_artifacts") or [])
    intent = state.get("intent")

    # Step 2: Methodology Critic
    try:
        critique = run_methodology_critic(state, live_llm_required=live_llm)
    except Exception as exc:
        from app.artifacts.workflow_artifacts import CritiqueReport
        from uuid import uuid4
        critique = CritiqueReport(
            artifact_id=f"critique-{uuid4().hex[:8]}",
            verdict="needs_repair",
            warnings=[f"critic_error:{exc}", "test_only_critic_fallback"],
        )

    # Derive terminal outcome
    final_outcome = derive_final_outcome(state, critique)

    # Step 3: Visualization
    ok_datasets = [d for d in dataset_artifacts if d.status == "ok" and (d.rows or 0) > 0]
    query_category = getattr(intent, "category", "simple") if intent else "simple"

    if ok_datasets and final_outcome == "passed":
        try:
            visualization = build_visualization(ok_datasets[0], query_category=query_category)
        except Exception:
            visualization = None
    else:
        visualization = None

    # Step 4: Narrator
    try:
        response = build_workflow_response(
            state,
            final_outcome=final_outcome,
            critique=critique,
            visualization=visualization,
            live_llm_required=live_llm,
        )
    except Exception as exc:
        # Fallback to a safe not_found response if narrator fails
        from app.artifacts.workflow_artifacts import NoDataExplanationArtifact
        from uuid import uuid4
        response = WorkflowResponse(
            run_id=str(state.get("run_id") or "unknown"),
            final_outcome="not_found",
            message=f"Ошибка при построении ответа: {exc}",
            not_found_evidence=NoDataExplanationArtifact(
                artifact_id=f"not-found-{uuid4().hex[:8]}",
                checked_sources=[],
                rejected_sources=[],
                rejection_reasons=[f"narrator_error:{exc}"],
                search_strategy="error_fallback",
            ),
            component_statuses={"narrator": f"error:{exc}"},
        )

    return response


def _write_pending_clarification_state(
    state: Phase2State,
    response: WorkflowResponse,
    *,
    config: WorkflowRunConfig,
) -> None:
    """Persist pending clarification state for continue_user_query to load."""
    try:
        run_id = str(state.get("run_id") or "unknown")
        artifact_dir = Path(str(config.artifact_dir)) / run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)

        pending_file = artifact_dir / "pending-clarification.json"

        def _default(obj: Any) -> Any:
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            if hasattr(obj, "__dict__"):
                return obj.__dict__
            return str(obj)

        # Save state with internal keys for continue_user_query
        serializable_state = {
            k: v for k, v in state.items()
            if not str(k).startswith("_")
        }

        from app.artifacts.workflow_artifacts import utc_now_iso
        pending_data = {
            "run_id": run_id,
            "state": serializable_state,
            "final_outcome": response.final_outcome,
            "clarification_questions": response.clarification_questions,
            "created_at": utc_now_iso(),
            "config": {
                "artifact_dir": str(config.artifact_dir),
                "live_llm_required": config.live_llm_required,
                "live_embeddings_required": config.live_embeddings_required,
                "goldens_path": str(config.goldens_path),
                "phase1_index_manifest": str(config.phase1_index_manifest),
                "phase1_source_catalog_manifest": str(config.phase1_source_catalog_manifest),
            },
        }
        pending_file.write_text(
            json.dumps(pending_data, ensure_ascii=False, indent=2, default=_default),
            encoding="utf-8",
        )
    except Exception:
        pass  # Non-fatal


def continue_user_query(
    run_id: str,
    clarification_answer: str,
    *,
    run_config: WorkflowRunConfig | None = None,
) -> WorkflowResponse:
    """Load a pending clarification state and rerun with merged answer.

    Loads the pending-clarification.json from the run's artifact directory.
    Merges clarification_answer into IntentFrame known_fields/missing_fields.
    Appends a trace event.
    Reruns from coverage/extraction when possible (without restarting source scouts
    unless the clarification changes source family or indicator).

    Returns a new complete WorkflowResponse (may change from needs_clarification
    to passed or not_found).
    """
    config = run_config or WorkflowRunConfig.default()

    # Find the pending clarification state
    artifact_dir = Path(str(config.artifact_dir)) / run_id
    pending_file = artifact_dir / "pending-clarification.json"

    if not pending_file.exists():
        # If no pending state found, try to run a fresh query using the clarification as query
        return run_user_query(clarification_answer, run_config=config)

    try:
        pending_data = json.loads(pending_file.read_text(encoding="utf-8"))
    except Exception:
        return run_user_query(clarification_answer, run_config=config)

    saved_state = pending_data.get("state") or {}
    previous_outcome = pending_data.get("final_outcome", "needs_clarification")

    # Rebuild Phase2State from saved state
    from app.artifacts.workflow_artifacts import (
        CoverageReport,
        DatasetArtifact,
        EvidenceBundleArtifact,
        ExtractionPlan,
        IntentFrame,
        ResearchDesignArtifact,
        ScriptArtifact,
        TraceEvent,
    )

    def _safe_pydantic(cls: type, data: Any) -> Any:
        """Safely reconstruct a Pydantic model, returning None on failure."""
        if data is None:
            return None
        try:
            if isinstance(data, dict):
                return cls(**data)
            return data
        except Exception:
            return None

    intent_raw = saved_state.get("intent")
    intent = _safe_pydantic(IntentFrame, intent_raw)

    # Merge clarification answer into intent
    if intent is not None:
        merged_known = dict(intent.known_fields or {})
        merged_known["clarification_answer"] = clarification_answer
        # Parse geo/period from clarification_answer
        import re
        years = re.findall(r"\b(19|20)\d{2}\b", clarification_answer)
        if years:
            merged_known["period"] = years[0] if len(years) == 1 else f"{years[0]}-{years[-1]}"
        for geo_kw in ("россия", "russia", "казахстан", "kazakhstan", "китай", "china", "бразилия", "brazil"):
            if geo_kw in clarification_answer.lower():
                merged_known["geography"] = geo_kw
                break

        updated_missing = [f for f in (intent.missing_fields or [])
                           if f not in merged_known]

        intent = IntentFrame(
            query=f"{intent.query} | Уточнение: {clarification_answer}",
            category=intent.category,
            known_fields=merged_known,
            missing_fields=updated_missing,
            needs_clarification=bool(updated_missing),
            source_preferences=list(intent.source_preferences or []),
            open_reasoning=list(intent.open_reasoning or []) + ["clarification_merged"],
        )

    # Reconstruct trace events
    trace_events_raw = saved_state.get("trace_events") or []
    trace_events = []
    for te in trace_events_raw:
        try:
            if isinstance(te, dict):
                trace_events.append(TraceEvent(**te))
        except Exception:
            pass

    # Append clarification trace event
    new_run_id_val = new_run_id()
    trace_events.append(
        TraceEvent(
            run_id=new_run_id_val,
            state="clarification",
            agent="Supervisor",
            input_summary=clarification_answer[:200],
            decision="clarification_merged",
            payload={
                "original_run_id": run_id,
                "clarification_answer": clarification_answer[:200],
                "previous_outcome": previous_outcome,
            },
        )
    )

    # Reconstruct coverage reports
    coverage_reports_raw = saved_state.get("coverage_reports") or []
    coverage_reports = []
    for cr in coverage_reports_raw:
        try:
            if isinstance(cr, dict):
                coverage_reports.append(CoverageReport(**cr))
        except Exception:
            pass

    # Reconstruct dataset artifacts
    dataset_artifacts_raw = saved_state.get("dataset_artifacts") or []
    dataset_artifacts = []
    for da in dataset_artifacts_raw:
        try:
            if isinstance(da, dict):
                dataset_artifacts.append(DatasetArtifact(**da))
        except Exception:
            pass

    # Reconstruct script artifacts
    script_artifacts_raw = saved_state.get("script_artifacts") or []
    script_artifacts = []
    for sa in script_artifacts_raw:
        try:
            if isinstance(sa, dict):
                script_artifacts.append(ScriptArtifact(**sa))
        except Exception:
            pass

    # Reconstruct evidence bundle
    evidence_raw = saved_state.get("evidence")
    evidence = _safe_pydantic(EvidenceBundleArtifact, evidence_raw) or EvidenceBundleArtifact()

    # Build merged state for re-finalization
    merged_state: Phase2State = {
        "run_id": new_run_id_val,
        "query": saved_state.get("query", clarification_answer),
        "intent": intent,
        "research_design": None,
        "evidence": evidence,
        "coverage_reports": coverage_reports,
        "extraction_plan": None,
        "dataset_artifacts": dataset_artifacts,
        "script_artifacts": script_artifacts,
        "final_outcome": None,
        "finalization_pending": True,
        "pending_reason": "clarification_merged",
        "trace_events": trace_events,
        "component_statuses": dict(saved_state.get("component_statuses") or {}),
        "_live_llm_required": config.live_llm_required,  # type: ignore[typeddict-unknown-key]
        "_live_embeddings_required": config.live_embeddings_required,  # type: ignore[typeddict-unknown-key]
        "_artifact_dir": str(config.artifact_dir),  # type: ignore[typeddict-unknown-key]
        "_index_manifest_path": str(config.phase1_index_manifest),  # type: ignore[typeddict-unknown-key]
        "_case_id": None,  # type: ignore[typeddict-unknown-key]
    }

    # Check if we can re-finalize with existing data
    has_ok_datasets = any(
        getattr(d, "status", None) == "ok" and (getattr(d, "rows", 0) or 0) > 0
        for d in dataset_artifacts
    )

    if has_ok_datasets and coverage_reports:
        # Re-finalize with merged intent without rerunning extraction
        response = _finalize_state(merged_state, config=config)
    else:
        # Need to re-run from scratch with merged intent
        response = run_user_query(
            f"{saved_state.get('query', '')} | Уточнение: {clarification_answer}",
            run_config=config,
        )

    # Persist updated state
    _write_pending_clarification_state(merged_state, response, config=config)

    return response
