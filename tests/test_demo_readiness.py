from __future__ import annotations

from pathlib import Path


def test_demo_readiness_reports_gates_without_dense_success() -> None:
    from app.demo.run_demo import DemoInputs, assess_demo_readiness

    phase_dir = Path(".planning/phases/01-data-architecture-research")
    result = assess_demo_readiness(
        DemoInputs(
            source_cards_manifest=phase_dir / "source-cards-manifest.json",
            source_catalog_manifest=phase_dir / "source-catalog-manifest.json",
            embedding_corpus_manifest=phase_dir / "embedding-corpus-manifest.json",
            index_manifest=phase_dir / "embedding-index-manifest.json",
            retrieval_eval=phase_dir / "retrieval-eval.csv",
            extraction_probes=phase_dir / "extraction-probes.json",
            data_relevance_eval=phase_dir / "data-relevance-eval.json",
        )
    )

    assert result["source_cards_status"] == "ready"
    assert result["qdrant_status"] in {"ready", "gated_skip"}
    assert result["retrieval_eval_status"] in {"ready", "gated"}
    assert result["extraction_eval_status"] in {"ready", "gated"}
    if result["dense_retrieval_ready"]:
        assert result["qdrant_status"] == "ready"
    assert result["trace_view_model"]["trace_events"]


def test_streamlit_app_imports_without_streamlit_runtime() -> None:
    import app.ui.streamlit_app as streamlit_app

    view_model = streamlit_app.load_view_model()

    assert view_model.diagnostic is True
    assert view_model.index_status.state in {"ready", "gated_skip"}
