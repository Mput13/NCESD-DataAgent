from __future__ import annotations

from pathlib import Path
from typing import Any

from app.artifacts.workflow_artifacts import (
    DatasetArtifact,
    ScriptArtifact,
    WorkflowResponse,
)
from app.demo.run_demo import DemoInputs, assess_demo_readiness
from app.ui.trace_models import WorkflowTraceViewModel
from app.workflow.service import (
    WorkflowRunConfig,
    apply_feedback,
    continue_user_query,
    run_user_query,
)


PHASE1_DIR = Path(".planning/phases/01-data-architecture-research")
EXAMPLE_PROMPTS = [
    "Какой ВВП России в 2024 году?",
    "Сравни динамику ВВП стран БРИКС за 2015-2024 годы.",
    "Дай данные по инфляции.",
    "Найди официальную инфляцию в Северной Корее за 2024 год.",
    "Найди показатель ЕМИСС 57319 и покажи доступные ресурсы.",
]


def default_demo_inputs(phase_dir: Path = PHASE1_DIR) -> DemoInputs:
    return DemoInputs(
        source_cards_manifest=phase_dir / "source-cards-manifest.json",
        source_catalog_manifest=phase_dir / "source-catalog-manifest.json",
        embedding_corpus_manifest=phase_dir / "embedding-corpus-manifest.json",
        index_manifest=phase_dir / "embedding-index-manifest.json",
        retrieval_eval=phase_dir / "retrieval-eval.csv",
        extraction_probes=phase_dir / "extraction-probes.json",
        data_relevance_eval=phase_dir / "data-relevance-eval.json",
    )


def load_view_model() -> WorkflowTraceViewModel:
    readiness = assess_demo_readiness(default_demo_inputs())
    return WorkflowTraceViewModel.model_validate(readiness["trace_view_model"])


def run_app() -> None:
    try:
        import streamlit as st
    except ModuleNotFoundError as exc:  # pragma: no cover - import smoke can run without streamlit
        raise RuntimeError("streamlit is required to run app.ui.streamlit_app") from exc

    st.set_page_config(page_title="DataAgent jury workflow", layout="wide")
    _ensure_session_state(st)

    st.title("DataAgent")
    _render_sidebar(st)

    for message in st.session_state["messages"]:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    selected_example = st.selectbox("Example prompt", EXAMPLE_PROMPTS, index=0)
    if st.button("Run example", use_container_width=False):
        _submit_prompt(st, selected_example)

    prompt = st.chat_input("Введите экономический запрос")
    if prompt:
        _submit_prompt(st, prompt)

    latest_response = st.session_state.get("latest_response")
    if latest_response is not None:
        _render_workflow_response(st, latest_response)
        _render_feedback_controls(st, latest_response)


