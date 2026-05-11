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

from app.artifacts.workflow_artifacts import (
    FeedbackArtifact,
    NoDataExplanationArtifact,
    TraceEvent,
    WorkflowResponse,
    utc_now_iso,
)
from app.workflow.state import Phase2State, new_run_id


class WorkflowRunConfig(BaseModel):
    """Runtime paths and live-call gates for the shared Phase 2 workflow API."""

    goldens_path: Path = Path()
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
    from app.workflow.nodes.critic import build_final_decision, run_methodology_critic
    from app.workflow.nodes.visualization import build_visualization_for_all_datasets
    from app.workflow.nodes.narrator import build_workflow_response
    from uuid import uuid4

    live_llm = bool(state.get("_live_llm_required", config.live_llm_required))
    dataset_artifacts = list(state.get("dataset_artifacts") or [])
    intent = state.get("intent")

    if not live_llm:
        trace_events = list(state.get("trace_events") or [])
        trace_events.append(
            TraceEvent(
                run_id=str(state.get("run_id") or "unknown"),
                state="finalization",
                agent="WorkflowService",
                decision="gated_live_llm_required",
                warnings=["live_llm_required=False is not a product execution mode"],
            )
        )
        component_statuses = dict(state.get("component_statuses") or {})
        component_statuses["service"] = "gated_live_llm_required"
        return WorkflowResponse(
            run_id=str(state.get("run_id") or "unknown"),
            final_outcome="needs_clarification",
            message="Live LLM execution is required for the workflow service.",
            clarification_questions=[
                "Система временно недоступна. Повторите запрос позднее."
            ],
            trace_events=trace_events,
            component_statuses=component_statuses,
        )

    # Step 2: Methodology Critic
    try:
        critique = run_methodology_critic(state, live_llm_required=live_llm)
    except Exception as exc:
        from app.artifacts.workflow_artifacts import CritiqueReport
        critique = CritiqueReport(
            artifact_id=f"critique-{uuid4().hex[:8]}",
            verdict="needs_repair",
            warnings=[f"critic_error:{exc}"],
        )

    # Derive terminal outcome. Intent-level ambiguity must stay a
    # clarification request even when retrieval/extraction have no data.
    if intent is not None and getattr(intent, "needs_clarification", False):
        final_outcome = "needs_clarification"
        decision = None
    else:
        decision = build_final_decision(state, critique)
        final_outcome = decision.terminal_outcome

    # Step 3: Visualization — process ALL selected datasets, errors must not change decision
    ok_datasets = [d for d in dataset_artifacts if d.status == "ok" and (d.rows or 0) > 0]
    query_category = getattr(intent, "category", "simple") if intent else "simple"

    visualization = None
    if ok_datasets and final_outcome == "passed":
        try:
            vis_specs = build_visualization_for_all_datasets(ok_datasets, query_category=query_category)
            # Use the first ok spec for the response; all are recorded in component_statuses
            ok_specs = [v for v in vis_specs if v.status == "ok"]
            visualization = ok_specs[0] if ok_specs else vis_specs[0] if vis_specs else None
        except Exception as vis_exc:
            # Visualization failure must NEVER change the final decision
            state.setdefault("component_statuses", {})["visualization"] = f"error:{vis_exc}"  # type: ignore[index]

    # Step 4: Narrator — failures are output-stage errors, not data absence
    try:
        response = build_workflow_response(
            state,
            final_outcome=final_outcome,
            critique=critique,
            visualization=visualization,
            live_llm_required=live_llm,
        )
    except Exception as exc:
        # Narrator failure: this is an output-stage system error.
        # Do NOT silently convert to not_found without annotation — surface it explicitly.
        from uuid import uuid4
        response = WorkflowResponse(
            run_id=str(state.get("run_id") or "unknown"),
            final_outcome="not_found",
            message=(
                f"Данные получены, но при формировании ответа произошла ошибка: {exc}. "
                "Это системная ошибка, а не отсутствие данных. Повторите запрос."
            ),
            not_found_evidence=NoDataExplanationArtifact(
                artifact_id=f"system-error-{uuid4().hex[:8]}",
                checked_sources=[],
                rejected_sources=[],
                rejection_reasons=[f"narrator_output_failure:{exc}"],
                search_strategy="error_fallback",
            ),
            component_statuses={
                "narrator": f"system_error:{exc}",
                "final_outcome_intended": final_outcome,
            },
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
            "original_query_text": str(state.get("query") or ""),
            "clarification_turns": [],
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


def _clarification_state_error_response(
    *,
    run_id: str,
    reason: str,
    detail: str,
    clarification_answer: str,
    previous_outcome: str | None = None,
) -> WorkflowResponse:
    """Return an explicit public response for an invalid clarification resume."""
    status = f"clarification_state_{reason}"
    trace = TraceEvent(
        run_id=run_id,
        state="clarification",
        agent="Clarification Manager",
        input_summary=clarification_answer[:200],
        decision=status,
        warnings=[detail],
        payload={
            "run_id": run_id,
            "clarification_answer": clarification_answer[:200],
            "previous_outcome": previous_outcome,
        },
    )
    evidence = NoDataExplanationArtifact(
        artifact_id=f"not-found-{status}",
        checked_sources=[{"run_id": run_id, "artifact": "pending-clarification.json"}],
        rejected_sources=[{"run_id": run_id, "reason": status}],
        rejection_reasons=[detail],
        search_strategy=status,
        limitations=["Clarification continuation cannot be resumed without a valid pending state."],
    )
    return WorkflowResponse(
        run_id=run_id,
        final_outcome="needs_clarification",
        message="Не удалось продолжить уточнение из сохраненного состояния workflow.",
        clarification_questions=["Повторите исходный запрос, чтобы начать новый запуск."],
        trace_events=[trace],
        not_found_evidence=evidence,
        component_statuses={"clarification": status},
    )


def continue_user_query(
    run_id: str,
    clarification_answer: str,
    *,
    run_config: WorkflowRunConfig | None = None,
) -> WorkflowResponse:
    """Load a pending clarification state and continue with the user's answer.

    Missing or corrupt pending state is fail-closed: this function never turns a
    clarification answer into a fresh standalone query.
    """
    config = run_config or WorkflowRunConfig.default()

    # Find the pending clarification state
    artifact_dir = Path(str(config.artifact_dir)) / run_id
    pending_file = artifact_dir / "pending-clarification.json"

    if not pending_file.exists():
        return _clarification_state_error_response(
            run_id=run_id,
            reason="missing",
            detail=f"pending clarification file is missing: {pending_file}",
            clarification_answer=clarification_answer,
        )

    try:
        pending_data = json.loads(pending_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return _clarification_state_error_response(
            run_id=run_id,
            reason="corrupt",
            detail=f"pending clarification file is corrupt: {exc}",
            clarification_answer=clarification_answer,
        )

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

    original_query = str(
        pending_data.get("original_query_text")
        or saved_state.get("query")
        or ""
    )

    # Merge clarification answer into intent via LLM re-analysis
    # Per ARCHITECTURE_STACK.md: clarification parsing must go through Intent Analyst,
    # not keyword matching. Preserve original query and answer as separate fields.
    from app.workflow.state import analyze_intent as _analyze_intent
    reanalysis_prompt = (
        f"Исходный запрос: {original_query}\n"
        f"Уточнение пользователя: {clarification_answer}"
    )
    try:
        analyzed_intent = _analyze_intent(
            reanalysis_prompt,
            live_llm_required=config.live_llm_required,
        )
        intent = IntentFrame(
            query=original_query,
            category=analyzed_intent.category,
            known_fields=dict(analyzed_intent.known_fields or {}),
            missing_fields=list(analyzed_intent.missing_fields or []),
            needs_clarification=analyzed_intent.needs_clarification,
            source_preferences=list(analyzed_intent.source_preferences or []),
            open_reasoning=list(analyzed_intent.open_reasoning or []) + [
                "clarification_reanalyzed_by_llm"
            ],
        )
    except Exception as exc:
        return _clarification_state_error_response(
            run_id=run_id,
            reason="reanalysis_gated",
            detail=f"clarification LLM re-analysis failed: {exc}",
            clarification_answer=clarification_answer,
            previous_outcome=str(previous_outcome),
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
            agent="Clarification Manager",
            input_summary=clarification_answer[:200],
            decision="clarification_merged",
            payload={
                "original_run_id": run_id,
                "original_query_text": original_query,
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
        "query": original_query,
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
        trace_events.append(
            TraceEvent(
                run_id=new_run_id_val,
                state="clarification",
                agent="Clarification Manager",
                decision="clarification_resume_unavailable",
                warnings=["No reusable dataset/coverage state exists for continuation."],
                payload={
                    "original_run_id": run_id,
                    "original_query_text": original_query,
                    "clarification_answer": clarification_answer[:200],
                },
            )
        )
        response = WorkflowResponse(
            run_id=new_run_id_val,
            final_outcome="needs_clarification",
            message="Уточнение сохранено, но продолжить этот запуск без валидного промежуточного состояния нельзя.",
            clarification_questions=["Повторите исходный запрос, чтобы начать новый запуск."],
            trace_events=trace_events,
            component_statuses={
                **dict(merged_state.get("component_statuses") or {}),
                "clarification": "clarification_resume_unavailable",
            },
        )

    # Persist updated state
    _write_pending_clarification_state(merged_state, response, config=config)
    try:
        updated_pending_file = Path(str(config.artifact_dir)) / new_run_id_val / "pending-clarification.json"
        updated_pending = json.loads(updated_pending_file.read_text(encoding="utf-8"))
        prior_turns = list(pending_data.get("clarification_turns") or [])
        prior_turns.append(
            {
                "original_run_id": run_id,
                "continued_run_id": new_run_id_val,
                "original_query_text": original_query,
                "clarification_answer": clarification_answer,
                "previous_outcome": previous_outcome,
                "created_at": utc_now_iso(),
            }
        )
        updated_pending["clarification_turns"] = prior_turns
        updated_pending_file.write_text(
            json.dumps(updated_pending, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass

    return response



EXECUTABLE_FEEDBACK_ACTIONS = {
    "revise_source_or_period",
    "revise_source",
    "revise_period",
    "explain_simpler",
}


def apply_feedback(
    run_id: str,
    *,
    rating: str | None = None,
    user_comment: str,
    requested_action: str | None = None,
    target_state: str | None = None,
    run_config: WorkflowRunConfig | None = None,
) -> WorkflowResponse | FeedbackArtifact:
    """Persist user feedback and execute supported repair actions.

    Streamlit calls this for both lightweight ratings and fix requests. Supported
    actions rerun through the clarification path so the repair is linked to the
    original run. Unsupported actions create a fix-request artifact for later
    inspection instead of pretending the UI button fixed anything.
    """
    config = run_config or WorkflowRunConfig.default()
    artifact_dir = Path(str(config.artifact_dir)) / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    requested_action = (requested_action or "").strip() or None
    normalized_rating = rating if rating in {"positive", "negative", "neutral", "not_set"} else "not_set"
    status = "rerun" if requested_action in EXECUTABLE_FEEDBACK_ACTIONS else "recorded"
    if requested_action and requested_action not in EXECUTABLE_FEEDBACK_ACTIONS:
        status = "fix_requested"

    feedback = FeedbackArtifact(
        run_id=run_id,
        artifact_id=f"feedback-{utc_now_iso().replace(':', '').replace('-', '')}",
        rating=normalized_rating,  # type: ignore[arg-type]
        user_comment=user_comment,
        requested_action=requested_action,
        target_state=target_state,
        status=status,  # type: ignore[arg-type]
        fix_request_reason=None if status != "fix_requested" else "requested_action_not_executable",
    )
    feedback_path = artifact_dir / f"{feedback.artifact_id}.json"
    feedback.path = str(feedback_path)
    feedback_path.write_text(
        json.dumps(feedback.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    trace_path = artifact_dir / "feedback-trace.jsonl"
    trace_event = TraceEvent(
        run_id=run_id,
        state=target_state or "feedback",
        agent="UserFeedback",
        input_summary=user_comment[:200],
        output_artifact=feedback.artifact_id,
        decision=status,
        payload=feedback.model_dump(),
    )
    with trace_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(trace_event.model_dump(), ensure_ascii=False) + "\n")

    if requested_action in EXECUTABLE_FEEDBACK_ACTIONS:
        repair_prompt = _feedback_repair_prompt(
            requested_action=requested_action,
            user_comment=user_comment,
            target_state=target_state,
        )
        response = continue_user_query(run_id, repair_prompt, run_config=config)
        response.trace_events.append(trace_event)
        response.component_statuses["feedback"] = "rerun"
        return response

    return feedback


def _feedback_repair_prompt(
    *,
    requested_action: str,
    user_comment: str,
    target_state: str | None,
) -> str:
    target = f" target_state={target_state}." if target_state else ""
    return f"Feedback action {requested_action}.{target} User comment: {user_comment}"
