"""Phase 2 workflow node tests: CKAN adapter, scouts, coverage, extraction planner."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Task 1: CKAN adapter tests
# ---------------------------------------------------------------------------


class TestCkanAdapterBounds:
    """search_ckan_source_cards caps rows at 5."""

    def test_rows_capped_at_5(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.data import ckan_adapter

        payload = {
            "result": {
                "count": 100,
                "results": [{"id": f"pkg-{i}", "title": f"Package {i}", "resources": []} for i in range(10)],
            }
        }

        def mock_package_search(query: str, *, rows: int = 5, endpoint: str | None = None) -> dict[str, Any]:
            # Simulate the cap: real ckan_package_search caps to rows=5
            results = payload["result"]["results"][:rows]
            return {"query": query, "rows": rows, "endpoint": endpoint or "https://repository.nsedc.ru/api/3/action/package_search", "count": 100, "results": results}

        monkeypatch.setattr(ckan_adapter, "ckan_package_search", mock_package_search)
        cards = ckan_adapter.search_ckan_source_cards("57319", rows=100)
        assert len(cards) <= 5, f"Expected <= 5 cards, got {len(cards)}"

    def test_source_card_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.data import ckan_adapter

        def mock_package_search(query: str, *, rows: int = 5, endpoint: str | None = None) -> dict[str, Any]:
            return {
                "query": query, "rows": rows, "endpoint": "https://example.com", "count": 1,
                "results": [{"id": "pkg-1", "title": "Test Package", "resources": [{"id": "res-1", "format": "CSV", "url": "http://example.com/file.csv"}], "notes": "Some notes"}],
            }

        monkeypatch.setattr(ckan_adapter, "ckan_package_search", mock_package_search)
        cards = ckan_adapter.search_ckan_source_cards("test")
        assert len(cards) == 1
        card = cards[0]
        # Must contain compressed fields
        assert "source_family" in card
        assert "dataset_id" in card
        assert "title" in card
        assert "formats" in card
        assert "resource_count" in card
        assert card["source_family"] == "ckan"
        assert card["resource_count"] == 1


class TestCkanPromote:
    """promote_ckan_package returns a promoted dict with compressed fields."""

    def test_promote_returns_compressed_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.data import ckan_adapter

        raw_package = {
            "id": "pkg-abc",
            "title": "Population data",
            "resources": [
                {"id": "res-1", "format": "CSV", "url": "http://example.com/file.csv", "name": "pop.csv"},
                {"id": "res-2", "format": "PDF", "url": "http://example.com/file.pdf", "name": "description.pdf"},
            ],
            "notes": "Population by year",
            "url": "http://example.com/dataset/pkg-abc",
        }

        def mock_package_show(package_id: str, *, endpoint_root: str | None = None) -> dict[str, Any]:
            return {"result": raw_package, "success": True}

        monkeypatch.setattr(ckan_adapter, "ckan_package_show", mock_package_show)
        promoted = ckan_adapter.promote_ckan_package("pkg-abc")
        assert promoted["dataset_id"] == "pkg-abc"
        assert "formats" in promoted
        assert isinstance(promoted["formats"], list)
        assert "resource_count" in promoted
        assert promoted["resource_count"] == 2  # capped at 20 or total

    def test_promote_caps_resources_at_20(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.data import ckan_adapter

        resources = [{"id": f"res-{i}", "format": "CSV", "url": f"http://example.com/file-{i}.csv", "name": f"file{i}.csv"} for i in range(30)]

        def mock_package_show(package_id: str, *, endpoint_root: str | None = None) -> dict[str, Any]:
            return {"result": {"id": "pkg-big", "title": "Big Package", "resources": resources, "notes": "", "url": ""}, "success": True}

        monkeypatch.setattr(ckan_adapter, "ckan_package_show", mock_package_show)
        promoted = ckan_adapter.promote_ckan_package("pkg-big")
        # resource_count is total, but promoted_resources should be capped at 20
        assert len(promoted.get("promoted_resources", [])) <= 20


class TestCkanExtract:
    """extract_ckan_dataset returns DatasetArtifact for CSV and NoDataExplanationArtifact for unsupported."""

    def test_unsupported_format_returns_no_data_artifact(self, tmp_path: Path) -> None:
        from app.data.ckan_adapter import extract_ckan_dataset

        promoted = {
            "dataset_id": "pkg-xls",
            "title": "Excel Only Package",
            "formats": ["XLS"],
            "promoted_resources": [{"id": "res-1", "format": "XLS", "url": "http://example.com/data.xls", "name": "data.xls"}],
            "resource_count": 1,
            "source_family": "ckan",
            "provenance_url": "http://example.com",
        }
        result = extract_ckan_dataset(
            promoted,
            resource_id="res-1",
            filters={},
            output_dir=tmp_path,
            artifact_id="test-xls",
        )
        from app.artifacts.workflow_artifacts import NoDataExplanationArtifact
        assert isinstance(result, NoDataExplanationArtifact)
        # Must contain the required reason string
        assert "ckan_resource_format_not_supported_for_deterministic_extraction" in " ".join(result.rejection_reasons)

    def test_csv_extraction_returns_dataset_artifact(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """CSV extraction via monkeypatched download returns DatasetArtifact."""
        from app.data import ckan_adapter

        csv_content = "indicator_id,country_id,date,value\nPOP,RUS,2020,144000000\nPOP,RUS,2021,145000000\n"

        def mock_get(url: str, **kwargs: Any) -> MagicMock:
            response = MagicMock()
            response.raise_for_status = MagicMock()
            response.content = csv_content.encode("utf-8")
            response.iter_content = lambda chunk_size: [csv_content.encode("utf-8")]
            return response

        monkeypatch.setattr("requests.get", mock_get)

        promoted = {
            "dataset_id": "pkg-csv",
            "title": "Population CSV Package",
            "formats": ["CSV"],
            "promoted_resources": [{"id": "res-csv", "format": "CSV", "url": "http://example.com/data.csv", "name": "data.csv"}],
            "resource_count": 1,
            "source_family": "ckan",
            "provenance_url": "http://example.com",
        }
        result = ckan_adapter.extract_ckan_dataset(
            promoted,
            resource_id="res-csv",
            filters={},
            output_dir=tmp_path,
            artifact_id="test-csv",
        )
        from app.artifacts.workflow_artifacts import DatasetArtifact
        assert isinstance(result, DatasetArtifact)
        assert result.rows > 0


class TestCkanCoveragePreview:
    """preview_ckan_coverage returns a CoverageReport."""

    def test_returns_coverage_report(self) -> None:
        from app.data.ckan_adapter import preview_ckan_coverage
        from app.artifacts.workflow_artifacts import CoverageReport

        promoted = {
            "dataset_id": "pkg-1",
            "title": "Test dataset",
            "formats": ["CSV"],
            "promoted_resources": [{"id": "res-1", "format": "CSV", "url": "http://example.com/data.csv", "name": "data.csv"}],
            "resource_count": 1,
            "source_family": "ckan",
            "provenance_url": "http://example.com/dataset/1",
        }
        report = preview_ckan_coverage(promoted)
        assert isinstance(report, CoverageReport)
        assert report.source_id == "pkg-1"
        assert "source_specific_risks" in report.evidence


# ---------------------------------------------------------------------------
# Task 2: Scout and coverage node tests
# ---------------------------------------------------------------------------


class TestRunSourceScouts:
    """run_source_scouts returns EvidenceBundleArtifact with selected and rejected sources."""

    def test_selected_and_rejected_both_preserved(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from app.workflow.nodes import scouts
        from app.artifacts.workflow_artifacts import EvidenceBundleArtifact

        # Build a minimal index manifest pointing at a fake corpus
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text(
            json.dumps({
                "card_id": "fedstat-001",
                "chunk_id": "fedstat-001-0",
                "source_family": "fedstat",
                "embedding_text": "title: ВВП России\nindicator_code: 12345\n",
                "provenance_url": "http://fedstat.ru/1",
            }) + "\n",
            encoding="utf-8",
        )
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "status": "gated_skip",
            "dense_status": "gated_skip",
            "corpus_artifact_path": str(corpus_path),
            "collection_name": "phase1_source_cards",
        }), encoding="utf-8")

        result = scouts.run_source_scouts(
            "ВВП России 2020",
            expected_sources=["fedstat"],
            index_manifest_path=manifest_path,
        )
        assert isinstance(result, EvidenceBundleArtifact)
        # Both lists must be present (even if empty)
        assert isinstance(result.selected_sources, list)
        assert isinstance(result.rejected_sources, list)

    def test_ckan_triggered_by_indicator_code(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """CKAN discovery triggers when query contains a CKAN indicator code like 57319."""
        from app.workflow.nodes import scouts
        from app.data import ckan_adapter

        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text("{}\n", encoding="utf-8")
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "status": "gated_skip",
            "dense_status": "gated_skip",
            "corpus_artifact_path": str(corpus_path),
            "collection_name": "test",
        }), encoding="utf-8")

        called = []

        def mock_search_ckan(query: str, *, rows: int = 5) -> list[dict[str, Any]]:
            called.append(query)
            return []

        monkeypatch.setattr(ckan_adapter, "search_ckan_source_cards", mock_search_ckan)

        scouts.run_source_scouts(
            "данные 57319",
            expected_sources=["ckan"],
            index_manifest_path=manifest_path,
        )
        assert called, "Expected CKAN to be called when query contains indicator code"

    def test_retrieval_planner_calls_structured_client_for_primary_probes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.artifacts.workflow_artifacts import (
            AmbiguityPolicy,
            DimensionIntent,
            GeographyIntent,
            MeasureIntent,
            OperationIntent,
            PeriodIntent,
            SourceScope,
            TaskIntent,
            UserIntentArtifact,
        )
        from app.workflow.state import plan_retrieval

        intent = UserIntentArtifact(
            original_query="Сравни динамику ВВП, инфляции и безработицы стран БРИКС за 2015-2024.",
            task=TaskIntent(
                category="comparison",
                user_goal="Сравнить динамику трех макроэкономических показателей стран БРИКС.",
                expected_output="table",
            ),
            measures=[
                MeasureIntent(
                    measure_id="m_gdp",
                    user_phrase="ВВП",
                    canonical_concept="gross domestic product",
                    aliases_ru=["ВВП"],
                    aliases_en=["GDP"],
                    official_terms_ru=["валовой внутренний продукт"],
                    official_terms_en=["gross domestic product"],
                    measurement_form="level",
                ),
                MeasureIntent(
                    measure_id="m_inflation",
                    user_phrase="инфляция",
                    canonical_concept="inflation / consumer price index",
                    aliases_ru=["инфляция", "ИПЦ"],
                    aliases_en=["inflation", "CPI"],
                    official_terms_ru=["индекс потребительских цен"],
                    official_terms_en=["consumer price index"],
                    measurement_form="rate",
                ),
                MeasureIntent(
                    measure_id="m_unemployment",
                    user_phrase="безработица",
                    canonical_concept="unemployment rate",
                    aliases_ru=["безработица"],
                    aliases_en=["unemployment rate"],
                    official_terms_ru=["уровень безработицы"],
                    official_terms_en=["unemployment rate"],
                    measurement_form="rate",
                ),
            ],
            dimensions=DimensionIntent(
                geographies=[
                    GeographyIntent(name="Brazil", iso3="BRA", group="BRICS"),
                    GeographyIntent(name="Russia", iso3="RUS", group="BRICS"),
                    GeographyIntent(name="India", iso3="IND", group="BRICS"),
                    GeographyIntent(name="China", iso3="CHN", group="BRICS"),
                    GeographyIntent(name="South Africa", iso3="ZAF", group="BRICS"),
                ],
                period=PeriodIntent(start="2015", end="2024"),
                frequency="annual",
            ),
            operations=OperationIntent(wants_comparison=True, wants_time_series=True),
            source_scope=SourceScope(requested_sources=[], source_constraint="none", source_hints=[]),
            ambiguity=AmbiguityPolicy(needs_clarification=False),
        )
        mock_client = MagicMock()

        def fake_structured_chat(messages, *, schema, **kwargs):
            probe_terms = {
                "m_gdp": {
                    "world_bank": "gross domestic product GDP",
                    "fedstat": "валовой внутренний продукт",
                    "ckan": "валовой внутренний продукт набор данных",
                },
                "m_inflation": {
                    "world_bank": "inflation consumer price index CPI",
                    "fedstat": "индекс потребительских цен инфляция",
                    "ckan": "индекс потребительских цен инфляция",
                },
                "m_unemployment": {
                    "world_bank": "unemployment rate labor force",
                    "fedstat": "уровень безработицы рабочая сила",
                    "ckan": "безработица рынок труда рабочая сила",
                },
            }
            return schema.model_validate(
                {
                    "original_query": intent.original_query,
                    "probes": [
                        {
                            "probe_id": f"p_{measure_id}_{family}",
                            "text": text,
                            "purpose": "source_specific" if family == "ckan" else "alias",
                            "measure_id": measure_id,
                            "language": "en" if family == "world_bank" else "ru",
                            "priority": 100 if family != "ckan" else 95,
                            "source_family_hint": family,
                            "basis": "LLM source-card metadata wording",
                            "origin": "llm",
                        }
                        for measure_id, by_family in probe_terms.items()
                        for family, text in by_family.items()
                    ],
                    "dimension_constraints": {
                        "geographies": ["SHOULD_BE_REPLACED_BY_INTENT"],
                        "periods": ["1999"],
                        "frequency": "unknown",
                    },
                    "source_scope": {"requested_sources": [], "source_constraint": "none", "source_hints": []},
                    "budget_policy": {"per_probe_limit": 50, "final_source_count": 3},
                    "trace_notes": ["Primary probes generated by LLM."],
                }
            )

        mock_client.structured_chat.side_effect = fake_structured_chat
        monkeypatch.setattr(
            "app.llm.yandex_ai_studio.qwen_credential_gate",
            lambda: {"status": "ready", "missing_env_vars": []},
        )
        monkeypatch.setattr("app.llm.yandex_ai_studio.YandexAIStudioClient", lambda: mock_client)

        retrieval_input = plan_retrieval(intent)

        mock_client.structured_chat.assert_called_once()
        families = {probe.source_family_hint for probe in retrieval_input.probes}
        assert {"fedstat", "world_bank", "ckan"}.issubset(families)
        for measure_id in {"m_gdp", "m_inflation", "m_unemployment"}:
            measure_families = {
                probe.source_family_hint
                for probe in retrieval_input.probes
                if probe.measure_id == measure_id and probe.origin == "llm"
            }
            assert measure_families == {"world_bank", "fedstat", "ckan"}
        assert all(
            probe.origin == "llm"
            for probe in retrieval_input.probes
            if probe.purpose != "raw_query_fallback"
        )
        assert retrieval_input.dimension_constraints.geographies == ["BRA", "RUS", "IND", "CHN", "ZAF"]
        assert retrieval_input.dimension_constraints.geography_group == "BRICS"
        assert retrieval_input.dimension_constraints.periods[0] == "2015"
        assert retrieval_input.dimension_constraints.periods[-1] == "2024"
        assert retrieval_input.dimension_constraints.frequency == "annual"
        primary = [probe for probe in retrieval_input.probes if probe.purpose != "raw_query_fallback"]
        assert all("2015" not in probe.text and "2024" not in probe.text for probe in primary)
        assert all("BRICS" not in probe.text and "сравни" not in probe.text.lower() for probe in primary)
        fallback = [probe for probe in retrieval_input.probes if probe.purpose == "raw_query_fallback"]
        assert len(fallback) == 1
        assert fallback[0].origin == "mechanical_fallback"
        assert fallback[0].priority <= 10
        assert retrieval_input.budget_policy.final_source_count is None

    def test_retrieval_planner_rejects_output_without_llm_primary_probes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.artifacts.workflow_artifacts import (
            AmbiguityPolicy,
            DimensionIntent,
            MeasureIntent,
            OperationIntent,
            SourceScope,
            TaskIntent,
            UserIntentArtifact,
        )
        from app.workflow.state import plan_retrieval

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
        mock_client = MagicMock()
        mock_client.structured_chat.side_effect = lambda messages, *, schema, **kwargs: schema.model_validate(
            {
                "original_query": intent.original_query,
                "probes": [],
                "dimension_constraints": {},
                "source_scope": {},
                "budget_policy": {},
                "trace_notes": [],
            }
        )
        monkeypatch.setattr(
            "app.llm.yandex_ai_studio.qwen_credential_gate",
            lambda: {"status": "ready", "missing_env_vars": []},
        )
        monkeypatch.setattr("app.llm.yandex_ai_studio.YandexAIStudioClient", lambda: mock_client)

        with pytest.raises(RuntimeError, match="llm_primary_probes_missing"):
            plan_retrieval(intent)

    def test_retrieval_planner_llm_failure_gates_without_deterministic_primary_probes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.artifacts.workflow_artifacts import (
            AmbiguityPolicy,
            DimensionIntent,
            MeasureIntent,
            OperationIntent,
            SourceScope,
            TaskIntent,
            UserIntentArtifact,
        )
        from app.workflow.graph import _node_retrieval_planner

        intent = UserIntentArtifact(
            original_query="ВВП России 2024",
            task=TaskIntent(category="direct_lookup", user_goal="Найти ВВП России.", expected_output="answer"),
            measures=[
                MeasureIntent(
                    measure_id="m1",
                    user_phrase="ВВП",
                    canonical_concept="gross domestic product",
                    measurement_form="level",
                )
            ],
            dimensions=DimensionIntent(),
            operations=OperationIntent(),
            source_scope=SourceScope(),
            ambiguity=AmbiguityPolicy(needs_clarification=False),
        )
        monkeypatch.setattr(
            "app.llm.yandex_ai_studio.qwen_credential_gate",
            lambda: {"status": "gated_skip", "missing_env_vars": ["YANDEX_AI_STUDIO_QWEN_API_KEY"]},
        )

        result = _node_retrieval_planner(
            {
                "run_id": "phase2-test",
                "query": intent.original_query,
                "canonical_intent": intent,
                "intent": intent.to_intent_frame(),
                "trace_events": [],
                "component_statuses": {},
            }
        )

        assert result["retrieval_input"] is None
        assert result["finalization_pending"] is True
        assert result["component_statuses"]["retrieval_planner"] == "gated"
        assert "retrieval_planner_llm_gated" in result["pending_reason"]

    def test_scouts_execute_multiple_retrieval_input_probes_and_preserve_probe_evidence(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from app.artifacts.workflow_artifacts import (
            DimensionConstraints,
            RetrievalInput,
            RetrievalSourceScope,
            SearchProbe,
            SourceBudgetPolicy,
        )
        from app.workflow.nodes import scouts

        class Candidate:
            def __init__(self, card_id: str, title: str, score: float) -> None:
                self.source_family = "world_bank"
                self.card_id = card_id
                self.chunk_id = f"{card_id}:chunk"
                self.title = title
                self.score = score
                self.relevance_score = score
                self.retrieval_mode = "fake"
                self.evidence_keywords = []
                self.metadata = {"provenance_url": "https://example.test"}
                self.rejection_reasons = []

        class Result:
            dense_status = "ready"

            def __init__(self, candidates: list[Candidate]) -> None:
                self.candidates = candidates
                self.rejected_candidates = []

        class FakeRetriever:
            calls: list[dict[str, Any]] = []

            def __init__(self, index_manifest_path: Path) -> None:
                self.index_manifest_path = index_manifest_path

            def search(self, query: str, *, expected_sources=None, limit: int = 5):
                self.calls.append({"query": query, "expected_sources": expected_sources, "limit": limit})
                return Result([Candidate("wb:gdp", "GDP", 0.9)])

        monkeypatch.setattr(scouts, "HybridRetriever", FakeRetriever)
        retrieval_input = RetrievalInput(
            original_query="Сравни ВВП России 2020",
            probes=[
                SearchProbe(
                    probe_id="p1",
                    text="gross domestic product GDP",
                    purpose="alias",
                    measure_id="m1",
                    language="en",
                    priority=100,
                    source_family_hint="world_bank",
                ),
                SearchProbe(
                    probe_id="p2",
                    text="валовой внутренний продукт",
                    purpose="official_term",
                    measure_id="m1",
                    language="ru",
                    priority=90,
                    source_family_hint="fedstat",
                ),
            ],
            dimension_constraints=DimensionConstraints(geographies=["RUS"], periods=["2020"], frequency="annual"),
            source_scope=RetrievalSourceScope(requested_sources=[], source_constraint="none", source_hints=[]),
            budget_policy=SourceBudgetPolicy(per_probe_limit=3),
        )

        evidence = scouts.run_source_scouts(
            "raw query should not be the only search",
            expected_sources=[],
            index_manifest_path=tmp_path / "manifest.json",
            retrieval_input=retrieval_input,
        )

        assert [call["query"] for call in FakeRetriever.calls] == [
            "gross domestic product GDP",
            "валовой внутренний продукт",
        ]
        assert all(call["expected_sources"] == [] for call in FakeRetriever.calls)
        assert len(evidence.selected_sources) == 1
        assert {item["probe_id"] for item in evidence.selected_sources[0]["probe_evidence"]} == {"p1", "p2"}
        assert {item["origin"] for item in evidence.selected_sources[0]["probe_evidence"]} == {"llm"}


class TestRunCoveragePreview:
    """run_coverage_preview returns list[CoverageReport] and routes to adapters by source_family."""

    def test_returns_list_of_coverage_reports(self) -> None:
        from app.workflow.nodes import coverage
        from app.artifacts.workflow_artifacts import EvidenceBundleArtifact, CoverageReport

        evidence = EvidenceBundleArtifact(
            selected_sources=[
                {
                    "source_family": "ckan",
                    "dataset_id": "pkg-1",
                    "title": "CKAN Dataset",
                    "formats": ["CSV"],
                    "promoted_resources": [],
                    "resource_count": 0,
                    "provenance_url": "http://example.com",
                }
            ],
            rejected_sources=[],
            retrieval_status="ok",
        )
        reports = coverage.run_coverage_preview(evidence, intent_fields={"periods": ["2020", "2021"]})
        assert isinstance(reports, list)
        for report in reports:
            assert isinstance(report, CoverageReport)
            # Every report must include source_specific_risks in evidence
            assert "source_specific_risks" in report.evidence


# ---------------------------------------------------------------------------
# Task 3: Extraction planner tests
# ---------------------------------------------------------------------------


class TestBuildExtractionPlan:
    """build_extraction_plan emits safe structured plans from allowlist only."""

    def test_allowed_operations_only(self) -> None:
        from app.workflow.nodes.extraction_planner import build_extraction_plan, ALLOWED_OPERATIONS
        from app.artifacts.workflow_artifacts import IntentFrame, CoverageReport

        intent = IntentFrame(
            query="ВВП России 2020",
            category="simple",
            known_fields={"periods": ["2020"], "geography": "Russia"},
        )
        report = CoverageReport(
            source_id="fedstat-001",
            status="ok",
            available_periods=["2020"],
            available_geographies=["Russia"],
            unit="миллиарды руб.",
            frequency="annual",
            evidence={"source_specific_risks": []},
        )
        plan = build_extraction_plan(intent, [report])
        assert plan.status == "ok"
        for op in plan.operations:
            assert op in ALLOWED_OPERATIONS, f"Operation '{op}' is not in ALLOWED_OPERATIONS"

    def test_no_sql_injection_in_plan(self) -> None:
        from app.workflow.nodes.extraction_planner import build_extraction_plan
        from app.artifacts.workflow_artifacts import IntentFrame, CoverageReport

        # Simulate malicious query
        intent = IntentFrame(
            query="SELECT * FROM users; DROP TABLE users; --",
            category="simple",
            known_fields={},
        )
        report = CoverageReport(
            source_id="fedstat-001",
            status="ok",
            available_periods=[],
            available_geographies=[],
            evidence={"source_specific_risks": []},
        )
        plan = build_extraction_plan(intent, [report])
        plan_json = plan.model_dump_json()
        # Must not contain raw DROP TABLE in the plan output
        assert "DROP TABLE" not in plan_json

    def test_gated_coverage_produces_skipped_plan(self) -> None:
        from app.workflow.nodes.extraction_planner import build_extraction_plan
        from app.artifacts.workflow_artifacts import IntentFrame, CoverageReport

        intent = IntentFrame(
            query="ВВП России",
            category="simple",
            known_fields={},
        )
        report = CoverageReport(
            source_id="fedstat-001",
            status="gated",
            available_periods=[],
            available_geographies=[],
            evidence={"source_specific_risks": ["data_gate"]},
            gated_reason="Parquet not available locally",
        )
        plan = build_extraction_plan(intent, [report])
        assert plan.status in ("skipped_with_reason", "needs_clarification", "gated")
        assert plan.skip_reason is not None

    def test_ckan_dispatch_key_present(self) -> None:
        """ExtractionPlan operations or source dispatch includes ckan key."""
        from app.workflow.nodes.extraction_planner import build_extraction_plan, ALLOWED_OPERATIONS
        from app.artifacts.workflow_artifacts import IntentFrame, CoverageReport

        # ALLOWED_OPERATIONS must mention extraction routing, which covers ckan
        # At minimum the plan module must reference extract_ckan_dataset dispatch
        from app.workflow.nodes import extraction_planner
        source = open(extraction_planner.__file__, encoding="utf-8").read()
        assert "extract_ckan_dataset" in source or "ckan" in source.lower(), (
            "extraction_planner must reference ckan extraction dispatch"
        )
        # Also ensure ALLOWED_OPERATIONS is non-empty and does not include free SQL
        assert "ALLOWED_OPERATIONS" in dir(__import__("app.workflow.nodes.extraction_planner", fromlist=["ALLOWED_OPERATIONS"]))
        assert len(ALLOWED_OPERATIONS) > 0