def _ensure_session_state(st: Any) -> None:
    defaults = {
        "messages": [],
        "latest_response": None,
        "latest_run_id": None,
        "pending_clarification": None,
        "feedback": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _submit_prompt(st: Any, prompt: str) -> None:
    run_config = WorkflowRunConfig.default()
    st.session_state["messages"].append({"role": "user", "content": prompt})

    if st.session_state.get("pending_clarification") and st.session_state.get("latest_run_id"):
        response = continue_user_query(
            st.session_state["latest_run_id"],
            prompt,
            run_config=run_config,
        )
    else:
        response = run_user_query(prompt, run_config=run_config)

    st.session_state["latest_response"] = response
    st.session_state["latest_run_id"] = response.run_id
    if response.final_outcome == "needs_clarification":
        st.session_state["pending_clarification"] = response.clarification_questions
    else:
        st.session_state["pending_clarification"] = None
    st.session_state["messages"].append({"role": "assistant", "content": response.message})


def _render_sidebar(st: Any) -> None:
    with st.sidebar:
        st.subheader("Readiness")
        try:
            readiness = assess_demo_readiness(default_demo_inputs())
        except Exception as exc:
            st.warning(f"Readiness unavailable: {exc}")
            return
        st.metric("overall", readiness.get("overall_status", "unknown"))
        st.metric("Qdrant", readiness.get("qdrant_status", "unknown"))
        st.metric("retrieval", readiness.get("retrieval_eval_status", "unknown"))
        st.metric("extraction", readiness.get("extraction_eval_status", "unknown"))


def _render_workflow_response(st: Any, response: WorkflowResponse) -> None:
    st.subheader("Answer")
    st.caption(f"run_id: {response.run_id} | outcome: {response.final_outcome}")
    st.write(response.message)

    _render_answer_blocks(st, response)
    _render_citations(st, response)
    _render_sources(st, response)
    _render_coverage(st, response)
    _render_extraction_plan(st, response)
    _render_dataset_artifacts(st, response.dataset_artifacts)
    _render_script_artifacts(st, response.script_artifacts)
    _render_visualization(st, response)
    _render_limitations(st, response)
    _render_clarification_questions(st, response)
    _render_not_found_evidence(st, response)
    _render_trace_events(st, response)
    _render_feedback_actions(st, response)


def _render_answer_blocks(st: Any, response: WorkflowResponse) -> None:
    with st.expander("Answer blocks", expanded=True):
        for block in response.answer_blocks:
            st.json(block, expanded=False)


def _render_citations(st: Any, response: WorkflowResponse) -> None:
    with st.expander("Citations", expanded=False):
        st.json(response.citations, expanded=False)


def _render_sources(st: Any, response: WorkflowResponse) -> None:
    selected, rejected = st.columns(2)
    with selected:
        st.subheader("Selected sources")
        st.json(response.selected_sources, expanded=False)
    with rejected:
        st.subheader("Rejected sources")
        st.json(response.rejected_sources, expanded=False)


def _render_coverage(st: Any, response: WorkflowResponse) -> None:
    with st.expander("Coverage", expanded=False):
        st.json([item.model_dump() for item in response.coverage], expanded=False)


def _render_extraction_plan(st: Any, response: WorkflowResponse) -> None:
    with st.expander("Extraction plan", expanded=False):
        if response.extraction_plan is None:
            st.write("No extraction plan.")
        else:
            st.json(response.extraction_plan.model_dump(), expanded=False)


def _render_dataset_artifacts(st: Any, artifacts: list[DatasetArtifact]) -> None:
    with st.expander("Dataset artifacts", expanded=True):
        for artifact in artifacts:
            st.json(artifact.model_dump(), expanded=False)
            _download_path(st, artifact.csv_path, f"Download CSV {artifact.artifact_id}", "text/csv")
            _download_path(
                st,
                artifact.parquet_path,
                f"Download Parquet {artifact.artifact_id}",
                "application/octet-stream",
            )


def _render_script_artifacts(st: Any, artifacts: list[ScriptArtifact]) -> None:
    with st.expander("Script artifacts", expanded=True):
        for artifact in artifacts:
            st.json(artifact.model_dump(), expanded=False)
            script_path = artifact.path or artifact.script_path
            _download_path(
                st,
                script_path,
                f"Download script {artifact.download_filename or artifact.artifact_id}",
                artifact.mime_type,
            )


def _download_path(st: Any, raw_path: str | None, label: str, mime_type: str) -> None:
    if not raw_path:
        return
    path = Path(raw_path)
    if not path.exists():
        return
    st.download_button(
        label,
        data=path.read_bytes(),
        file_name=path.name,
        mime=mime_type,
        key=f"download-{label}-{path}",
    )


def _render_visualization(st: Any, response: WorkflowResponse) -> None:
    with st.expander("Visualization", expanded=False):
        if response.visualization is None:
            st.write("No visualization.")
        else:
            st.json(response.visualization.model_dump(), expanded=False)


def _render_limitations(st: Any, response: WorkflowResponse) -> None:
    with st.expander("Limitations", expanded=False):
        st.json(response.limitations, expanded=False)


def _render_clarification_questions(st: Any, response: WorkflowResponse) -> None:
    if response.final_outcome != "needs_clarification":
        return
    st.warning("Clarification needed")
    for question in response.clarification_questions:
        st.write(question)


def _render_not_found_evidence(st: Any, response: WorkflowResponse) -> None:
    if response.not_found_evidence is None:
        return
    with st.expander("Not found evidence", expanded=True):
        st.json(response.not_found_evidence.model_dump(), expanded=False)


def _render_trace_events(st: Any, response: WorkflowResponse) -> None:
    with st.expander("Trace", expanded=True):
        for event in response.trace_events:
            st.json(event.model_dump(), expanded=False)


def _render_feedback_actions(st: Any, response: WorkflowResponse) -> None:
    with st.expander("Feedback actions", expanded=False):
        st.json([action.model_dump() for action in response.feedback_actions], expanded=False)


def _render_feedback_controls(st: Any, response: WorkflowResponse) -> None:
    st.subheader("Feedback")
    rating = st.radio(
        "Rating",
        ["not_set", "positive", "neutral", "negative"],
        horizontal=True,
        key=f"rating-{response.run_id}",
    )
    comment = st.text_area(
        "Comment or fix request",
        key=f"comment-{response.run_id}",
    )
    action = st.selectbox(
        "Requested action",
        [
            "",
            "revise_source_or_period",
            "revise_source",
            "revise_period",
            "explain_simpler",
            "manual_fix_request",
        ],
        key=f"action-{response.run_id}",
    )
    target_state = st.selectbox(
        "Target state",
        ["", "source_scouts", "coverage_schema", "extraction_planner", "narrator"],
        key=f"target-{response.run_id}",
    )
    if st.button("Submit feedback", key=f"submit-feedback-{response.run_id}"):
        result = apply_feedback(
            response.run_id,
            rating=rating,
            user_comment=comment,
            requested_action=action or None,
            target_state=target_state or None,
            run_config=WorkflowRunConfig.default(),
        )
        st.session_state["feedback"] = result
        if isinstance(result, WorkflowResponse):
            st.session_state["latest_response"] = result
            st.session_state["latest_run_id"] = result.run_id
            st.success("Feedback applied and workflow reran.")
        else:
            st.success("Feedback artifact recorded.")


if __name__ == "__main__":
    run_app()
