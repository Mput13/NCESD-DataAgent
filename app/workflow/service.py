"""Phase 2 workflow service API.

Provides:
- WorkflowRunConfig: runtime paths and live-call gates
- run_user_query_to_pending_finalization: executes the graph through
  extraction and returns Phase2State with finalization_pending=True
- run_user_query: raises NotImplementedError until plan 02-06 wires
  critic, visualization, and narrator

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

    NOT IMPLEMENTED until plan 02-06 wires critic, visualization, and narrator.
    Use run_user_query_to_pending_finalization() for pre-finalization execution.
    """
    _ = query
    _ = run_config or WorkflowRunConfig.default()
    raise NotImplementedError(
        "Phase 2 final WorkflowResponse implementation is provided by plan 02-06"
    )
