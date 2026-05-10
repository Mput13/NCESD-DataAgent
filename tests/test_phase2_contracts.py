from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_phase2_runtime_imports_declared_dependencies() -> None:
    import duckdb
    import langgraph
    import pyarrow
    import pydantic
    import qdrant_client
    import streamlit

    assert duckdb
    assert langgraph
    assert pyarrow
    assert pydantic
    assert qdrant_client
    assert streamlit


def _workflow_response_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "phase2-test-run",
        "final_outcome": "passed",
        "message": "Ответ построен по проверенным источникам.",
        "answer_blocks": [{"type": "text", "text": "Ответ"}],
        "citations": [{"source_id": "world_bank:NY.GDP.MKTP.CD"}],
        "selected_sources": [{"source_id": "world_bank:NY.GDP.MKTP.CD"}],
        "rejected_sources": [],
        "coverage": [],
        "extraction_plan": None,
        "dataset_artifacts": [
            {
                "artifact_id": "dataset-1",
                "status": "ok",
                "source_id": "world_bank:NY.GDP.MKTP.CD",
                "rows": 1,
            }
        ],
        "script_artifacts": [
            {
                "artifact_id": "script-1",
                "language": "python",
                "script_path": ".planning/phases/02-jury-mvp/workflow-runs/script.py",
                "entrypoint": "python script.py",
                "source_ids": ["world_bank:NY.GDP.MKTP.CD"],
            }
        ],
        "visualization": None,
        "trace_events": [],
        "limitations": [],
        "clarification_questions": [],
        "not_found_evidence": None,
        "feedback_actions": [],
        "component_statuses": {"retrieval": "ok", "extraction": "ok"},
    }
    payload.update(overrides)
    return payload


def test_workflow_response_rejects_internal_final_outcomes() -> None:
    from app.artifacts.workflow_artifacts import WorkflowResponse

    with pytest.raises(ValidationError):
        WorkflowResponse(**_workflow_response_payload(final_outcome="gated"))


def test_passed_workflow_response_requires_dataset_and_script_artifacts() -> None:
    from app.artifacts.workflow_artifacts import WorkflowResponse

    with pytest.raises(ValidationError):
        WorkflowResponse(
            **_workflow_response_payload(
                final_outcome="passed",
                dataset_artifacts=[],
                script_artifacts=[],
            )
        )


def test_needs_clarification_workflow_response_requires_questions() -> None:
    from app.artifacts.workflow_artifacts import WorkflowResponse

    response = WorkflowResponse(
        **_workflow_response_payload(
            final_outcome="needs_clarification",
            dataset_artifacts=[],
            script_artifacts=[],
            clarification_questions=["Уточните период и страну."],
            component_statuses={"intent": "needs_clarification"},
        )
    )

    assert response.final_outcome == "needs_clarification"
    assert response.clarification_questions == ["Уточните период и страну."]


def test_not_found_workflow_response_requires_no_data_evidence() -> None:
    from app.artifacts.workflow_artifacts import NoDataExplanationArtifact, WorkflowResponse

    evidence = NoDataExplanationArtifact(
        artifact_id="not-found-1",
        checked_sources=[{"source_id": "fedstat:missing"}],
        rejection_reasons=["No trusted source covers the requested indicator."],
        search_strategy="fedstat/world_bank/ckan",
    )
    response = WorkflowResponse(
        **_workflow_response_payload(
            final_outcome="not_found",
            dataset_artifacts=[],
            script_artifacts=[],
            not_found_evidence=evidence,
            component_statuses={"retrieval": "not_found"},
        )
    )

    assert response.final_outcome == "not_found"
    assert response.not_found_evidence == evidence


def test_workflow_run_config_default_points_to_phase2_artifacts() -> None:
    from pathlib import Path
    from app.workflow.service import WorkflowRunConfig

    config = WorkflowRunConfig.default()

    # Use Path comparison to be OS-agnostic (handles both / and \ separators)
    assert config.goldens_path == Path(".planning/phases/01-data-architecture-research/golden-cases.yaml")
    assert config.phase1_index_manifest == Path(
        ".planning/phases/01-data-architecture-research/embedding-index-manifest.json"
    )
    assert config.phase1_source_catalog_manifest == Path(
        ".planning/phases/01-data-architecture-research/source-catalog-manifest.json"
    )
    assert config.artifact_dir == Path(".planning/phases/02-jury-mvp/workflow-runs")


def test_run_user_query_now_implemented_by_plan_02_06(tmp_path) -> None:
    """After plan 02-06, run_user_query returns WorkflowResponse (plan 02-06 implemented it)."""
    from app.workflow.service import WorkflowRunConfig, run_user_query
    from app.artifacts.workflow_artifacts import WorkflowResponse

    config = WorkflowRunConfig.default().model_copy(
        update={
            "artifact_dir": tmp_path / "artifacts",
            "live_llm_required": False,
            "live_embeddings_required": False,
        }
    )
    response = run_user_query("Какая динамика ВВП России?", run_config=config)
    assert isinstance(response, WorkflowResponse)
    assert response.final_outcome in ("passed", "needs_clarification", "not_found")
