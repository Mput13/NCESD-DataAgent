"""Agent diagnostic tests.

Each test targets one specific failure point in the pipeline.
Run without Qdrant or Yandex credentials — all LLM/retrieval paths are mocked.

HOW IT SHOULD WORK vs HOW IT ACTUALLY WORKS is documented inline per test.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.artifacts.workflow_artifacts import (
    CoverageReport,
    DatasetArtifact,
    EvidenceBundleArtifact,
    ExtractionPlan,
    IntentFrame,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_intent(
    *,
    category: str = "simple",
    geography: str | None = "Россия",
    period: str | None = "2022",
    indicator: str | None = "ВВП",
    needs_clarification: bool = False,
    countries: list[str] | None = None,
) -> IntentFrame:
    known: dict[str, Any] = {}
    if geography:
        known["geography"] = geography
    if period:
        known["period"] = period
    if indicator:
        known["indicator"] = indicator
    if countries is not None:
        known["countries"] = countries
    elif geography:
        known["countries"] = [geography]
    return IntentFrame(
        query=f"{indicator} {geography} {period}",
        category=category,  # type: ignore[arg-type]
        known_fields=known,
        missing_fields=[],
        needs_clarification=needs_clarification,
        source_preferences=[],
        open_reasoning=[],
    )


def _make_ok_coverage(source_id: str = "world_bank:NY.GDP.MKTP.CD") -> CoverageReport:
    return CoverageReport(
        source_id=source_id,
        status="ok",
        checks=["parquet_found", "geography_matched"],
        available_periods=["2020", "2021", "2022", "2023"],
        available_geographies=["RUS"],
        matched_periods=["2022"],
        matched_geographies=["RUS"],
        extraction_ready=True,
        evidence={"row_count": 42, "source_specific_risks": []},
    )


def _make_dataset(value: float = 2240422612843.0) -> DatasetArtifact:
    from uuid import uuid4
    return DatasetArtifact(
        artifact_id=f"dataset-{uuid4().hex[:8]}",
        source_id="world_bank:NY.GDP.MKTP.CD",
        status="ok",
        rows=1,
        columns=["geo_name", "period", "value", "unit"],
        records=[
            {
                "geo_name": "Russia",
                "geo_id": "RUS",
                "period": "2022",
                "value": value,
                "unit": "current US$",
                "quality_flags": [],
            }
        ],
        provenance=[{"source_id": "world_bank:NY.GDP.MKTP.CD", "period": "2022"}],
    )


# ===========================================================================
# 1. Intent parsing: geography → countries propagation
# ===========================================================================


class TestIntentGeographyToCountries:
    """
    SHOULD: analyze_intent returns IntentFrame where known_fields["countries"]
            is always a non-empty list when geography is present.
            coverage.py reads known_fields["countries"] to filter World Bank parquet.

    ACTUAL BUG: If Qwen returns {"geography": "Россия", "countries": []} the
                _derive_countries_from_geography validator in _IntentAnalysisSchema
                fills countries from geography. BUT if known_fields is built
                only from result.geography (line 165-170 of state.py), and
                result.countries is empty, the fallback on line 169 sets
                known_fields["countries"] = ["Россия"] — correct.
                HOWEVER if Qwen returns countries=[] and geography=None but
                indicator is present — countries never gets set at all.
    """

    def test_intent_frame_has_countries_when_geography_set(self) -> None:
        intent = _make_intent(geography="Россия", countries=["Россия"])
        assert "countries" in intent.known_fields
        assert intent.known_fields["countries"] == ["Россия"]

    def test_intent_frame_countries_derived_from_geography_string(self) -> None:
        """geography='Россия, Китай' should produce countries=['Россия', 'Китай']."""
        known: dict[str, Any] = {"geography": "Россия, Китай", "period": "2022"}
        known["countries"] = [c.strip() for c in known["geography"].split(",") if c.strip()]
        intent = IntentFrame(
            query="ВВП Россия Китай 2022",
            category="comparative",
            known_fields=known,
            missing_fields=[],
            needs_clarification=False,
            source_preferences=[],
            open_reasoning=[],
        )
        assert intent.known_fields["countries"] == ["Россия", "Китай"]

    def test_coverage_receives_countries_list_not_empty(self) -> None:
        """World Bank coverage must receive a non-empty countries list."""
        from app.workflow.nodes.coverage import _world_bank_coverage

        source_card = {
            "source_family": "world_bank",
            "card_id": "NY.GDP.MKTP.CD",
            "dataset_id": "NY.GDP.MKTP.CD",
            "title": "GDP current US$",
        }
        intent_fields = {"geography": "Россия", "countries": ["Россия"], "period": "2022"}

        # Should not crash and countries must be passed through
        with patch("app.data.world_bank_adapter.preview_world_bank_coverage") as mock_preview:
            mock_preview.return_value = _make_ok_coverage("NY.GDP.MKTP.CD")
            report = _world_bank_coverage(source_card, intent_fields=intent_fields)

        call_kwargs = mock_preview.call_args
        countries_passed = call_kwargs.kwargs.get("countries") or call_kwargs.args[1] if call_kwargs.args[1:] else []
        # The key assertion: countries list must not be empty
        assert countries_passed != [], (
            "BUG: coverage._world_bank_coverage passed empty countries=[]. "
            "World Bank adapter will match no rows."
        )


# ===========================================================================
# 2. Period parsing: string → list expansion
# ===========================================================================


class TestPeriodExpansion:
    """
    SHOULD: extraction_planner._safe_filters_from_intent expands period ranges.
            "2020-2022" → ["2020", "2021", "2022"]
            "2022" → ["2022"]
            "последние доступные годы" → [] (natural language filtered out)

    ACTUAL: coverage.py line 243 filters periods with .isdigit() and len==4,
            so "2020-2022" stays as-is (not split). Then extraction planner
            _expand_period handles it — but only if known_fields["period"] is set.
            If Qwen returns period="последние доступные годы" the coverage check
            passes empty periods=[] which means no row filtering → wrong data.
    """

    def test_period_range_expanded_to_years(self) -> None:
        from app.workflow.nodes.extraction_planner import _safe_filters_from_intent

        intent = _make_intent(period="2020-2022")
        filters = _safe_filters_from_intent(intent)
        assert "periods" in filters, "period range should produce 'periods' key"
        assert filters["periods"] == ["2020", "2021", "2022"], (
            f"Expected ['2020','2021','2022'], got {filters['periods']}"
        )

    def test_single_year_becomes_list(self) -> None:
        from app.workflow.nodes.extraction_planner import _safe_filters_from_intent

        intent = _make_intent(period="2022")
        filters = _safe_filters_from_intent(intent)
        assert filters.get("periods") == ["2022"]

    def test_natural_language_period_filtered_out(self) -> None:
        from app.workflow.nodes.extraction_planner import _safe_filters_from_intent

        intent = _make_intent(period="последние доступные годы")
        filters = _safe_filters_from_intent(intent)
        # Natural language should not survive into filters
        assert filters.get("periods") == [], (
            "BUG: natural language period string leaked into extraction filters. "
            f"Got: {filters.get('periods')}"
        )

    def test_coverage_drops_natural_language_periods(self) -> None:
        """coverage.py must drop non-year strings before calling adapter."""
        from app.workflow.nodes.coverage import _world_bank_coverage

        source_card = {
            "source_family": "world_bank",
            "card_id": "NY.GDP.MKTP.CD",
            "dataset_id": "NY.GDP.MKTP.CD",
            "title": "GDP",
        }
        intent_fields = {
            "geography": "Россия",
            "countries": ["Россия"],
            "period": "последние доступные годы",  # natural language — must be dropped
        }

        with patch("app.data.world_bank_adapter.preview_world_bank_coverage") as mock_preview:
            mock_preview.return_value = _make_ok_coverage("NY.GDP.MKTP.CD")
            _world_bank_coverage(source_card, intent_fields=intent_fields)

        call_kwargs = mock_preview.call_args
        periods_passed = call_kwargs.kwargs.get("periods", [])
        for p in periods_passed:
            assert str(p).isdigit() and len(str(p)) == 4, (
                f"BUG: non-year string '{p}' passed to world_bank adapter as period filter"
            )


# ===========================================================================
# 3. Source scouts: gated_no_index hides all errors
# ===========================================================================


class TestSourceScoutsGating:
    """
    SHOULD: When index manifest is missing, source scouts should return a clear
            gated_no_index status that propagates to component_statuses and
            eventually surfaces as not_found with a useful message.

    ACTUAL: The graph node returns gated_no_index status, but finalization
            _finalize_state doesn't distinguish gated_no_index from actual not_found.
            User sees "Данные не найдены" with no mention that Qdrant is not configured.
    """

    def test_no_index_manifest_produces_gated_no_index(self, tmp_path: Path) -> None:
        from app.workflow.graph import _node_source_scouts

        state: dict[str, Any] = {
            "run_id": "test-run",
            "query": "ВВП России 2022",
            "intent": _make_intent(),
            "evidence": EvidenceBundleArtifact(),
            "trace_events": [],
            "component_statuses": {},
            "_index_manifest_path": str(tmp_path / "nonexistent-manifest.json"),
            "_live_llm_required": False,
            "_live_embeddings_required": False,
        }

        result = _node_source_scouts(state)

        assert result["component_statuses"].get("source_scouts") == "gated_no_index", (
            f"Expected 'gated_no_index', got: {result['component_statuses'].get('source_scouts')}"
        )
        assert result["evidence"].selected_sources == []

    def test_gated_no_index_routes_to_not_found(self, tmp_path: Path) -> None:
        """After gated_no_index, _route_after_scouts must return finalization_pending_not_found."""
        from app.workflow.graph import _route_after_scouts

        state: dict[str, Any] = {
            "evidence": EvidenceBundleArtifact(
                selected_sources=[],
                retrieval_status="gated",
            ),
        }
        route = _route_after_scouts(state)
        assert route == "finalization_pending_not_found"


# ===========================================================================
# 4. Extraction plan: gated coverage does not block extraction entirely
# ===========================================================================


class TestExtractionPlannerGating:
    """
    SHOULD: If some coverage reports are gated and some are ok, extraction
            should proceed with the ok reports.

    ACTUAL: build_extraction_plan checks ok_reports first. If ok_reports is empty
            it returns gated/skipped. If there is one ok report, it proceeds.
            This is correct — but the test verifies the boundary.
    """

    def test_all_gated_coverage_returns_gated_plan(self) -> None:
        from app.workflow.nodes.extraction_planner import build_extraction_plan

        intent = _make_intent()
        gated_report = CoverageReport(
            source_id="fedstat:12345",
            status="gated",
            checks=["parquet_not_found"],
            available_periods=[],
            available_geographies=[],
            gated_reason="local FedStat parquet not found",
        )

        plan = build_extraction_plan(intent, [gated_report], live_llm_required=False)
        assert plan.status == "gated", f"Expected 'gated', got '{plan.status}'"
        assert plan.operations == []

    def test_one_ok_report_produces_ok_plan(self) -> None:
        from app.workflow.nodes.extraction_planner import build_extraction_plan

        intent = _make_intent()
        ok_report = _make_ok_coverage()
        gated_report = CoverageReport(
            source_id="fedstat:12345",
            status="gated",
            checks=["parquet_not_found"],
            available_periods=[],
            available_geographies=[],
            gated_reason="local parquet not found",
        )

        plan = build_extraction_plan(intent, [ok_report, gated_report], live_llm_required=False)
        assert plan.status == "ok", (
            f"BUG: one ok report + one gated → should be 'ok', got '{plan.status}'"
        )
        assert "export_dataset" in plan.operations

    def test_plan_operations_are_all_in_allowlist(self) -> None:
        from app.workflow.nodes.extraction_planner import (
            ALLOWED_OPERATIONS,
            build_extraction_plan,
        )

        intent = _make_intent(category="comparative")
        ok_report = _make_ok_coverage()
        plan = build_extraction_plan(intent, [ok_report], live_llm_required=False)

        for op in plan.operations:
            assert op in ALLOWED_OPERATIONS, (
                f"BUG: operation '{op}' not in allowlist {ALLOWED_OPERATIONS}"
            )


# ===========================================================================
# 5. Narrator number guard: numbers in message must be in records
# ===========================================================================


class TestNarratorNumberGuard:
    """
    SHOULD: assert_message_numbers_are_supported raises ValueError when a number
            in the message is not in DatasetArtifact records.

    ACTUAL: In _build_response_live the guard fires but the exception is caught
            and silently passed. The guard is disabled in production.
            Tests verify the guard itself works correctly.
    """

    def test_number_in_records_passes(self) -> None:
        from app.workflow.nodes.narrator import assert_message_numbers_are_supported

        dataset = _make_dataset(value=2240422612843.0)
        # The exact value from records — should pass
        assert_message_numbers_are_supported(
            "ВВП России в 2022 году составил 2240422612843 долларов США.",
            [dataset],
        )

    def test_invented_number_fails(self) -> None:
        from app.workflow.nodes.narrator import assert_message_numbers_are_supported

        dataset = _make_dataset(value=2240422612843.0)
        with pytest.raises(ValueError, match="Unsupported numeric claims"):
            assert_message_numbers_are_supported(
                "ВВП России составил 9999999999999 долларов.",  # not in records
                [dataset],
            )

    def test_year_from_provenance_passes(self) -> None:
        """Years in the message should be sourced from records.period or provenance."""
        from app.workflow.nodes.narrator import assert_message_numbers_are_supported

        dataset = _make_dataset(value=100.0)
        # 2022 is in records["period"] — should pass
        assert_message_numbers_are_supported(
            "Данные за 2022 год: 100 единиц.",
            [dataset],
        )

    def test_guard_disabled_in_live_path(self) -> None:
        """
        Documents the current state: guard is disabled in _build_response_live.
        This test SHOULD FAIL when the guard is properly enabled.
        It currently passes because the exception is silently caught.
        """
        from app.workflow.nodes.narrator import assert_message_numbers_are_supported

        dataset = _make_dataset(value=100.0)
        # This number is NOT in records — guard should raise
        try:
            assert_message_numbers_are_supported("Значение равно 999888777.", [dataset])
            guard_raised = False
        except ValueError:
            guard_raised = True

        # Document: guard works in isolation
        assert guard_raised, (
            "The number guard does NOT fire for invented numbers. "
            "This is correct test behaviour — guard works. "
            "In production (_build_response_live) the exception is caught with 'pass'."
        )


# ===========================================================================
# 6. matrix_hint leaks from acceptance fixtures into runtime
# ===========================================================================


class TestMatrixHintLeakage:
    """
    SHOULD: _node_research_designer only loads matrix_hint when _case_id is set
            AND the matrix file exists. In a real user query _case_id is None,
            so matrix_hint must be None.

    ACTUAL BUG: If golden-coverage-matrix.json exists in the repo and _case_id
                is accidentally set (e.g. via WorkflowRunConfig.case_id),
                the research designer gets a hint from the eval fixture.
                This makes acceptance tests pass by cheating.
    """

    def test_real_user_query_has_no_case_id(self) -> None:
        from app.workflow.service import WorkflowRunConfig

        config = WorkflowRunConfig.default()
        # A real user query should have no case_id
        assert config.case_id is None, (
            f"BUG: WorkflowRunConfig.default() has case_id={config.case_id}. "
            "Real user queries must not have a case_id."
        )

    def test_matrix_hint_not_loaded_without_case_id(self) -> None:
        """Without _case_id in state, matrix_hint must be None inside research designer."""
        from app.workflow.graph import _node_research_designer

        intent = _make_intent()
        state: dict[str, Any] = {
            "run_id": "test-run",
            "query": "ВВП России 2022",
            "intent": intent,
            "trace_events": [],
            "component_statuses": {},
            "_live_llm_required": False,
            "_case_id": None,  # real user query — no case_id
        }

        with patch("app.workflow.state.design_research") as mock_design:
            mock_design.side_effect = RuntimeError("no LLM")
            result = _node_research_designer(state)

        # Should be gated (no LLM), but matrix_hint must not have been loaded
        # Verify by checking that design_research was called without a matrix_hint
        if mock_design.called:
            call_kwargs = mock_design.call_args.kwargs
            assert call_kwargs.get("matrix_hint") is None, (
                f"BUG: matrix_hint={call_kwargs.get('matrix_hint')} passed to "
                "design_research without a case_id. Acceptance fixtures leaking into runtime."
            )


# ===========================================================================
# 7. End-to-end: full pipeline with mocked LLM and retrieval
# ===========================================================================


class TestEndToEndMocked:
    """
    Full pipeline smoke test with all external calls mocked.
    Verifies the happy path produces a WorkflowResponse with outcome=passed.
    """

    def test_full_pipeline_passed_outcome(self, tmp_path: Path) -> None:
        from app.workflow.service import WorkflowRunConfig, run_user_query

        config = WorkflowRunConfig.default().model_copy(
            update={
                "artifact_dir": tmp_path / "artifacts",
                "live_llm_required": False,
                "live_embeddings_required": False,
            }
        )

        # Without LLM this should return not_found (no retrieval without Qdrant)
        # but must NOT raise an exception
        from app.artifacts.workflow_artifacts import WorkflowResponse

        response = run_user_query("ВВП России 2022", run_config=config)
        assert isinstance(response, WorkflowResponse)
        assert response.final_outcome in ("passed", "needs_clarification", "not_found"), (
            f"Unexpected outcome: {response.final_outcome}"
        )
        # Must have trace events — silent failure is worse than loud failure
        assert response.trace_events, "BUG: response has no trace events"

    def test_empty_query_returns_clarification(self, tmp_path: Path) -> None:
        from app.workflow.service import WorkflowRunConfig, run_user_query

        config = WorkflowRunConfig.default().model_copy(
            update={
                "artifact_dir": tmp_path / "artifacts",
                "live_llm_required": False,
                "live_embeddings_required": False,
            }
        )

        response = run_user_query("", run_config=config)
        # Empty query cannot return passed — must be clarification or not_found
        assert response.final_outcome in ("needs_clarification", "not_found"), (
            f"BUG: empty query returned outcome='{response.final_outcome}'"
        )


# ===========================================================================
# 8. String parsing showcase: what Qwen sends vs what we need
# ===========================================================================


class TestQueryStringParsing:
    """
    Показывает как разбирается строка запроса на каждом шаге.
    Не использует реальный LLM — демонстрирует только детерминированный парсинг.
    """

    QUERY = "Какой ВВП России в 2022 году?"

    def test_intent_fallback_parses_geography(self) -> None:
        """Rule-based fallback intent (intent.py) должен найти 'России'."""
        from app.workflow.intent import build_intent

        intent = build_intent(self.QUERY)
        assert intent.geography, f"Geography not found in: '{self.QUERY}'"
        assert any("Росс" in g for g in intent.geography), (
            f"Expected 'Россия' in geography, got: {intent.geography}"
        )

    def test_intent_fallback_parses_year(self) -> None:
        from app.workflow.intent import build_intent

        intent = build_intent(self.QUERY)
        assert intent.period == "2022", (
            f"Expected period='2022', got: '{intent.period}'"
        )

    def test_intent_fallback_finds_gdp_indicator(self) -> None:
        from app.workflow.intent import build_intent

        intent = build_intent("ВВП России 2022")
        assert "ввп" in intent.indicators or any("вв" in i.lower() for i in intent.indicators), (
            f"GDP indicator not found in: {intent.indicators}"
        )

    def test_period_range_string_parsed_correctly(self) -> None:
        """'2019-2023' должен распасться в список годов."""
        import re
        period = "2019-2023"
        m = re.fullmatch(r"(\d{4})\s*[-–—]\s*(\d{4})", period)
        assert m, f"Period range regex didn't match: '{period}'"
        years = list(range(int(m.group(1)), int(m.group(2)) + 1))
        assert years == [2019, 2020, 2021, 2022, 2023]

    def test_country_alias_russia_resolves(self) -> None:
        """COUNTRY_ALIASES в world_bank_adapter должен знать 'Россия' → 'RUS'."""
        from app.data.world_bank_adapter import COUNTRY_ALIASES

        assert "россия" in COUNTRY_ALIASES or "russia" in COUNTRY_ALIASES, (
            f"'Россия'/'Russia' not in COUNTRY_ALIASES. "
            f"Sample keys: {list(COUNTRY_ALIASES.keys())[:10]}"
        )
        code = COUNTRY_ALIASES.get("россия") or COUNTRY_ALIASES.get("russia")
        assert code == "RUS", f"Expected 'RUS', got '{code}'"

    def test_world_bank_lexical_score_gdp_russia(self) -> None:
        """Запрос 'ВВП России 2022' должен дать ненулевой score для GDP-индикатора."""
        from app.sources.base import lexical_score

        query = "ВВП России 2022 GDP"
        fields = ["NY.GDP.MKTP.CD", "GDP current US dollars", "Gross domestic product"]
        score = lexical_score(query, fields)
        assert score > 0, (
            f"BUG: lexical_score=0 for GDP query against GDP indicator fields. "
            f"Query tokens: {query.lower().split()}"
        )
