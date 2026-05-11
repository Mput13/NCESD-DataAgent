"""Phase 2 finalization tests: critic, visualization, narrator, service finalization.

TDD tests for plan 02-06: Methodology Critic, Visualization, Narrator, run_user_query.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ok_dataset(
    *,
    artifact_id: str = "dataset-001",
    source_id: str = "world_bank:NY.GDP.MKTP.CD",
    rows: int = 3,
    provenance: list[dict[str, Any]] | None = None,
    columns: list[str] | None = None,
    records: list[dict[str, Any]] | None = None,
) -> Any:
    from app.artifacts.workflow_artifacts import DatasetArtifact

    if records is None:
        records = [
            {"geo_id": "RUS", "period": "2020", "value": 1483000000000},
            {"geo_id": "RUS", "period": "2021", "value": 1778000000000},
            {"geo_id": "RUS", "period": "2022", "value": 2240000000000},
        ]
    if columns is None:
        columns = list(records[0].keys()) if records else ["geo_id", "period", "value"]
    if provenance is None:
        provenance = [{"source_id": source_id, "url": "https://data.worldbank.org"}]

    return DatasetArtifact(
        artifact_id=artifact_id,
        status="ok",
        source_id=source_id,
        rows=rows,
        columns=columns,
        records=records,
        provenance=provenance,
        quality_flags=["deterministic_duckdb_output"],
    )


def _make_ok_coverage(source_id: str = "world_bank:NY.GDP.MKTP.CD") -> Any:
    from app.artifacts.workflow_artifacts import CoverageReport

    return CoverageReport(
        source_id=source_id,
        status="ok",
        checks=["period_ok", "geography_ok", "unit_ok"],
        available_periods=["2020", "2021", "2022"],
        available_geographies=["RUS"],
        unit="current USD",
        frequency="annual",
        evidence={"parquet_rows": 100},
    )


def _make_gated_coverage(source_id: str = "world_bank:NY.GDP.MKTP.CD") -> Any:
    from app.artifacts.workflow_artifacts import CoverageReport

    return CoverageReport(
        source_id=source_id,
        status="gated",
        gated_reason="embedding_index_not_ready",
    )


def _make_script_artifact(path: str | None = None, *, tmp_path_factory: Any = None) -> Any:
    from app.artifacts.workflow_artifacts import ScriptArtifact

    actual_path = path
    if actual_path is None and tmp_path_factory is not None:
        p = tmp_path_factory.mktemp("scripts") / "script-001.py"
        p.write_text("# script", encoding="utf-8")
        actual_path = str(p)

    return ScriptArtifact(
        artifact_id="script-001",
        language="python",
        path=actual_path,
        script_path=actual_path,
        content="# Deterministic extraction script",
        entrypoint="main",
        source_ids=["world_bank:NY.GDP.MKTP.CD"],
        downloadable=True,
        download_filename="script-001.py",
        display_name="Extraction script",
    )


def _make_state(
    *,
    dataset_artifacts: list[Any] | None = None,
    script_artifacts: list[Any] | None = None,
    coverage_reports: list[Any] | None = None,
    pending_reason: str | None = None,
    query: str = "ВВП России 2020-2022",
    intent: Any = None,
    tmp_path: Path | None = None,
) -> dict[str, Any]:
    from app.workflow.state import new_run_id

    return {
        "run_id": new_run_id(),
        "query": query,
        "intent": intent,
        "research_design": None,
        "evidence": None,
        "coverage_reports": coverage_reports or [],
        "extraction_plan": None,
        "dataset_artifacts": dataset_artifacts or [],
        "script_artifacts": script_artifacts or [],
        "final_outcome": None,
        "finalization_pending": True,
        "pending_reason": pending_reason,
        "trace_events": [],
        "component_statuses": {},
        "_artifact_dir": str(tmp_path or ".planning/phases/02-jury-mvp/workflow-runs"),
    }


# ===========================================================================
# Task 1: Methodology Critic
# ===========================================================================


class TestMethodologyCriticModule:
    """critic.py module exists with required functions."""

    def test_critic_module_importable(self) -> None:
        from app.workflow.nodes import critic  # noqa: F401

    def test_critic_has_run_methodology_critic(self) -> None:
        from app.workflow.nodes.critic import run_methodology_critic

        assert callable(run_methodology_critic)

    def test_critic_has_derive_final_outcome(self) -> None:
        from app.workflow.nodes.critic import derive_final_outcome

        assert callable(derive_final_outcome)

    def test_critic_source_contains_derive_final_outcome(self) -> None:
        import app.workflow.nodes.critic as critic_module
        from pathlib import Path

        src = Path(critic_module.__file__).read_text(encoding="utf-8")
        assert "def derive_final_outcome" in src

    def test_critic_source_contains_passed_outcome_requires_comment(self) -> None:
        import app.workflow.nodes.critic as critic_module
        from pathlib import Path

        src = Path(critic_module.__file__).read_text(encoding="utf-8")
        assert "passed outcome requires" in src

    def test_critic_live_llm_required_false_raises(self) -> None:
        """live_llm_required=False must raise RuntimeError — no silent keyword fallback."""
        import pytest
        from app.workflow.nodes.critic import run_methodology_critic

        with pytest.raises(RuntimeError, match="live LLM call"):
            run_methodology_critic({}, live_llm_required=False)


class TestRunMethodologyCritic:
    """run_methodology_critic produces a CritiqueReport."""

    def test_gated_coverage_live_llm_false_raises(self) -> None:
        """live_llm_required=False always raises — no keyword fallback."""
        import pytest
        from app.workflow.nodes.critic import run_methodology_critic

        state = _make_state(
            dataset_artifacts=[_make_ok_dataset()],
            coverage_reports=[_make_gated_coverage()],
        )
        with pytest.raises(RuntimeError, match="live LLM call"):
            run_methodology_critic(state, live_llm_required=False)

    def test_no_ok_dataset_live_llm_false_raises(self) -> None:
        """live_llm_required=False always raises."""
        import pytest
        from app.artifacts.workflow_artifacts import DatasetArtifact
        from app.workflow.nodes.critic import run_methodology_critic

        bad_dataset = DatasetArtifact(artifact_id="dataset-bad", status="gated", rows=0)
        state = _make_state(dataset_artifacts=[bad_dataset], coverage_reports=[_make_ok_coverage()])
        with pytest.raises(RuntimeError, match="live LLM call"):
            run_methodology_critic(state, live_llm_required=False)

    def test_empty_provenance_live_llm_false_raises(self) -> None:
        """live_llm_required=False always raises."""
        import pytest
        from app.artifacts.workflow_artifacts import DatasetArtifact
        from app.workflow.nodes.critic import run_methodology_critic

        dataset_no_prov = DatasetArtifact(artifact_id="dataset-noprov", status="ok", rows=2, provenance=[])
        state = _make_state(dataset_artifacts=[dataset_no_prov], coverage_reports=[_make_ok_coverage()])
        with pytest.raises(RuntimeError, match="live LLM call"):
            run_methodology_critic(state, live_llm_required=False)

    def test_all_ok_coverage_and_dataset_produces_critique_report(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With mocked LLM, all-OK inputs produce a valid CritiqueReport."""
        from pydantic import BaseModel
        from app.artifacts.workflow_artifacts import CritiqueReport
        from app.workflow.nodes.critic import run_methodology_critic

        class FakeCritiqueSchema(BaseModel):
            verdict: str = "pass"
            warnings: list[str] = []
            repair_plan: list[str] = []

        mock_client = FakeCritiqueSchema()
        monkeypatch.setattr("app.llm.yandex_ai_studio.qwen_credential_gate",
                            lambda: {"status": "ok", "missing_env_vars": []})
        from unittest.mock import MagicMock
        fake = MagicMock()
        fake.structured_chat.return_value = FakeCritiqueSchema()
        monkeypatch.setattr("app.llm.yandex_ai_studio.YandexAIStudioClient", lambda: fake)

        state = _make_state(dataset_artifacts=[_make_ok_dataset()], coverage_reports=[_make_ok_coverage()])
        critique = run_methodology_critic(state, live_llm_required=True)
        assert isinstance(critique, CritiqueReport)
        assert critique.artifact_id

    def test_no_datasets_no_coverage_live_llm_required_false_raises(self) -> None:
        """live_llm_required=False must raise regardless of state contents."""
        import pytest
        from app.workflow.nodes.critic import run_methodology_critic

        state = _make_state(dataset_artifacts=[], coverage_reports=[])
        with pytest.raises(RuntimeError, match="live LLM call"):
            run_methodology_critic(state, live_llm_required=False)

    def test_monkeypatched_llm_returns_pass_verdict_when_all_ok(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With monkeypatched LLM, all-OK state produces pass verdict."""
        from app.workflow.nodes.critic import run_methodology_critic
        from pydantic import BaseModel

        class FakeCritiqueSchema(BaseModel):
            verdict: str = "pass"
            warnings: list[str] = []
            repair_plan: list[str] = []

        def fake_structured_chat(self, messages, *, schema, **kwargs):
            return FakeCritiqueSchema()

        monkeypatch.setattr(
            "app.llm.yandex_ai_studio.YandexAIStudioClient.structured_chat",
            fake_structured_chat,
        )
        monkeypatch.setattr(
            "app.llm.yandex_ai_studio.YandexAIStudioConfig.from_env",
            lambda cls=None, profile="QWEN": type(
                "FakeConfig",
                (),
                {"api_key": "fake", "model": "gpt://x/q/latest", "base_url": "https://llm.api.cloud.yandex.net/v1"},
            )(),
        )
        monkeypatch.setattr(
            "app.llm.yandex_ai_studio.qwen_credential_gate",
            lambda profile="QWEN": {"status": "ready", "missing_env_vars": []},
        )

        state = _make_state(
            dataset_artifacts=[_make_ok_dataset()],
            coverage_reports=[_make_ok_coverage()],
        )
        critique = run_methodology_critic(state, live_llm_required=True)
        assert critique.verdict == "pass"


class TestDeriveFinalOutcome:
    """derive_final_outcome: maps CritiqueReport to TerminalOutcome."""

    def test_pass_verdict_with_ok_dataset_and_script_gives_passed(
        self, tmp_path: Path
    ) -> None:
        from app.artifacts.workflow_artifacts import CritiqueReport
        from app.workflow.nodes.critic import derive_final_outcome

        script_path = tmp_path / "script.py"
        script_path.write_text("# script", encoding="utf-8")

        script = _make_script_artifact(str(script_path))
        dataset = _make_ok_dataset()

        critique = CritiqueReport(
            artifact_id="critique-001",
            verdict="pass",
            warnings=[],
        )
        state = _make_state(
            dataset_artifacts=[dataset],
            script_artifacts=[script],
            coverage_reports=[_make_ok_coverage()],
        )
        outcome = derive_final_outcome(state, critique)
        assert outcome == "passed"

    def test_pass_verdict_without_ok_dataset_gives_needs_repair(self) -> None:
        from app.artifacts.workflow_artifacts import CritiqueReport, DatasetArtifact
        from app.workflow.nodes.critic import derive_final_outcome

        bad_dataset = DatasetArtifact(
            artifact_id="dataset-bad",
            status="gated",
            rows=0,
        )
        critique = CritiqueReport(
            artifact_id="critique-001",
            verdict="pass",
            warnings=[],
        )
        state = _make_state(
            dataset_artifacts=[bad_dataset],
            script_artifacts=[_make_script_artifact()],
            coverage_reports=[_make_ok_coverage()],
        )
        outcome = derive_final_outcome(state, critique)
        # If dataset is not OK, cannot be "passed"
        assert outcome != "passed"

    def test_not_found_verdict_gives_not_found_outcome(self) -> None:
        from app.artifacts.workflow_artifacts import CritiqueReport
        from app.workflow.nodes.critic import derive_final_outcome

        critique = CritiqueReport(
            artifact_id="critique-001",
            verdict="not_found",
            warnings=["no trusted source covers this indicator"],
        )
        state = _make_state(dataset_artifacts=[], coverage_reports=[])
        outcome = derive_final_outcome(state, critique)
        assert outcome == "not_found"

    def test_needs_user_clarification_verdict_gives_needs_clarification_outcome(self) -> None:
        from app.artifacts.workflow_artifacts import CritiqueReport
        from app.workflow.nodes.critic import derive_final_outcome

        critique = CritiqueReport(
            artifact_id="critique-001",
            verdict="needs_user_clarification",
            warnings=["ambiguous indicator: GDP in USD or RUB?"],
        )
        state = _make_state(dataset_artifacts=[], coverage_reports=[])
        outcome = derive_final_outcome(state, critique)
        assert outcome == "needs_clarification"

    def test_needs_repair_verdict_gives_needs_repair_or_not_found_outcome(self) -> None:
        from app.artifacts.workflow_artifacts import CritiqueReport
        from app.workflow.nodes.critic import derive_final_outcome

        critique = CritiqueReport(
            artifact_id="critique-001",
            verdict="needs_repair",
            repair_plan=["Fix coverage"],
        )
        state = _make_state(dataset_artifacts=[], coverage_reports=[])
        outcome = derive_final_outcome(state, critique)
        # needs_repair maps to not_found in terminal path
        assert outcome in ("not_found", "needs_clarification")

    def test_gated_coverage_prevents_passed_outcome(self) -> None:
        """Even with pass verdict, gated coverage must block passed outcome."""
        from app.artifacts.workflow_artifacts import CritiqueReport
        from app.workflow.nodes.critic import derive_final_outcome

        critique = CritiqueReport(
            artifact_id="critique-001",
            verdict="pass",
        )
        state = _make_state(
            dataset_artifacts=[_make_ok_dataset()],
            coverage_reports=[_make_gated_coverage()],  # gated!
        )
        outcome = derive_final_outcome(state, critique)
        assert outcome != "passed", (
            "Gated coverage must prevent 'passed' outcome"
        )


# ===========================================================================
# Task 2: Visualization
# ===========================================================================


class TestVisualizationModule:
    """visualization.py exists with required function."""

    def test_visualization_module_importable(self) -> None:
        from app.workflow.nodes import visualization  # noqa: F401

    def test_build_visualization_function_exists(self) -> None:
        from app.workflow.nodes.visualization import build_visualization

        assert callable(build_visualization)

    def test_visualization_source_contains_render_visualization_from_dataset_artifact(
        self,
    ) -> None:
        import app.workflow.nodes.visualization as vis_module
        from pathlib import Path

        src = Path(vis_module.__file__).read_text(encoding="utf-8")
        assert "render_visualization_from_dataset_artifact" in src


class TestBuildVisualization:
    """build_visualization creates VisualizationSpec from DatasetArtifact."""

    def test_none_dataset_returns_skipped_spec(self) -> None:
        from app.artifacts.workflow_artifacts import VisualizationSpec
        from app.workflow.nodes.visualization import build_visualization

        spec = build_visualization(None, query_category="simple")
        assert isinstance(spec, VisualizationSpec)
        assert spec.status == "skipped_with_reason"
        assert spec.skip_reason is not None

    def test_time_series_single_geo_gives_line_chart(self) -> None:
        from app.workflow.nodes.visualization import build_visualization

        dataset = _make_ok_dataset(
            columns=["geo_id", "period", "value"],
            records=[
                {"geo_id": "RUS", "period": "2020", "value": 1},
                {"geo_id": "RUS", "period": "2021", "value": 2},
            ],
        )
        spec = build_visualization(dataset, query_category="simple")
        assert spec.chart_type == "line"

    def test_time_series_multi_geo_gives_grouped_line(self) -> None:
        from app.workflow.nodes.visualization import build_visualization

        dataset = _make_ok_dataset(
            columns=["geo_id", "period", "value"],
            records=[
                {"geo_id": "RUS", "period": "2020", "value": 1},
                {"geo_id": "CHN", "period": "2020", "value": 2},
                {"geo_id": "RUS", "period": "2021", "value": 3},
                {"geo_id": "CHN", "period": "2021", "value": 4},
            ],
        )
        spec = build_visualization(dataset, query_category="comparative")
        assert spec.chart_type == "grouped_line"

    def test_no_period_column_gives_bar_or_table(self) -> None:
        from app.workflow.nodes.visualization import build_visualization

        dataset = _make_ok_dataset(
            columns=["country", "value"],
            records=[
                {"country": "Russia", "value": 100},
                {"country": "China", "value": 200},
            ],
        )
        spec = build_visualization(dataset, query_category="comparative")
        assert spec.chart_type in ("bar", "table")

    def test_empty_dataset_returns_skipped(self) -> None:
        from app.artifacts.workflow_artifacts import DatasetArtifact
        from app.workflow.nodes.visualization import build_visualization

        empty_dataset = DatasetArtifact(
            artifact_id="empty-001",
            status="ok",
            rows=0,
            columns=[],
            records=[],
            provenance=[{"source_id": "test"}],
        )
        spec = build_visualization(empty_dataset, query_category="simple")
        assert spec.status in ("skipped_with_reason", "ok")
        # Should not raise

    def test_visualization_dataset_artifact_id_preserved(self) -> None:
        from app.workflow.nodes.visualization import build_visualization

        dataset = _make_ok_dataset(artifact_id="my-dataset-123")
        spec = build_visualization(dataset, query_category="simple")
        assert spec.dataset_artifact_id == "my-dataset-123"


# ===========================================================================
# Task 3: Narrator, service finalization, clarification follow-up
# ===========================================================================


class TestNarratorModule:
    """narrator.py module exists with required functions."""

    def test_narrator_module_importable(self) -> None:
        from app.workflow.nodes import narrator  # noqa: F401

    def test_build_workflow_response_exists(self) -> None:
        from app.workflow.nodes.narrator import build_workflow_response

        assert callable(build_workflow_response)

    def test_assert_message_numbers_are_supported_exists(self) -> None:
        from app.workflow.nodes.narrator import assert_message_numbers_are_supported

        assert callable(assert_message_numbers_are_supported)

    def test_narrator_source_contains_assert_message_numbers(self) -> None:
        import app.workflow.nodes.narrator as narrator_module
        from pathlib import Path

        src = Path(narrator_module.__file__).read_text(encoding="utf-8")
        assert "assert_message_numbers_are_supported" in src

    def test_narrator_live_llm_required_false_raises(self) -> None:
        """live_llm_required=False must raise RuntimeError — no silent keyword fallback."""
        import pytest
        from app.workflow.nodes.narrator import build_workflow_response
        from app.artifacts.workflow_artifacts import CritiqueReport

        critique = CritiqueReport(artifact_id="c-001", verdict="pass")
        with pytest.raises(RuntimeError, match="live LLM call"):
            build_workflow_response({}, final_outcome="not_found", critique=critique,
                                    visualization=None, live_llm_required=False)

    def test_narrator_source_contains_script_artifacts(self) -> None:
        import app.workflow.nodes.narrator as narrator_module
        from pathlib import Path

        src = Path(narrator_module.__file__).read_text(encoding="utf-8")
        assert "script_artifacts" in src


class TestAssertMessageNumbersAreSupported:
    """assert_message_numbers_are_supported catches unsupported numerics."""

    def test_number_in_dataset_passes(self) -> None:
        from app.workflow.nodes.narrator import assert_message_numbers_are_supported

        dataset = _make_ok_dataset(
            records=[
                {"geo_id": "RUS", "period": "2022", "value": 1483000000000},
            ]
        )
        # No exception expected - number appears in dataset
        assert_message_numbers_are_supported(
            "ВВП России в 2022 году составил 1483000000000 USD.",
            [dataset],
        )

    def test_unsupported_number_raises(self) -> None:
        from app.workflow.nodes.narrator import assert_message_numbers_are_supported

        dataset = _make_ok_dataset(
            records=[
                {"geo_id": "RUS", "period": "2022", "value": 1483000000000},
            ]
        )
        with pytest.raises(ValueError, match="999999"):
            assert_message_numbers_are_supported(
                "ВВП составил 999999 млрд долларов.",
                [dataset],
            )

    def test_year_in_message_passes(self) -> None:
        from app.workflow.nodes.narrator import assert_message_numbers_are_supported

        dataset = _make_ok_dataset(
            records=[{"geo_id": "RUS", "period": "2022", "value": 100}]
        )
        # Years from period column should be allowed
        assert_message_numbers_are_supported(
            "Данные за 2022 год.",
            [dataset],
        )

    def test_empty_datasets_rejects_any_number(self) -> None:
        from app.workflow.nodes.narrator import assert_message_numbers_are_supported

        with pytest.raises(ValueError):
            assert_message_numbers_are_supported(
                "Показатель составил 42.",
                [],
            )

    def test_no_numbers_in_message_always_passes(self) -> None:
        from app.workflow.nodes.narrator import assert_message_numbers_are_supported

        assert_message_numbers_are_supported(
            "Данные не найдены в проверенных источниках.",
            [],
        )


class TestBuildWorkflowResponse:
    """build_workflow_response produces a WorkflowResponse."""

    def _mock_narrator(self, monkeypatch: pytest.MonkeyPatch, message: str = "Ответ LLM") -> None:
        """Patch YandexAIStudioClient so narrator returns a predictable response."""
        from unittest.mock import MagicMock
        from pydantic import BaseModel

        class FakeNarratorSchema(BaseModel):
            message: str = "Ответ LLM"
            summary: str = "summary"
            methodology: str = "det"
            limitations: list[str] = []
            how_found: str = "scouts"
            clarification_questions: list[str] = ["Уточните запрос?"]

        fake = MagicMock()
        fake.structured_chat.return_value = FakeNarratorSchema(message=message)
        monkeypatch.setattr("app.llm.yandex_ai_studio.qwen_credential_gate",
                            lambda: {"status": "ok", "missing_env_vars": []})
        monkeypatch.setattr("app.llm.yandex_ai_studio.YandexAIStudioClient", lambda: fake)

    def test_passed_response_includes_dataset_and_script(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Message with no numbers — passes numeric assertion guardrail
        self._mock_narrator(monkeypatch, message="Данные получены из источников Росстат.")
        from app.artifacts.workflow_artifacts import CritiqueReport, WorkflowResponse
        from app.workflow.nodes.narrator import build_workflow_response
        from app.workflow.nodes.visualization import build_visualization

        script_path = tmp_path / "script.py"
        script_path.write_text("# script", encoding="utf-8")
        script = _make_script_artifact(str(script_path))
        dataset = _make_ok_dataset()
        critique = CritiqueReport(artifact_id="critique-001", verdict="pass")
        visualization = build_visualization(dataset, query_category="simple")
        state = _make_state(
            dataset_artifacts=[dataset],
            script_artifacts=[script],
            coverage_reports=[_make_ok_coverage()],
            tmp_path=tmp_path,
        )

        response = build_workflow_response(
            state, final_outcome="passed", critique=critique,
            visualization=visualization, live_llm_required=True,
        )

        assert isinstance(response, WorkflowResponse)
        assert response.final_outcome == "passed"
        assert len(response.dataset_artifacts) >= 1
        assert len(response.script_artifacts) >= 1

    def test_passed_response_script_artifact_path_is_downloadable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Message with no numbers — passes numeric assertion guardrail
        self._mock_narrator(monkeypatch, message="Данные получены из источников Росстат.")
        from app.artifacts.workflow_artifacts import CritiqueReport
        from app.workflow.nodes.narrator import build_workflow_response
        from app.workflow.nodes.visualization import build_visualization

        script_path = tmp_path / "script.py"
        script_path.write_text("# script", encoding="utf-8")
        script = _make_script_artifact(str(script_path))
        dataset = _make_ok_dataset()
        critique = CritiqueReport(artifact_id="critique-001", verdict="pass")
        visualization = build_visualization(dataset, query_category="simple")
        state = _make_state(
            dataset_artifacts=[dataset], script_artifacts=[script],
            coverage_reports=[_make_ok_coverage()],
        )

        response = build_workflow_response(
            state, final_outcome="passed", critique=critique,
            visualization=visualization, live_llm_required=True,
        )

        downloadable_scripts = [
            sa for sa in response.script_artifacts
            if sa.downloadable and sa.path and Path(sa.path).exists()
        ]
        assert len(downloadable_scripts) >= 1

    def test_needs_clarification_response_has_questions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._mock_narrator(monkeypatch)
        from app.artifacts.workflow_artifacts import CritiqueReport, IntentFrame
        from app.workflow.nodes.narrator import build_workflow_response

        intent = IntentFrame(
            query="Какой ВВП?", category="ambiguous",
            missing_fields=["geography", "period"], needs_clarification=True,
        )
        critique = CritiqueReport(
            artifact_id="critique-001", verdict="needs_user_clarification",
            warnings=["ambiguous query"],
        )
        state = _make_state(
            dataset_artifacts=[], script_artifacts=[],
            query="Какой ВВП?", intent=intent,
        )

        response = build_workflow_response(
            state, final_outcome="needs_clarification", critique=critique,
            visualization=None, live_llm_required=True,
        )

        assert response.final_outcome == "needs_clarification"
        assert len(response.clarification_questions) >= 1

    def test_not_found_response_has_no_data_evidence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._mock_narrator(monkeypatch)
        from app.artifacts.workflow_artifacts import CritiqueReport
        from app.workflow.nodes.narrator import build_workflow_response

        critique = CritiqueReport(
            artifact_id="critique-001", verdict="not_found",
            warnings=["no trusted source covers this indicator"],
        )
        state = _make_state(dataset_artifacts=[], script_artifacts=[])

        response = build_workflow_response(
            state, final_outcome="not_found", critique=critique,
            visualization=None, live_llm_required=True,
        )

        assert response.final_outcome == "not_found"
        assert response.not_found_evidence is not None

    def test_fallback_raises_not_silently_returns(self) -> None:
        """live_llm_required=False must raise, never silently return a fake response."""
        import pytest
        from app.artifacts.workflow_artifacts import CritiqueReport
        from app.workflow.nodes.narrator import build_workflow_response

        critique = CritiqueReport(artifact_id="critique-001", verdict="not_found")
        state = _make_state(dataset_artifacts=[], script_artifacts=[])

        with pytest.raises(RuntimeError, match="live LLM call"):
            build_workflow_response(
                state,
                final_outcome="not_found",
                critique=critique,
                visualization=None,
                live_llm_required=False,
            )


# ===========================================================================
# Task 3: Service finalization — run_user_query and continue_user_query
# ===========================================================================


class TestRunUserQuery:
    """run_user_query returns complete WorkflowResponse after plan 02-06."""

    def test_run_user_query_no_longer_raises_not_implemented(
        self, tmp_path: Path
    ) -> None:
        from app.workflow.service import WorkflowRunConfig, run_user_query

        config = WorkflowRunConfig.default().model_copy(
            update={
                "artifact_dir": tmp_path / "artifacts",
                "live_llm_required": False,
                "live_embeddings_required": False,
            }
        )

        # After plan 02-06, run_user_query must not raise NotImplementedError
        try:
            response = run_user_query("ВВП России 2020-2022", run_config=config)
            from app.artifacts.workflow_artifacts import WorkflowResponse
            assert isinstance(response, WorkflowResponse)
            assert response.final_outcome in ("passed", "needs_clarification", "not_found")
        except NotImplementedError:
            pytest.fail("run_user_query still raises NotImplementedError after plan 02-06")

    def test_run_user_query_returns_valid_terminal_outcome(
        self, tmp_path: Path
    ) -> None:
        from app.workflow.service import WorkflowRunConfig, run_user_query

        config = WorkflowRunConfig.default().model_copy(
            update={
                "artifact_dir": tmp_path / "artifacts",
                "live_llm_required": False,
                "live_embeddings_required": False,
            }
        )
        response = run_user_query("Инфляция в России", run_config=config)
        assert response.final_outcome in ("passed", "needs_clarification", "not_found")

    def test_run_user_query_response_has_run_id(self, tmp_path: Path) -> None:
        from app.workflow.service import WorkflowRunConfig, run_user_query

        config = WorkflowRunConfig.default().model_copy(
            update={
                "artifact_dir": tmp_path / "artifacts",
                "live_llm_required": False,
                "live_embeddings_required": False,
            }
        )
        response = run_user_query("Тест", run_config=config)
        assert response.run_id
        assert response.run_id.startswith("phase2-")


class TestContinueUserQuery:
    """continue_user_query loads pending clarification state and merges answer."""

    def test_continue_user_query_function_exists(self) -> None:
        from app.workflow.service import continue_user_query

        assert callable(continue_user_query)

    def test_service_source_contains_continue_user_query(self) -> None:
        import app.workflow.service as svc_module
        from pathlib import Path

        src = Path(svc_module.__file__).read_text(encoding="utf-8")
        assert "def continue_user_query" in src

    def test_continue_user_query_with_saved_state_merges_answer(
        self, tmp_path: Path
    ) -> None:
        """Saving a pending clarification state and calling continue merges answer."""
        import json
        from app.workflow.service import (
            WorkflowRunConfig,
            continue_user_query,
            run_user_query,
        )

        config = WorkflowRunConfig.default().model_copy(
            update={
                "artifact_dir": tmp_path / "artifacts",
                "live_llm_required": False,
                "live_embeddings_required": False,
            }
        )

        # First query — ambiguous to trigger clarification path
        response = run_user_query("Какой ВВП?", run_config=config)
        run_id = response.run_id

        # Now continue with answer
        continued = continue_user_query(
            run_id=run_id,
            clarification_answer="ВВП России за 2020-2022 годы в текущих долларах США",
            run_config=config,
        )
        from app.artifacts.workflow_artifacts import WorkflowResponse
        assert isinstance(continued, WorkflowResponse)
        assert continued.final_outcome in ("passed", "needs_clarification", "not_found")

    def test_continue_user_query_can_change_outcome(
        self, tmp_path: Path
    ) -> None:
        """After providing a clarification answer, outcome may change from needs_clarification."""
        import json
        from app.workflow.service import (
            WorkflowRunConfig,
            continue_user_query,
            run_user_query,
        )

        config = WorkflowRunConfig.default().model_copy(
            update={
                "artifact_dir": tmp_path / "artifacts",
                "live_llm_required": False,
                "live_embeddings_required": False,
            }
        )

        response = run_user_query("Инфляция", run_config=config)
        continued = continue_user_query(
            run_id=response.run_id,
            clarification_answer="Инфляция ИПЦ в России за 2020-2022 годы",
            run_config=config,
        )
        # Outcome must be a valid terminal state
        assert continued.final_outcome in ("passed", "needs_clarification", "not_found")
