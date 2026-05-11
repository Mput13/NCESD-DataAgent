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


def test_workflow_runtime_does_not_reference_golden_fixture_files() -> None:
    """Runtime workflow modules must not read acceptance fixtures as hints."""
    offenders: list[str] = []
    forbidden = ("golden-coverage-matrix.json", "golden-cases.yaml", "matrix_hint", "_case_id")
    for path in Path("app/workflow").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        hits = [needle for needle in forbidden if needle in source]
        if hits:
            offenders.append(f"{path}: {', '.join(hits)}")

    assert not offenders, "Acceptance fixture leakage in runtime:\n" + "\n".join(offenders)


def test_design_research_prompt_has_no_matrix_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock

    from app.artifacts.workflow_artifacts import IntentFrame
    from app.workflow.state import _ResearchDesignSchema, design_research

    captured_messages: list[dict[str, str]] = []

    def fake_structured_chat(messages, *, schema, **kwargs):
        captured_messages.extend(messages)
        return _ResearchDesignSchema(hypotheses=["h"], dimensions=[], indicators=[])

    mock_client = MagicMock()
    mock_client.structured_chat.side_effect = fake_structured_chat
    monkeypatch.setattr(
        "app.llm.yandex_ai_studio.qwen_credential_gate",
        lambda: {"status": "ready", "missing_env_vars": []},
    )
    monkeypatch.setattr("app.llm.yandex_ai_studio.YandexAIStudioClient", lambda: mock_client)

    design_research(
        IntentFrame(
            query="ВВП России",
            category="simple",
            known_fields={"geography": "Россия"},
        ),
        live_llm_required=True,
    )

    prompt_text = "\n".join(message["content"] for message in captured_messages)
    assert "матрицы покрытия" not in prompt_text
    assert "golden" not in prompt_text.lower()
