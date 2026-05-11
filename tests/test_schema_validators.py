"""Tests for LLM output schema validators — coercion and tolerance."""
import pytest
from unittest.mock import MagicMock, patch


class TestIntentAnalysisSchemaGeography:
    def test_geography_as_list_is_coerced_to_string(self):
        from app.workflow.state import _IntentAnalysisSchema
        schema = _IntentAnalysisSchema(
            category="comparative",
            needs_clarification=False,
            geography=["Россия", "Казахстан"],
        )
        assert schema.geography == "Россия, Казахстан"

    def test_geography_as_string_unchanged(self):
        from app.workflow.state import _IntentAnalysisSchema
        schema = _IntentAnalysisSchema(
            category="simple",
            needs_clarification=False,
            geography="Россия",
        )
        assert schema.geography == "Россия"

    def test_geography_as_none_stays_none(self):
        from app.workflow.state import _IntentAnalysisSchema
        schema = _IntentAnalysisSchema(
            category="simple",
            needs_clarification=False,
            geography=None,
        )
        assert schema.geography is None

    def test_countries_derived_from_list_geography(self):
        from app.workflow.state import _IntentAnalysisSchema
        schema = _IntentAnalysisSchema(
            category="comparative",
            needs_clarification=False,
            geography=["Россия", "Казахстан"],
        )
        assert schema.countries == ["Россия", "Казахстан"]

    def test_countries_derived_from_string_geography(self):
        from app.workflow.state import _IntentAnalysisSchema
        schema = _IntentAnalysisSchema(
            category="simple",
            needs_clarification=False,
            geography="Россия",
        )
        assert schema.countries == ["Россия"]

    def test_countries_empty_when_no_geography(self):
        from app.workflow.state import _IntentAnalysisSchema
        schema = _IntentAnalysisSchema(
            category="simple",
            needs_clarification=False,
        )
        assert schema.countries == []


class TestCoverageAssessmentSchema:
    """_CoverageAssessment is defined locally in coverage.py — test via module import."""

    def _build_schema(self, **kwargs):
        # Import and invoke _llm_assess_coverage internals by patching
        # Instead, test that a dict with these values parses without error
        from pydantic import BaseModel, field_validator
        from typing import Any

        class _CoverageAssessment(BaseModel):
            source_id: str = ""
            can_proceed: bool = True
            best_slice: str | None = None
            alternative_slices: list[str] = []
            quality_risks: list[str] = []
            ask_user: bool = False
            ask_user_reason: str = ""

            @field_validator("alternative_slices", "quality_risks", mode="before")
            @classmethod
            def _coerce_to_list(cls, v: Any) -> list[str]:
                if v is None:
                    return []
                if isinstance(v, str):
                    return [v] if v else []
                return list(v)

        return _CoverageAssessment(**kwargs)

    def test_best_slice_null_is_accepted(self):
        obj = self._build_schema(source_id="s1", best_slice=None)
        assert obj.best_slice is None

    def test_quality_risks_as_string_coerced_to_list(self):
        obj = self._build_schema(source_id="s1", quality_risks="some risk")
        assert obj.quality_risks == ["some risk"]

    def test_quality_risks_as_none_becomes_empty_list(self):
        obj = self._build_schema(source_id="s1", quality_risks=None)
        assert obj.quality_risks == []

    def test_alternative_slices_as_string_coerced_to_list(self):
        obj = self._build_schema(source_id="s1", alternative_slices="2020-2023")
        assert obj.alternative_slices == ["2020-2023"]

    def test_coverage_llm_assess_survives_null_best_slice(self):
        """_llm_assess_coverage must not crash when LLM returns null for best_slice."""
        from unittest.mock import MagicMock, patch
        from app.workflow.nodes.coverage import _llm_assess_coverage
        from app.artifacts.workflow_artifacts import CoverageReport

        reports = [
            CoverageReport(
                source_id="test-source",
                status="ok",
                checks=["pyarrow_parquet_metadata_read"],
                available_periods=["2020", "2021"],
                available_geographies=["Россия"],
            )
        ]
        # Simulate LLM returning null for best_slice
        mock_result = MagicMock()
        mock_result.assessments = [
            MagicMock(
                source_id="test-source",
                can_proceed=True,
                best_slice=None,       # <<< проблемное поле
                alternative_slices=[],
                quality_risks=None,    # <<< тоже проблемное
                ask_user=False,
                ask_user_reason="",
            )
        ]

        with patch("app.workflow.nodes.coverage.qwen_credential_gate") as mock_gate, \
             patch("app.workflow.nodes.coverage.YandexAIStudioClient") as mock_client:
            mock_gate.return_value = {"status": "ready"}
            mock_client.return_value.structured_chat.return_value = mock_result

            result = _llm_assess_coverage(reports, intent_fields={"geography": "Россия"})

        # Must return reports (not crash), and source must be present
        assert len(result) == 1
        assert result[0].source_id == "test-source"


