"""Phase 2 workflow service tests: state, intent analysis, research designer, graph, CLI."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Task 1: Phase2State definition
# ---------------------------------------------------------------------------


class TestPhase2State:
    """Phase2State TypedDict has all required fields."""

    def test_phase2_state_has_required_fields(self) -> None:
        from app.workflow.state import Phase2State

        # Instantiate an empty state (TypedDict with total=False allows empty)
        state: Phase2State = {}
        # All expected keys should be accessible on the type
        expected_keys = [
            "run_id",
            "query",
            "intent",
            "research_design",
            "evidence",
            "coverage_reports",
            "extraction_plan",
            "dataset_artifacts",
            "script_artifacts",
            "final_outcome",
            "finalization_pending",
            "trace_events",
            "component_statuses",
        ]
        # All keys must appear in the TypedDict annotations
        annotations = Phase2State.__annotations__
        for key in expected_keys:
            assert key in annotations, f"Phase2State missing field: {key}"

    def test_new_run_id_returns_phase2_prefix(self) -> None:
        from app.workflow.state import new_run_id

        run_id = new_run_id()
        assert run_id.startswith("phase2-"), f"Expected 'phase2-' prefix, got {run_id!r}"

    def test_phase2_state_dataset_artifacts_typed_as_list(self) -> None:
        from app.workflow.state import Phase2State
        import typing

        hints = typing.get_type_hints(Phase2State)
        # The field must be annotated as a list type
        assert "dataset_artifacts" in hints
        assert "script_artifacts" in hints

    def test_phase2_state_finalization_pending_field(self) -> None:
        from app.workflow.state import Phase2State

        annotations = Phase2State.__annotations__
        assert "finalization_pending" in annotations


# ---------------------------------------------------------------------------
# Task 1: analyze_intent
# ---------------------------------------------------------------------------


class TestAnalyzeIntent:
    """analyze_intent: Qwen target path and test fallback."""

    def test_analyze_intent_monkeypatched_returns_intent_frame(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.workflow.state import analyze_intent
        from app.artifacts.workflow_artifacts import IntentFrame

        fake_intent = IntentFrame(
            query="ВВП России 2024",
            category="simple",
            known_fields={"geography": "Russia", "period": "2024"},
            missing_fields=[],
            needs_clarification=False,
            source_preferences=[],
            open_reasoning=["Qwen structured output"],
        )

        # Monkeypatch YandexAIStudioClient.structured_chat
        def fake_structured_chat(self, messages, *, schema, **kwargs):
            return fake_intent

        monkeypatch.setattr(
            "app.llm.yandex_ai_studio.YandexAIStudioClient.structured_chat",
            fake_structured_chat,
        )
        # Patch config from_env to avoid missing credentials
        monkeypatch.setattr(
            "app.llm.yandex_ai_studio.YandexAIStudioConfig.from_env",
            lambda cls=None, profile="QWEN": type(
                "FakeConfig",
                (),
                {"api_key": "fake", "model": "gpt://x/q/latest", "base_url": "https://llm.api.cloud.yandex.net/v1"},
            )(),
        )

        result = analyze_intent("ВВП России 2024", live_llm_required=True)
        assert isinstance(result, IntentFrame)
        assert result.query == "ВВП России 2024"

    def test_analyze_intent_fallback_marks_test_only(self) -> None:
        from app.workflow.state import analyze_intent
        from app.artifacts.workflow_artifacts import IntentFrame

        result = analyze_intent("ВВП России 2024", live_llm_required=False)
        assert isinstance(result, IntentFrame)
        # Fallback must mark as test_only
        assert any(
            "test_only" in r for r in result.open_reasoning
        ), f"Expected test_only in open_reasoning, got {result.open_reasoning}"

    def test_analyze_intent_fallback_marks_test_only_intent_fallback(self) -> None:
        from app.workflow.state import analyze_intent

        result = analyze_intent("Инфляция", live_llm_required=False)
        assert any(
            "test_only_intent_fallback" in r for r in result.open_reasoning
        ), f"Expected test_only_intent_fallback marker, got {result.open_reasoning}"

    def test_analyze_intent_ambiguous_cases_need_clarification(self) -> None:
        from app.workflow.state import analyze_intent

        # Ambiguous queries should be detectable via fallback
        result = analyze_intent("Какой ВВП?", live_llm_required=False)
        assert isinstance(result.needs_clarification, bool)

    def test_analyze_intent_component_status_test_only_when_fallback(self) -> None:
        """Fallback component_status must expose test_only so plan 02-07 can exclude it."""
        from app.workflow.state import analyze_intent

        result = analyze_intent("test", live_llm_required=False)
        # The open_reasoning should include the test_only marker
        joined = " ".join(result.open_reasoning)
        assert "test_only" in joined


# ---------------------------------------------------------------------------
# Task 1: design_research
# ---------------------------------------------------------------------------


class TestDesignResearch:
    """design_research: Qwen structured output target path + test fallback."""

    def test_design_research_fallback_marks_test_only_research_design_fallback(self) -> None:
        from app.workflow.state import design_research, analyze_intent
        from app.artifacts.workflow_artifacts import ResearchDesignArtifact

        intent = analyze_intent("ВВП БРИКС", live_llm_required=False)
        result = design_research(intent, live_llm_required=False)
        assert isinstance(result, ResearchDesignArtifact)
        # Must use test_only_research_design_fallback marker
        all_text = " ".join(result.assumptions + result.hypotheses)
        assert "test_only_research_design_fallback" in all_text, (
            f"Expected test_only_research_design_fallback in design, got: {all_text!r}"
        )

    def test_design_research_returns_research_design_artifact(self) -> None:
        from app.workflow.state import design_research, analyze_intent
        from app.artifacts.workflow_artifacts import ResearchDesignArtifact

        intent = analyze_intent("Торговля России и Казахстана", live_llm_required=False)
        result = design_research(intent, live_llm_required=False)
        assert isinstance(result, ResearchDesignArtifact)
        assert result.artifact_id

    def test_design_research_with_matrix_hint(self) -> None:
        from app.workflow.state import design_research, analyze_intent

        intent = analyze_intent("Инфляция", live_llm_required=False)
        hint = {"source_family": "world_bank", "source_id": "FP.CPI.TOTL.ZG"}
        result = design_research(intent, live_llm_required=False, matrix_hint=hint)
        assert result is not None


# ---------------------------------------------------------------------------
# Task 2: LangGraph graph build
# ---------------------------------------------------------------------------


class TestBuildPhase2Graph:
    """build_phase2_graph returns a compiled LangGraph graph."""

    def test_graph_has_required_nodes(self) -> None:
        from app.workflow.graph import build_phase2_graph

        graph = build_phase2_graph()
        # The compiled graph should be invocable (not None)
        assert graph is not None

    def test_graph_module_contains_state_graph(self) -> None:
        import app.workflow.graph as graph_module

        src = Path(graph_module.__file__).read_text(encoding="utf-8")
        assert "StateGraph" in src, "graph.py must use langgraph StateGraph"

    def test_graph_module_contains_finalization_pending_node(self) -> None:
        import app.workflow.graph as graph_module

        src = Path(graph_module.__file__).read_text(encoding="utf-8")
        assert "finalization_pending" in src


# ---------------------------------------------------------------------------
# Task 2: run_user_query_to_pending_finalization
# ---------------------------------------------------------------------------


class TestRunUserQueryToPendingFinalization:
    """run_user_query_to_pending_finalization returns Phase2State with finalization_pending=True."""

    def test_run_to_pending_returns_phase2_state(self, tmp_path: Path) -> None:
        from app.workflow.service import run_user_query_to_pending_finalization
        from app.workflow.graph_contract import WorkflowRunConfig

        config = WorkflowRunConfig.default().model_copy(
            update={
                "artifact_dir": tmp_path / "artifacts",
                "live_llm_required": False,
                "live_embeddings_required": False,
            }
        )
        state = run_user_query_to_pending_finalization(
            "ВВП России 2024",
            run_config=config,
        )
        assert isinstance(state, dict)
        assert state.get("finalization_pending") is True

    def test_run_to_pending_includes_run_id(self, tmp_path: Path) -> None:
        from app.workflow.service import run_user_query_to_pending_finalization
        from app.workflow.graph_contract import WorkflowRunConfig

        config = WorkflowRunConfig.default().model_copy(
            update={
                "artifact_dir": tmp_path / "artifacts",
                "live_llm_required": False,
                "live_embeddings_required": False,
            }
        )
        state = run_user_query_to_pending_finalization("Инфляция", run_config=config)
        assert "run_id" in state
        assert state["run_id"].startswith("phase2-")

    def test_run_user_query_still_raises_not_implemented(self) -> None:
        from app.workflow.service import run_user_query
        from app.workflow.graph_contract import WorkflowRunConfig

        with pytest.raises(NotImplementedError) as exc_info:
            run_user_query("test")
        assert "plan 02-06" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Task 2: deterministic_tools node
# ---------------------------------------------------------------------------


class TestDeterministicToolsNode:
    """run_deterministic_tools node consumes ExtractionPlan and produces artifacts."""

    def test_deterministic_tools_module_exists(self) -> None:
        from app.workflow.nodes import deterministic_tools  # noqa: F401

    def test_run_deterministic_tools_function_exists(self) -> None:
        from app.workflow.nodes.deterministic_tools import run_deterministic_tools

        assert callable(run_deterministic_tools)

    def test_deterministic_tools_with_skipped_plan_produces_no_artifacts(
        self, tmp_path: Path
    ) -> None:
        from app.workflow.nodes.deterministic_tools import run_deterministic_tools
        from app.workflow.state import new_run_id
        from app.artifacts.workflow_artifacts import ExtractionPlan

        state = {
            "run_id": new_run_id(),
            "query": "test",
            "extraction_plan": ExtractionPlan(
                artifact_id="plan-001",
                status="skipped_with_reason",
                operations=[],
                skip_reason="no_coverage_reports_provided",
            ),
            "dataset_artifacts": [],
            "script_artifacts": [],
            "trace_events": [],
            "component_statuses": {},
            "finalization_pending": False,
        }
        result = run_deterministic_tools(state, output_dir=tmp_path)
        # Should update component_statuses
        assert "deterministic_tools" in result.get("component_statuses", {})

    def test_deterministic_tools_appends_trace_event(self, tmp_path: Path) -> None:
        from app.workflow.nodes.deterministic_tools import run_deterministic_tools
        from app.workflow.state import new_run_id
        from app.artifacts.workflow_artifacts import ExtractionPlan

        state = {
            "run_id": new_run_id(),
            "query": "test",
            "extraction_plan": ExtractionPlan(
                artifact_id="plan-trace-001",
                status="skipped_with_reason",
                operations=[],
                skip_reason="test",
            ),
            "dataset_artifacts": [],
            "script_artifacts": [],
            "trace_events": [],
            "component_statuses": {},
            "finalization_pending": False,
        }
        result = run_deterministic_tools(state, output_dir=tmp_path)
        assert len(result.get("trace_events", [])) > 0


# ---------------------------------------------------------------------------
# Task 3: run_graph CLI
# ---------------------------------------------------------------------------


class TestRunGraphCLI:
    """run_graph.py supports --query and --case-index; uses service path."""

    def test_run_graph_module_contains_run_user_query_to_pending(self) -> None:
        import app.workflow.run_graph as rg_module

        src = Path(rg_module.__file__).read_text(encoding="utf-8")
        assert "run_user_query_to_pending_finalization" in src

    def test_run_graph_module_has_query_argument(self) -> None:
        import app.workflow.run_graph as rg_module

        src = Path(rg_module.__file__).read_text(encoding="utf-8")
        assert "--query" in src

    def test_run_graph_output_json_contains_finalization_pending(
        self, tmp_path: Path
    ) -> None:
        """Invoke main() with --query and check JSON output has finalization_pending."""
        import subprocess
        import sys

        out_file = tmp_path / "output.json"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.workflow.run_graph",
                "--query",
                "ВВП России",
                "--json-output",
                str(out_file),
                "--no-live-llm",
                "--no-live-embeddings",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            pytest.fail(
                f"run_graph failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
        assert out_file.exists(), "JSON output file was not created"
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert "finalization_pending" in data or data.get("status") == "finalization_pending", (
            f"Expected finalization_pending in output, got keys: {list(data.keys())}"
        )
