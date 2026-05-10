from __future__ import annotations

from pathlib import Path
from typing import Any

from app.demo.run_demo import DemoInputs, assess_demo_readiness
from app.ui.trace_models import FeedbackRequest, FixRequest, WorkflowTraceViewModel


PHASE_DIR = Path(".planning/phases/01-data-architecture-research")
EXAMPLE_PROMPTS = [
    "Какой ВВП России в 2024 году?",
    "Покажи ВВП России по ППС по Росстату.",
    "Сравни динамику ВВП стран БРИКС за 2015-2024 годы.",
    "Дай данные по инфляции.",
    "Найди показатель ЕМИСС 57319 и покажи доступные ресурсы.",
    "Проверь, готов ли dense retrieval искать источники по карточкам FedStat, World Bank и CKAN.",
]


def default_demo_inputs(phase_dir: Path = PHASE_DIR) -> DemoInputs:
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
    except ModuleNotFoundError as exc:  # pragma: no cover - local import smoke can run without streamlit
        raise RuntimeError("streamlit is required to run app.ui.streamlit_app") from exc

    readiness = assess_demo_readiness(default_demo_inputs())
    view_model = WorkflowTraceViewModel.model_validate(readiness["trace_view_model"])

    st.set_page_config(page_title="DataAgent diagnostic trace", layout="wide")
    st.title("DataAgent diagnostic trace")

    prompt = st.chat_input("Введите экономический запрос")
    selected_example = st.selectbox("example prompts", EXAMPLE_PROMPTS, index=0)
    active_query = prompt or selected_example

    status_col, index_col, feedback_col = st.columns([1.1, 1.1, 1.0])
    with status_col:
        st.subheader("state machine")
        st.metric("overall", readiness["overall_status"])
        st.metric("retrieval", readiness["retrieval_eval_status"])
        st.metric("extraction", readiness["extraction_eval_status"])
        st.caption(f"active query: {active_query}")
    with index_col:
        st.subheader("index readiness")
        st.metric("Qdrant", readiness["qdrant_status"])
        st.metric("dense retrieval", "ready" if readiness["dense_retrieval_ready"] else "gated")
        st.json(readiness["prepared"], expanded=False)
    with feedback_col:
        st.subheader("feedback")
        rating = st.radio("diagnostic rating", ["not_set", "positive", "neutral", "negative"], horizontal=True)
        comment = st.text_area("fix request", placeholder="Уточнить источник, период, покрытие или объяснение")
        feedback = FeedbackRequest(
            run_id=view_model.run_id,
            artifact_id="demo-readiness.json",
            rating=rating,  # type: ignore[arg-type]
            comment=comment or None,
        )
        fix_request = FixRequest(
            run_id=view_model.run_id,
            target_state="prepared_index_check",
            requested_change=comment or None,
        )
        st.json(
            {"FeedbackRequest": feedback.model_dump(), "FixRequest": fix_request.model_dump()},
            expanded=False,
        )

    trace_col, artifact_col = st.columns([1.2, 1.0])
    with trace_col:
        st.subheader("live trace")
        _render_trace(st, view_model)
    with artifact_col:
        st.subheader("artifacts")
        st.json(readiness["artifacts"], expanded=False)
        st.subheader("answer area")
        st.info(
            "Numeric narration is withheld until deterministic extraction evidence is ready. "
            "This diagnostic surface exposes source and gate evidence first."
        )
        st.subheader("rejected")
        st.json(view_model.rejected_sources, expanded=False)
        st.subheader("sources")
        st.json(view_model.selected_sources, expanded=False)


def _render_trace(st: Any, view_model: WorkflowTraceViewModel) -> None:
    for event in view_model.trace_events:
        with st.expander(f"{event.state} - {event.agent}", expanded=True):
            st.write(event.decision)
            st.json(
                {
                    "tool_calls": event.tool_calls,
                    "artifact": event.output_artifact,
                    "warnings": event.warnings,
                    "payload": event.payload,
                },
                expanded=False,
            )


if __name__ == "__main__":
    run_app()

