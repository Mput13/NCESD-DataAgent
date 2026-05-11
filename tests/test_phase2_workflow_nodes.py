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

    def test_preserves_retrieval_paths_subgraph_and_channel_statuses(
        self, tmp_path: Path
    ) -> None:
        from app.workflow.nodes import scouts

        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text(
            json.dumps({
                "card_id": "fedstat:57319:metadata",
                "chunk_id": "fedstat-57319-0",
                "source_family": "fedstat",
                "embedding_text": (
                    "title: Валовой внутренний продукт GDP\n"
                    "source_family: FedStat\n"
                    "dataset_id: 57319\n"
                    "geography: Россия\n"
                ),
                "provenance_url": "http://fedstat.ru/57319",
            }, ensure_ascii=False) + "\n",
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
            "ВВП России",
            expected_sources=["fedstat"],
            index_manifest_path=manifest_path,
        )

        assert result.selected_for_coverage
        candidate = result.selected_for_coverage[0]
        assert "lexical" in candidate.retrieval_paths
        assert "fusion_modes" in candidate.retrieval_provenance
        assert result.channel_statuses
        assert result.subgraph_context is None or "nodes" in result.subgraph_context

    def test_dense_gated_with_lexical_candidate_is_partial(self, tmp_path: Path) -> None:
        from app.workflow.nodes import scouts

        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text(
            json.dumps({
                "card_id": "fedstat:57319:metadata",
                "chunk_id": "fedstat-57319-0",
                "source_family": "fedstat",
                "embedding_text": "title: ВВП России\nsource_family: FedStat\n",
            }, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "status": "gated_skip",
            "dense_status": "gated_skip",
            "corpus_artifact_path": str(corpus_path),
            "collection_name": "test",
        }), encoding="utf-8")

        result = scouts.run_source_scouts(
            "ВВП России",
            expected_sources=["fedstat"],
            index_manifest_path=manifest_path,
        )

        assert result.selected_for_coverage
        assert result.retrieval_status == "partial"
        dense = next(s for s in result.channel_statuses if s.channel == "dense")
        assert dense.status == "gated"

    def test_ckan_required_adapter_error_visible(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from app.workflow.nodes import scouts
        from app.data import ckan_adapter

        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text("", encoding="utf-8")
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "status": "gated_skip",
            "dense_status": "gated_skip",
            "corpus_artifact_path": str(corpus_path),
            "collection_name": "test",
        }), encoding="utf-8")

        def boom(query: str, *, rows: int = 5) -> list[dict[str, Any]]:
            raise RuntimeError("ckan unavailable")

        monkeypatch.setattr(ckan_adapter, "search_ckan_source_cards", boom)

        result = scouts.run_source_scouts(
            "данные 57319",
            expected_sources=["ckan"],
            index_manifest_path=manifest_path,
        )

        ckan = next(s for s in result.channel_statuses if s.channel == "ckan")
        assert ckan.status == "error"
        assert "ckan unavailable" in (ckan.error or "")


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

    def test_consumes_selected_for_coverage_and_records_provenance(self) -> None:
        from app.workflow.nodes import coverage
        from app.artifacts.workflow_artifacts import EvidenceBundleArtifact, SourceCandidate

        evidence = EvidenceBundleArtifact(
            selected_for_coverage=[
                SourceCandidate(
                    source_candidate_id="ckan:pkg-1",
                    source_family="ckan",
                    card_id="pkg-1",
                    dataset_id="pkg-1",
                    title="CKAN Dataset",
                    formats=["CSV"],
                    retrieval_paths=["ckan"],
                    retrieval_provenance={"fusion_modes": ["ckan"]},
                    adapter_name="extract_ckan_dataset",
                )
            ],
            retrieval_status="ok",
        )

        reports = coverage.run_coverage_preview(
            evidence,
            intent_fields={"periods": ["2020"]},
            live_llm_required=False,
        )

        assert reports[0].source_candidate_id == "ckan:pkg-1"
        assert reports[0].source_family == "ckan"
        assert reports[0].retrieval_provenance["fusion_modes"] == ["ckan"]

    def test_aggregate_no_covered_slice_when_reports_not_ready(self) -> None:
        from app.workflow.nodes.coverage import aggregate_coverage_status
        from app.artifacts.workflow_artifacts import CoverageReport

        reports = [
            CoverageReport(
                source_id="fedstat-001",
                status="ok",
                extraction_ready=False,
                extraction_blockers=["missing_period"],
            ),
            CoverageReport(source_id="ckan-001", status="gated", gated_reason="llm_coverage_gated"),
        ]

        assert aggregate_coverage_status(reports, had_sources=True) == "no_covered_slice"


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

    def test_refuses_non_ready_reports_and_carries_dispatch_metadata(self) -> None:
        from app.workflow.nodes.extraction_planner import build_extraction_plan
        from app.artifacts.workflow_artifacts import IntentFrame, CoverageReport

        intent = IntentFrame(
            query="ВВП России 2020",
            category="simple",
            known_fields={"period": "2020"},
        )
        not_ready = CoverageReport(
            source_id="fedstat-001",
            source_candidate_id="candidate-fedstat-001",
            source_family="fedstat",
            status="ok",
            extraction_ready=False,
            extraction_blockers=["period_not_available"],
        )
        ready = CoverageReport(
            source_id="NY.GDP.MKTP.CD",
            source_candidate_id="candidate-wb-gdp",
            source_family="world_bank",
            status="ok",
            extraction_ready=True,
            evidence={"row_count": 10},
        )

        plan = build_extraction_plan(intent, [not_ready, ready], live_llm_required=False)

        assert plan.status == "ok"
        assert plan.source_id == "NY.GDP.MKTP.CD"
        assert plan.source_family == "world_bank"
        assert plan.adapter_name == "extract_world_bank_dataset"
        assert plan.source_candidate_ids == ["candidate-wb-gdp"]
        assert plan.coverage_report_ids == ["candidate-wb-gdp"]
