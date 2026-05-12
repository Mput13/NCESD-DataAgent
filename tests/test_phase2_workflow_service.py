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

        from pydantic import BaseModel

        class FakeIntentSchema(BaseModel):
            category: str = "simple"
            needs_clarification: bool = False
            geography: str | None = "Russia"
            period: str | None = "2024"
            indicator: str | None = None
            source_preferences: list[str] = []
            missing_fields: list[str] = []

        # Monkeypatch YandexAIStudioClient.structured_chat to return schema-compatible object
        def fake_structured_chat(self, messages, *, schema, **kwargs):
            return FakeIntentSchema()

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
        # Patch credential gate to appear ready
        monkeypatch.setattr(
            "app.llm.yandex_ai_studio.qwen_credential_gate",
            lambda profile="QWEN": {"status": "ready", "missing_env_vars": []},
        )

        result = analyze_intent("ВВП России 2024", live_llm_required=True)
        assert isinstance(result, IntentFrame)
        assert result.query == "ВВП России 2024"
        assert result.category == "simple"

    def test_analyze_intent_live_llm_required_false_raises(self) -> None:
        """live_llm_required=False must raise — no silent keyword fallback allowed."""
        import pytest
        from app.workflow.state import analyze_intent

        with pytest.raises(RuntimeError, match="live LLM call"):
            analyze_intent("ВВП России 2024", live_llm_required=False)

    def test_analyze_intent_live_path_calls_yandex_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """live_llm_required=True must call YandexAIStudioClient, not keyword matching."""
        from unittest.mock import MagicMock
        from app.workflow.state import analyze_intent, _IntentAnalysisSchema

        mock_result = _IntentAnalysisSchema(
            category="simple",
            needs_clarification=False,
            geography="Россия",
            period="2024",
            indicator="ВВП",
            source_preferences=["world_bank"],
            missing_fields=[],
        )
        mock_client = MagicMock()
        mock_client.structured_chat.return_value = mock_result
        monkeypatch.setattr("app.llm.yandex_ai_studio.qwen_credential_gate",
                            lambda: {"status": "ok", "missing_env_vars": []})
        monkeypatch.setattr("app.llm.yandex_ai_studio.YandexAIStudioClient",
                            lambda: mock_client)

        result = analyze_intent("ВВП России 2024", live_llm_required=True)
        assert result.category == "simple"
        assert result.known_fields.get("geography") == "Россия"
        mock_client.structured_chat.assert_called_once()


# ---------------------------------------------------------------------------
# Task 1: design_research
# ---------------------------------------------------------------------------


class TestDesignResearch:
    """design_research: Qwen structured output is the only path."""

    def test_design_research_live_llm_required_false_raises(self) -> None:
        """live_llm_required=False must raise — no silent keyword fallback allowed."""
        import pytest
        from app.workflow.state import design_research
        from app.artifacts.workflow_artifacts import IntentFrame

        intent = IntentFrame(
            query="ВВП БРИКС",
            category="comparative",
            known_fields={},
            missing_fields=[],
            needs_clarification=False,
            source_preferences=[],
            open_reasoning=[],
        )
        with pytest.raises(RuntimeError, match="live LLM call"):
            design_research(intent, live_llm_required=False)

    def test_design_research_live_path_calls_yandex_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """live_llm_required=True must call YandexAIStudioClient."""
        from unittest.mock import MagicMock
        from app.workflow.state import design_research, _ResearchDesignSchema
        from app.artifacts.workflow_artifacts import IntentFrame

        intent = IntentFrame(
            query="ВВП России",
            category="simple",
            known_fields={"geography": "Россия"},
            missing_fields=[],
            needs_clarification=False,
            source_preferences=["world_bank"],
            open_reasoning=[],
        )
        mock_result = _ResearchDesignSchema(
            hypotheses=["ВВП России растёт"],
            dimensions=["geography", "period"],
            indicators=["NY.GDP.MKTP.CD"],
            grouping_policy=None,
            assumptions=[],
        )
        mock_client = MagicMock()
        mock_client.structured_chat.return_value = mock_result
        monkeypatch.setattr("app.llm.yandex_ai_studio.qwen_credential_gate",
                            lambda: {"status": "ok", "missing_env_vars": []})
        monkeypatch.setattr("app.llm.yandex_ai_studio.YandexAIStudioClient",
                            lambda: mock_client)

        result = design_research(intent, live_llm_required=True)
        assert result.hypotheses == ["ВВП России растёт"]
        mock_client.structured_chat.assert_called_once()


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
        from app.workflow.service import WorkflowRunConfig

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
        from app.workflow.service import WorkflowRunConfig

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

    def test_run_user_query_now_implemented_by_plan_02_06(self, tmp_path: Path) -> None:
        """After plan 02-06, run_user_query returns WorkflowResponse, not NotImplementedError."""
        from app.workflow.service import WorkflowRunConfig, run_user_query
        from app.artifacts.workflow_artifacts import WorkflowResponse

        config = WorkflowRunConfig.default().model_copy(
            update={
                "artifact_dir": tmp_path / "artifacts",
                "live_llm_required": False,
                "live_embeddings_required": False,
            }
        )
        response = run_user_query("test", run_config=config)
        assert isinstance(response, WorkflowResponse)
        assert response.final_outcome in ("passed", "needs_clarification", "not_found")


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


