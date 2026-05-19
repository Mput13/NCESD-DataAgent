from __future__ import annotations

import json
from pathlib import Path

import pytest


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


def test_run_graph_emits_machine_readable_trace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 2: run_golden_case uses Phase2State with finalization_pending (LLM mocked)."""
    from unittest.mock import MagicMock
    from app.workflow.run_graph import run_golden_case
    from app.workflow.state import _IntentAnalysisSchema

    # Mock LLM so the graph runs without real Yandex credentials
    mock_intent = _IntentAnalysisSchema(
        category="simple",
        needs_clarification=False,
        geography="Россия",
        period="2024",
        indicator="ВВП",
        source_preferences=["world_bank"],
        missing_fields=[],
    )
    fake_client = MagicMock()
    fake_client.structured_chat.return_value = mock_intent
    monkeypatch.setattr("app.llm.yandex_ai_studio.qwen_credential_gate",
                        lambda: {"status": "ok", "missing_env_vars": []})
    monkeypatch.setattr("app.llm.yandex_ai_studio.YandexAIStudioClient", lambda: fake_client)

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
    json_output = tmp_path / "output.json"

    result = run_golden_case(
        goldens_path=goldens,
        case_index=0,
        json_output=json_output,
        live_llm=True,
        live_embeddings=False,
        artifact_dir=tmp_path / "artifacts",
    )

    assert result.get("run_id", "").startswith("phase2-")
    assert "unsupported_numeric_claim" not in json.dumps(result)


def test_phase2_graph_routes_intent_to_retrieval_planner_not_research_designer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 2026-05-19 removes pre-retrieval Research Designer from runtime path."""
    from app.artifacts.workflow_artifacts import (
        AmbiguityPolicy,
        DimensionIntent,
        MeasureIntent,
        OperationIntent,
        RetrievalInput,
        SearchProbe,
        SourceScope,
        TaskIntent,
        UserIntentArtifact,
    )
    from app.workflow.graph import _node_retrieval_planner, _route_after_intent

    intent = UserIntentArtifact(
        original_query="ВВП России 2024",
        task=TaskIntent(category="direct_lookup", user_goal="Найти ВВП России.", expected_output="answer"),
        measures=[
            MeasureIntent(
                measure_id="m1",
                user_phrase="ВВП",
                canonical_concept="gross domestic product",
                aliases_ru=["ВВП"],
                aliases_en=["GDP"],
                official_terms_ru=["валовой внутренний продукт"],
                official_terms_en=["gross domestic product"],
                measurement_form="level",
            )
        ],
        dimensions=DimensionIntent(),
        operations=OperationIntent(),
        source_scope=SourceScope(),
        ambiguity=AmbiguityPolicy(needs_clarification=False),
    )

    state = {
        "run_id": "phase2-test",
        "query": intent.original_query,
        "canonical_intent": intent,
        "intent": intent.to_intent_frame(),
        "trace_events": [],
        "component_statuses": {},
        "_supervisor_route": "research",
    }
    retrieval_input = RetrievalInput(
        original_query=intent.original_query,
        probes=[
            SearchProbe(
                probe_id="p_llm_wb",
                text="gross domestic product GDP",
                purpose="alias",
                measure_id="m1",
                language="en",
                priority=100,
                source_family_hint="world_bank",
                origin="llm",
            )
        ],
    )
    called = []
    monkeypatch.setattr(
        "app.workflow.graph.plan_retrieval",
        lambda canonical_intent: called.append(canonical_intent) or retrieval_input,
    )

    assert _route_after_intent(state) == "retrieval_planner"
    next_state = _node_retrieval_planner(state)
    assert called == [intent]
    assert next_state["retrieval_input"].probes
    assert next_state["trace_events"][-1].state == "retrieval_planner"
