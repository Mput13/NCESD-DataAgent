from __future__ import annotations

import json
from pathlib import Path


def test_workflow_artifacts_cover_graph_and_ui_contracts() -> None:
    from app.artifacts.workflow_artifacts import (
        CoverageReport,
        CritiqueReport,
        DatasetArtifact,
        ExtractionPlan,
        FeedbackArtifact,
        FinalAnswer,
        IntentFrame,
        MethodologyNote,
        ResearchDesignArtifact,
        SourceRejectionRecord,
        TraceEvent,
        VisualizationSpec,
    )

    intent = IntentFrame(
        query="Дай данные по инфляции.",
        category="ambiguous",
        known_fields={},
        missing_fields=["geography", "period"],
        needs_clarification=True,
    )
    coverage = CoverageReport(
        source_id="world_bank:FP.CPI.TOTL.ZG",
        status="gated",
        checks=["period", "geography"],
        evidence={"reason": "representative"},
    )
    trace = TraceEvent(
        run_id="run-test",
        state="triage",
        agent="Supervisor",
        output_artifact="intent",
        decision="clarify",
    )

    assert intent.needs_clarification is True
    assert coverage.status == "gated"
    assert trace.agent == "Supervisor"
    assert ResearchDesignArtifact
    assert ExtractionPlan
    assert DatasetArtifact
    assert MethodologyNote
    assert VisualizationSpec
    assert CritiqueReport
    assert FinalAnswer
    assert FeedbackArtifact
    assert SourceRejectionRecord


def test_graph_contract_names_roles_budgets_and_trace_owner() -> None:
    from app.artifacts.workflow_artifacts import TraceEvent
    from app.workflow.graph_contract import (
        NODE_CONTRACTS,
        QUERY_BUDGETS,
        GraphState,
        build_initial_state,
    )

    required_nodes = {
        "Supervisor",
        "FedStat Scout",
        "World Bank Scout",
        "CKAN Scout",
        "Coverage & Schema",
        "Extraction Planner",
        "Deterministic Tools",
        "Methodology Critic",
        "Narrator",
        "Visualization",
    }

    assert required_nodes.issubset({node.name for node in NODE_CONTRACTS})
    assert QUERY_BUDGETS["Direct lookup"].tool_call_limit < QUERY_BUDGETS["Research query"].tool_call_limit
    state = build_initial_state("Какой ВВП России?", case_id="GC-T")
    assert isinstance(state, GraphState)
    assert all(isinstance(event, TraceEvent) for event in state.trace_events)


def test_run_graph_emits_machine_readable_trace(tmp_path: Path) -> None:
    from app.workflow.run_graph import run_golden_case

    goldens = tmp_path / "golden.yaml"
    goldens.write_text(
        """
- id: GC-T
  category: simple
  query_ru: "Какой ВВП России?"
  expected_sources:
    - "FedStat"
  needs_clarification: false
""",
        encoding="utf-8",
    )
    manifest = tmp_path / "embedding-index-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "status": "gated_skip",
                "dense_status": "gated_skip",
                "vector_store": "qdrant",
                "collection_name": "phase1_source_cards_test",
                "corpus_artifact_path": str(tmp_path / "missing.jsonl"),
                "missing_env_vars": ["YANDEX_AI_STUDIO_API_KEY"],
            }
        ),
        encoding="utf-8",
    )

    result = run_golden_case(
        goldens_path=goldens,
        case_index=0,
        index_manifest_path=manifest,
    )

    assert result["status"] == "gated"
    assert result["qdrant_status"] == "gated_skip"
    assert result["trace_events"]
    assert result["rejected_sources"] or result["selected_sources"] or result["no_data_reason"]
    assert "unsupported_numeric_claim" not in json.dumps(result)