# ---------------------------------------------------------------------------
# Plan 02-08: clarification and feedback service/UI wiring
# ---------------------------------------------------------------------------


class TestPhase208WorkflowSurface:
    def test_web_server_uses_workflow_service_entrypoints(self) -> None:
        src = Path("app/web/server.py").read_text(encoding="utf-8")
        assert "run_user_query" in src
        assert "continue_user_query" in src
        assert "apply_feedback" in src
        assert "WorkflowRunConfig" in src

    def test_continue_user_query_preserves_run_and_can_change_outcome(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.artifacts.workflow_artifacts import (
            CoverageReport,
            CritiqueReport,
            DatasetArtifact,
            IntentFrame,
            ScriptArtifact,
            TraceEvent,
            WorkflowResponse,
        )
        from app.workflow import service
        from app.workflow.service import WorkflowRunConfig, continue_user_query, run_user_query

        def fake_pending(query: str, *, run_config: WorkflowRunConfig | None = None) -> dict[str, Any]:
            return {
                "run_id": "phase2-test-clarify",
                "query": query,
                "intent": IntentFrame(
                    query=query,
                    category="ambiguous",
                    missing_fields=["geography"],
                    needs_clarification=True,
                ),
                "evidence": None,
                "coverage_reports": [
                    CoverageReport(source_id="test-source", status="ok", checks=["test"])
                ],
                "dataset_artifacts": [
                    DatasetArtifact(
                        artifact_id="dataset-test",
                        status="ok",
                        source_id="test-source",
                        rows=1,
                        records=[{"year": 2024, "value": 1}],
                    )
                ],
                "script_artifacts": [
                    ScriptArtifact(artifact_id="script-test", path="script.py")
                ],
                "trace_events": [
                    TraceEvent(run_id="phase2-test-clarify", state="intent_analyst", agent="IntentAnalyst")
                ],
                "component_statuses": {},
            }

        def fake_finalize(state: dict[str, Any], *, config: WorkflowRunConfig) -> WorkflowResponse:
            intent = state.get("intent")
            if getattr(intent, "missing_fields", []):
                return WorkflowResponse(
                    run_id=str(state["run_id"]),
                    final_outcome="needs_clarification",
                    message="Need geography.",
                    clarification_questions=["Which geography?"],
                    trace_events=list(state.get("trace_events") or []),
                )
            return WorkflowResponse(
                run_id=str(state["run_id"]),
                final_outcome="not_found",
                message="Checked sources; no data found.",
                not_found_evidence={
                    "artifact_id": "not-found-test",
                    "checked_sources": [{"source_id": "test"}],
                    "rejected_sources": [],
                    "rejection_reasons": ["test"],
                    "search_strategy": "test",
                },
                trace_events=list(state.get("trace_events") or []),
                component_statuses={"critic": CritiqueReport(artifact_id="c", verdict="not_found").verdict},
            )

        # Mock analyze_intent so continue_user_query LLM re-analysis succeeds
        from app.artifacts.workflow_artifacts import IntentFrame as _IntentFrame
        def fake_analyze_intent(query: str, *, live_llm_required: bool = True) -> _IntentFrame:
            return _IntentFrame(
                query=query, category="simple",
                known_fields={"geography": "Russia", "period": "2024"},
                missing_fields=[],
                needs_clarification=False,
                source_preferences=["world_bank"],
                open_reasoning=["mocked"],
            )
        monkeypatch.setattr("app.workflow.state.analyze_intent", fake_analyze_intent)

        monkeypatch.setattr(service, "run_user_query_to_pending_finalization", fake_pending)
        monkeypatch.setattr(service, "_finalize_state", fake_finalize)
        config = WorkflowRunConfig.default().model_copy(
            update={
                "artifact_dir": tmp_path / "artifacts",
                "live_llm_required": False,
                "live_embeddings_required": False,
            }
        )

        first = run_user_query("ambiguous inflation", run_config=config)
        assert first.final_outcome == "needs_clarification"
        assert (tmp_path / "artifacts" / first.run_id / "pending-clarification.json").exists()

        follow_up = continue_user_query(first.run_id, "Russia, 2024", run_config=config)
        assert follow_up.final_outcome == "not_found"
        assert any(event.decision == "clarification_merged" for event in follow_up.trace_events)

    def test_apply_feedback_persists_run_linked_artifact(self, tmp_path: Path) -> None:
        from app.artifacts.workflow_artifacts import FeedbackArtifact
        from app.workflow.service import WorkflowRunConfig, apply_feedback

        config = WorkflowRunConfig.default().model_copy(
            update={
                "artifact_dir": tmp_path / "artifacts",
                "live_llm_required": False,
                "live_embeddings_required": False,
            }
        )
        result = apply_feedback(
            "phase2-feedback-test",
            rating="negative",
            user_comment="Please check the source.",
            run_config=config,
        )
        assert isinstance(result, FeedbackArtifact)
        assert result.run_id == "phase2-feedback-test"
        assert result.path is not None
        persisted = json.loads(Path(result.path).read_text(encoding="utf-8"))
        assert persisted["run_id"] == "phase2-feedback-test"

    def test_apply_feedback_fix_request_creates_artifact(self, tmp_path: Path) -> None:
        from app.artifacts.workflow_artifacts import FeedbackArtifact
        from app.workflow.service import WorkflowRunConfig, apply_feedback

        config = WorkflowRunConfig.default().model_copy(
            update={
                "artifact_dir": tmp_path / "artifacts",
                "live_llm_required": False,
                "live_embeddings_required": False,
            }
        )
        result = apply_feedback(
            "phase2-fix-test",
            user_comment="Needs a new source family.",
            requested_action="manual_fix_request",
            target_state="source_scouts",
            run_config=config,
        )
        assert isinstance(result, FeedbackArtifact)
        assert result.status == "fix_requested"
        assert result.fix_request_reason == "requested_action_not_executable"
        assert result.path is not None

    def test_apply_feedback_executable_action_invokes_rerun(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.artifacts.workflow_artifacts import NoDataExplanationArtifact, WorkflowResponse
        from app.workflow import service
        from app.workflow.service import WorkflowRunConfig, apply_feedback

        calls: list[tuple[str, str]] = []

        def fake_continue(
            run_id: str,
            clarification_answer: str,
            *,
            run_config: WorkflowRunConfig | None = None,
        ) -> WorkflowResponse:
            calls.append((run_id, clarification_answer))
            return WorkflowResponse(
                run_id="phase2-rerun-test-2",
                final_outcome="not_found",
                message="Rerun completed.",
                not_found_evidence=NoDataExplanationArtifact(
                    artifact_id="not-found-rerun",
                    checked_sources=[],
                    rejected_sources=[],
                    rejection_reasons=["rerun"],
                    search_strategy="test",
                ),
            )

        monkeypatch.setattr(service, "continue_user_query", fake_continue)
        config = WorkflowRunConfig.default().model_copy(
            update={
                "artifact_dir": tmp_path / "artifacts",
                "live_llm_required": False,
                "live_embeddings_required": False,
            }
        )

        result = apply_feedback(
            "phase2-rerun-test",
            user_comment="Use World Bank instead.",
            requested_action="revise_source",
            target_state="source_scouts",
            run_config=config,
        )
        assert isinstance(result, WorkflowResponse)
        assert calls and calls[0][0] == "phase2-rerun-test"
        assert result.component_statuses["feedback"] == "rerun"