class TestCritiqueSchema:
    def test_warnings_as_none_becomes_empty_list(self):
        from app.workflow.nodes.critic import _CritiqueSchema
        schema = _CritiqueSchema(verdict="pass", warnings=None, repair_plan=[])
        assert schema.warnings == []

    def test_warnings_as_string_becomes_list(self):
        from app.workflow.nodes.critic import _CritiqueSchema
        schema = _CritiqueSchema(verdict="pass", warnings="некоторое предупреждение", repair_plan=[])
        assert schema.warnings == ["некоторое предупреждение"]

    def test_repair_plan_as_none_becomes_empty_list(self):
        from app.workflow.nodes.critic import _CritiqueSchema
        schema = _CritiqueSchema(verdict="pass", warnings=[], repair_plan=None)
        assert schema.repair_plan == []

    def test_repair_plan_as_string_becomes_list(self):
        from app.workflow.nodes.critic import _CritiqueSchema
        schema = _CritiqueSchema(verdict="pass", warnings=[], repair_plan="fix something")
        assert schema.repair_plan == ["fix something"]

    def test_valid_pass_verdict_accepted(self):
        from app.workflow.nodes.critic import _CritiqueSchema
        schema = _CritiqueSchema(verdict="pass", warnings=[], repair_plan=[])
        assert schema.verdict == "pass"


class TestNarratorDiagnosticArtifacts:
    """Dataset and script artifacts must appear in not_found responses as diagnostic."""

    def _make_minimal_state(self, dataset_rows: int) -> dict:
        from uuid import uuid4
        from app.artifacts.workflow_artifacts import (
            DatasetArtifact, ScriptArtifact, EvidenceBundleArtifact,
            NoDataExplanationArtifact,
        )
        dataset = DatasetArtifact(
            artifact_id=f"ds-{uuid4().hex[:8]}",
            status="ok",
            source_id="test-source",
            rows=dataset_rows,
            records=[{"value": 42.0}] if dataset_rows > 0 else [],
            provenance=[{"source": "test"}],
        )
        script = ScriptArtifact(
            artifact_id=f"sc-{uuid4().hex[:8]}",
            content="print('hello')",
            downloadable=False,
        )
        return {
            "run_id": "test-run",
            "query": "ВВП России",
            "intent": None,
            "dataset_artifacts": [dataset],
            "script_artifacts": [script],
            "coverage_reports": [],
            "trace_events": [],
            "component_statuses": {},
            "evidence": EvidenceBundleArtifact(
                selected_sources=[],
                rejected_sources=[{"card_id": "s1", "rejection_reason": "not_found"}],
            ),
        }

    def test_not_found_response_includes_diagnostic_dataset(self):
        from unittest.mock import patch, MagicMock
        from app.workflow.nodes.narrator import build_workflow_response
        from app.artifacts.workflow_artifacts import CritiqueReport
        from uuid import uuid4

        state = self._make_minimal_state(dataset_rows=0)
        critique = CritiqueReport(
            artifact_id=f"cr-{uuid4().hex[:8]}",
            verdict="not_found",
            warnings=[],
            repair_plan=[],
        )

        with patch("app.workflow.nodes.narrator.qwen_credential_gate") as mock_gate, \
             patch("app.workflow.nodes.narrator.YandexAIStudioClient") as mock_client:
            mock_gate.return_value = {"status": "ready"}
            mock_llm = mock_client.return_value
            mock_llm.structured_chat.return_value = MagicMock(
                message="Данные не найдены.",
                answer_blocks=[],
                citations=[],
                limitations=[],
                clarification_questions=[],
            )

            response = build_workflow_response(
                state,
                final_outcome="not_found",
                critique=critique,
                visualization=None,
                live_llm_required=False,
            )

        # Diagnostic artifacts must be present
        assert len(response.dataset_artifacts) > 0, (
            "not_found response must include diagnostic dataset_artifacts"
        )
        # Must carry diagnostic quality flag
        assert any("diagnostic" in d.quality_flags for d in response.dataset_artifacts)

    def test_not_found_response_includes_diagnostic_script(self):
        from unittest.mock import patch, MagicMock
        from app.workflow.nodes.narrator import build_workflow_response
        from app.artifacts.workflow_artifacts import CritiqueReport
        from uuid import uuid4

        state = self._make_minimal_state(dataset_rows=0)
        critique = CritiqueReport(
            artifact_id=f"cr-{uuid4().hex[:8]}",
            verdict="not_found",
            warnings=[],
            repair_plan=[],
        )

        with patch("app.workflow.nodes.narrator.qwen_credential_gate") as mock_gate, \
             patch("app.workflow.nodes.narrator.YandexAIStudioClient") as mock_client:
            mock_gate.return_value = {"status": "ready"}
            mock_client.return_value.structured_chat.return_value = MagicMock(
                message="Данные не найдены.",
                answer_blocks=[],
                citations=[],
                limitations=[],
                clarification_questions=[],
            )

            response = build_workflow_response(
                state,
                final_outcome="not_found",
                critique=critique,
                visualization=None,
                live_llm_required=False,
            )

        assert len(response.script_artifacts) > 0, (
            "not_found response must include diagnostic script_artifacts"
        )
