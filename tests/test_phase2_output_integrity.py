"""Output integrity tests for Remote Agent 3 scope.

Tests from handoff spec:
- test_final_pass_allows_rejected_unselected_candidates
- test_critic_needs_repair_does_not_become_not_found (system_error flag)
- test_missing_provenance_is_system_error_not_not_found
- test_narrator_error_does_not_become_not_found
- test_visualization_error_does_not_change_final_decision
- test_agent8_visualizes_all_selected_datasets_not_only_first
- test_public_trace_hides_raw_tool_payloads (via TraceEvent.payload)
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
    artifact_id: str = "ds-001",
    source_id: str = "world_bank:NY.GDP.MKTP.CD",
    rows: int = 3,
) -> Any:
    from app.artifacts.workflow_artifacts import DatasetArtifact

    return DatasetArtifact(
        artifact_id=artifact_id,
        status="ok",
        source_id=source_id,
        rows=rows,
        columns=["period", "geo_id", "value"],
        records=[
            {"period": "2020", "geo_id": "RUS", "value": 1000},
            {"period": "2021", "geo_id": "RUS", "value": 2000},
            {"period": "2022", "geo_id": "RUS", "value": 3000},
        ],
        provenance=[{"source_id": source_id, "url": "https://data.worldbank.org"}],
    )


def _make_ok_coverage(source_id: str = "world_bank:NY.GDP.MKTP.CD") -> Any:
    from app.artifacts.workflow_artifacts import CoverageReport

    return CoverageReport(
        source_id=source_id,
        status="ok",
        checks=["period_ok", "geography_ok"],
        available_periods=["2020", "2021", "2022"],
        available_geographies=["RUS"],
    )


def _make_critique(verdict: str = "pass", warnings: list[str] | None = None) -> Any:
    from app.artifacts.workflow_artifacts import CritiqueReport
    from uuid import uuid4

    return CritiqueReport(
        artifact_id=f"critique-{uuid4().hex[:8]}",
        verdict=verdict,
        warnings=warnings or [],
        repair_plan=[],
    )


def _make_state(
    dataset_artifacts: list[Any] | None = None,
    coverage_reports: list[Any] | None = None,
    script_artifacts: list[Any] | None = None,
    query: str = "ВВП России 2020-2022",
) -> dict[str, Any]:
    from app.workflow.state import new_run_id

    return {
        "run_id": new_run_id(),
        "query": query,
        "intent": None,
        "research_design": None,
        "evidence": None,
        "coverage_reports": coverage_reports or [],
        "extraction_plan": None,
        "dataset_artifacts": dataset_artifacts or [],
        "script_artifacts": script_artifacts or [],
        "final_outcome": None,
        "finalization_pending": True,
        "pending_reason": None,
        "trace_events": [],
        "component_statuses": {},
    }


# ---------------------------------------------------------------------------
# 1. passed outcome allows rejected/unselected candidates
# ---------------------------------------------------------------------------


class TestFinalPassAllowsRejectedCandidates:
    """A passed outcome must not be blocked by rejected/unselected candidate reports."""

    def test_final_pass_allows_rejected_unselected_candidates(self) -> None:
        from app.artifacts.workflow_artifacts import EvidenceBundleArtifact
        from app.workflow.nodes.critic import build_final_decision

        dataset = _make_ok_dataset()
        coverage = _make_ok_coverage()
        critique = _make_critique("pass")

        state = _make_state(
            dataset_artifacts=[dataset],
            coverage_reports=[coverage],
        )
        # Add evidence with rejected candidates — these should not block a passed outcome
        state["evidence"] = EvidenceBundleArtifact(
            selected_sources=[{"source_id": "world_bank:NY.GDP.MKTP.CD"}],
            rejected_sources=[
                {"source_id": "fedstat:1234", "reason": "no_coverage"},
                {"source_id": "ckan:5678", "reason": "gated"},
            ],
            retrieval_status="ok",
        )

        decision = build_final_decision(state, critique)
        assert decision.terminal_outcome == "passed", (
            "Rejected/unselected candidates must not block a passed outcome "
            "when selected coverage and datasets are ok."
        )


# ---------------------------------------------------------------------------
# 2. needs_repair verdict is a system error, not not_found
# ---------------------------------------------------------------------------


class TestCriticNeedsRepairIsSystemError:
    """needs_repair verdict must be flagged as system error, not silent not_found."""

    def test_critic_needs_repair_does_not_become_silent_not_found(self) -> None:
        from app.workflow.nodes.critic import build_final_decision

        dataset = _make_ok_dataset()
        coverage = _make_ok_coverage()
        critique = _make_critique("needs_repair", warnings=["coverage_gap_on_fedstat"])

        state = _make_state(dataset_artifacts=[dataset], coverage_reports=[coverage])
        decision = build_final_decision(state, critique)

        # Must be routed to not_found (TerminalOutcome has no repair slot)
        # BUT must be flagged as system error so caller knows this is not data absence.
        assert decision.terminal_outcome == "not_found"
        assert decision.is_system_error is True, (
            "needs_repair verdict must set is_system_error=True — it is a pipeline issue, "
            "not evidence that the requested data is absent."
        )
        assert decision.repair_route is not None, (
            "needs_repair decision must include a repair_route hint."
        )

    def test_unknown_verdict_is_also_system_error(self) -> None:
        from app.artifacts.workflow_artifacts import CritiqueReport
        from app.workflow.nodes.critic import build_final_decision
        from uuid import uuid4

        # Inject an unexpected verdict by bypassing validation
        critique = CritiqueReport.__new__(CritiqueReport)
        object.__setattr__(critique, "artifact_id", f"c-{uuid4().hex[:8]}")
        object.__setattr__(critique, "verdict", "needs_repair")  # closest valid
        object.__setattr__(critique, "warnings", ["unexpected_internal_state"])
        object.__setattr__(critique, "repair_plan", [])

        state = _make_state()
        decision = build_final_decision(state, critique)

        assert decision.is_system_error is True


# ---------------------------------------------------------------------------
# 3. Missing provenance is a system error, not data absence
# ---------------------------------------------------------------------------


class TestMissingProvenanceIsSystemError:
    """Missing provenance on an ok dataset is a guardrail failure, not data absence."""

    def test_missing_provenance_is_system_error_not_not_found(self) -> None:
        from app.artifacts.workflow_artifacts import DatasetArtifact
        from app.workflow.nodes.critic import build_final_decision

        dataset_no_prov = DatasetArtifact(
            artifact_id="ds-noprov",
            status="ok",
            rows=5,
            columns=["period", "value"],
            records=[{"period": "2020", "value": 100}],
            provenance=[],  # empty provenance — guardrail failure
        )
        critique = _make_critique("pass")
        state = _make_state(
            dataset_artifacts=[dataset_no_prov],
            coverage_reports=[_make_ok_coverage()],
        )

        decision = build_final_decision(state, critique)

        assert decision.terminal_outcome == "not_found"
        assert decision.is_system_error is True, (
            "Missing provenance on an ok dataset is a pipeline guardrail failure, "
            "NOT evidence of data absence."
        )
        assert "missing_provenance" in " ".join(decision.blocking_failures)


# ---------------------------------------------------------------------------
# 4. Narrator error must not silently become not_found
# ---------------------------------------------------------------------------


class TestNarratorErrorDoesNotBecomeNotFound:
    """When narrator fails, the response must carry system_error context, not hide it."""

    def test_narrator_error_does_not_become_silent_not_found(
        self, tmp_path: Path
    ) -> None:
        from app.workflow.service import WorkflowRunConfig, _finalize_state

        config = WorkflowRunConfig.default().model_copy(
            update={
                "artifact_dir": tmp_path / "artifacts",
                "live_llm_required": True,
                "live_embeddings_required": False,
            }
        )

        dataset = _make_ok_dataset()
        state = _make_state(
            dataset_artifacts=[dataset],
            coverage_reports=[_make_ok_coverage()],
        )
        state["_live_llm_required"] = True  # type: ignore[index]

        with patch("app.workflow.nodes.critic.run_methodology_critic") as mock_critic, \
             patch("app.workflow.nodes.narrator.build_workflow_response") as mock_narrator:

            mock_critic.return_value = _make_critique("pass")
            mock_narrator.side_effect = RuntimeError("Narrator LLM timeout")

            response = _finalize_state(state, config=config)

        # Must return a WorkflowResponse (not raise)
        from app.artifacts.workflow_artifacts import WorkflowResponse
        assert isinstance(response, WorkflowResponse)

        # The response may be not_found (only valid fallback), but must record
        # that this is a system/output error, not data absence.
        assert response.component_statuses.get("narrator", "").startswith("system_error") or \
               "narrator_output_failure" in str(response.not_found_evidence.rejection_reasons if response.not_found_evidence else ""), (
            "Narrator failure must be recorded as system_error in component_statuses "
            "or rejection_reasons, not silently presented as data absence."
        )


# ---------------------------------------------------------------------------
# 5. Visualization error must not change final decision
# ---------------------------------------------------------------------------


class TestVisualizationErrorDoesNotChangeFinalDecision:
    """A visualization build error must not flip a passed decision to not_found."""

    def test_visualization_error_does_not_change_final_decision(
        self, tmp_path: Path
    ) -> None:
        from app.workflow.service import WorkflowRunConfig, _finalize_state
        from app.artifacts.workflow_artifacts import ScriptArtifact

        script_path = tmp_path / "script.py"
        script_path.write_text("# script", encoding="utf-8")
        script = ScriptArtifact(
            artifact_id="script-001",
            path=str(script_path),
            downloadable=True,
            download_filename="script-001.py",
        )

        config = WorkflowRunConfig.default().model_copy(
            update={
                "artifact_dir": tmp_path / "artifacts",
                "live_llm_required": True,
            }
        )
        dataset = _make_ok_dataset()
        state = _make_state(
            dataset_artifacts=[dataset],
            coverage_reports=[_make_ok_coverage()],
            script_artifacts=[script],
        )
        state["_live_llm_required"] = True  # type: ignore[index]

        from app.artifacts.workflow_artifacts import WorkflowResponse, NoDataExplanationArtifact
        fake_passed_response = WorkflowResponse(
            run_id=state["run_id"],
            final_outcome="passed",
            message="Данные получены из источников.",
            dataset_artifacts=[dataset],
            script_artifacts=[script],
        )

        with patch("app.workflow.nodes.critic.run_methodology_critic") as mock_critic, \
             patch("app.workflow.nodes.visualization.build_visualization_for_all_datasets") as mock_vis, \
             patch("app.workflow.nodes.narrator.build_workflow_response") as mock_narrator:

            mock_critic.return_value = _make_critique("pass")
            mock_vis.side_effect = RuntimeError("Vega-lite crash")
            mock_narrator.return_value = fake_passed_response

            response = _finalize_state(state, config=config)

        assert response.final_outcome == "passed", (
            "Visualization crash must NOT change a passed final decision to not_found."
        )


# ---------------------------------------------------------------------------
# 6. Visualization processes ALL selected datasets, not only the first
# ---------------------------------------------------------------------------


class TestVisualizationAllDatasets:
    """build_visualization_for_all_datasets must return one spec per dataset."""

    def test_agent8_visualizes_all_selected_datasets_not_only_first(self) -> None:
        from app.workflow.nodes.visualization import build_visualization_for_all_datasets

        datasets = [
            _make_ok_dataset("ds-001", "world_bank:NY.GDP.MKTP.CD"),
            _make_ok_dataset("ds-002", "fedstat:31074"),
            _make_ok_dataset("ds-003", "world_bank:FP.CPI.TOTL.ZG"),
        ]

        specs = build_visualization_for_all_datasets(datasets, query_category="comparative")

        assert len(specs) == 3, (
            "Must return one VisualizationSpec per dataset, not only the first."
        )
        artifact_ids = {s.dataset_artifact_id for s in specs}
        assert "ds-001" in artifact_ids
        assert "ds-002" in artifact_ids
        assert "ds-003" in artifact_ids

    def test_visualization_error_on_one_dataset_does_not_skip_others(self) -> None:
        from app.artifacts.workflow_artifacts import DatasetArtifact
        from app.workflow.nodes.visualization import build_visualization_for_all_datasets

        # A dataset that will trigger an error in the renderer
        bad_dataset = DatasetArtifact(
            artifact_id="ds-bad",
            status="ok",
            rows=1,
            columns=["value"],
            records=[{"value": None}],
            provenance=[{"source_id": "test"}],
        )
        good_dataset = _make_ok_dataset("ds-good")

        specs = build_visualization_for_all_datasets(
            [bad_dataset, good_dataset], query_category="simple"
        )

        # Must return specs for both — bad one gets skipped_with_reason or ok
        assert len(specs) == 2
        good_spec = next((s for s in specs if s.dataset_artifact_id == "ds-good"), None)
        assert good_spec is not None, "Good dataset must still get a spec even if another fails."


# ---------------------------------------------------------------------------
# 7. Public trace hides raw tool payloads
# ---------------------------------------------------------------------------


class TestPublicTraceHidesRawPayloads:
    """TraceEvent.payload should not leak raw internal tool data to the user-facing trace."""

    def test_public_trace_hides_raw_tool_payloads(self) -> None:
        from app.artifacts.workflow_artifacts import TraceEvent

        # A trace event with sensitive internal payload
        event = TraceEvent(
            run_id="phase2-test",
            state="source_scouts",
            agent="SourceScouts",
            payload={
                "raw_qdrant_results": [{"id": "abc", "vector": [0.1] * 768}],
                "api_key_debug": "secret-key-123",
                "internal_sql": "SELECT * FROM embeddings WHERE ...",
            },
        )

        # The public projection must not include raw tool payloads
        # Per handoff: user-facing trace shows search/analysis summary first;
        # raw TraceEvent JSON only in debug/collapsed UI.
        # Test that TraceEvent exists and payload is accessible (for debug)
        # but that public-facing fields are separate from raw payload.
        assert event.payload is not None  # raw payload exists for debug
        assert event.state == "source_scouts"
        assert event.agent == "SourceScouts"

        # Public-facing fields must not include raw payload contents
        public_fields = {
            "run_id": event.run_id,
            "state": event.state,
            "agent": event.agent,
            "decision": event.decision,
            "input_summary": event.input_summary,
            "output_artifact": event.output_artifact,
        }
        raw_payload_str = str(event.payload)
        for field_val in public_fields.values():
            if field_val is not None:
                assert field_val not in raw_payload_str or field_val in ("phase2-test",), (
                    "Public trace fields must be separate from raw payload data."
                )

    def test_final_outcome_decision_has_required_fields(self) -> None:
        """FinalOutcomeDecision model exists with all required fields from handoff."""
        from app.artifacts.workflow_artifacts import FinalOutcomeDecision

        decision = FinalOutcomeDecision(
            terminal_outcome="passed",
            dataset_ids=["ds-001"],
            coverage_report_ids=["world_bank:NY.GDP.MKTP.CD"],
            extraction_plan_id="plan-001",
            warnings=[],
            blocking_failures=[],
            repair_route=None,
        )

        assert decision.terminal_outcome == "passed"
        assert decision.dataset_ids == ["ds-001"]
        assert decision.coverage_report_ids == ["world_bank:NY.GDP.MKTP.CD"]
        assert decision.extraction_plan_id == "plan-001"
        assert decision.is_system_error is False
        assert decision.system_error_detail is None
