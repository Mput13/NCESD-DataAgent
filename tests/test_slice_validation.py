"""Tests for slice-level coverage validation fields."""
import pytest


class TestCoverageReportSliceFields:
    def test_coverage_report_has_slice_fields_with_defaults(self):
        from app.artifacts.workflow_artifacts import CoverageReport
        report = CoverageReport(
            source_id="test",
            status="ok",
        )
        assert hasattr(report, "matched_geographies")
        assert hasattr(report, "matched_periods")
        assert hasattr(report, "requested_slice_rows")
        assert hasattr(report, "extraction_ready")
        assert report.matched_geographies == []
        assert report.matched_periods == []
        assert report.requested_slice_rows == 0
        assert report.extraction_ready is False

    def test_coverage_report_slice_fields_settable(self):
        from app.artifacts.workflow_artifacts import CoverageReport
        report = CoverageReport(
            source_id="test",
            status="ok",
            matched_geographies=["Россия"],
            matched_periods=["2020", "2021", "2022"],
            requested_slice_rows=150,
            extraction_ready=True,
        )
        assert report.matched_geographies == ["Россия"]
        assert report.requested_slice_rows == 150
        assert report.extraction_ready is True

    def test_coverage_report_extra_fields_still_forbidden(self):
        from app.artifacts.workflow_artifacts import CoverageReport
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CoverageReport(source_id="test", status="ok", unknown_field="value")


class TestFedstatSliceCoverage:
    """preview_fedstat_coverage must populate slice fields."""

    def _make_source_card(self, tmp_path) -> dict:
        """Create a minimal FedStat source card with a real parquet file."""
        import pyarrow as pa
        import pyarrow.parquet as pq

        # Create a FedStat-style wide parquet file
        # First row = indicator names, subsequent rows = data with geo/unit columns
        table = pa.table({
            "Территория": ["Наименование показателя", "Россия", "Казахстан"],
            "Единица измерения": ["", "руб.", "руб."],
            "2020": ["ВВП", "100000.0", "50000.0"],
            "2021": ["ВВП", "110000.0", "55000.0"],
            "2022": ["ВВП", "120000.0", ""],  # Kazakhstan has missing 2022
        })
        parquet_path = tmp_path / "12345.parquet"
        pq.write_table(table, parquet_path)

        return {
            "dataset_id": "12345",
            "local_path": str(parquet_path),
            "title": "ВВП по регионам",
        }

    def test_matched_geographies_populated_when_filter_matches(self, tmp_path):
        from app.data.fedstat_adapter import preview_fedstat_coverage

        card = self._make_source_card(tmp_path)
        filters = {"geography": "Россия"}
        report = preview_fedstat_coverage(card, filters=filters)

        assert "Россия" in report.matched_geographies, (
            f"Expected 'Россия' in matched_geographies, got {report.matched_geographies}"
        )
        assert report.requested_slice_rows > 0
        assert report.extraction_ready is True

    def test_matched_geographies_empty_when_filter_not_found(self, tmp_path):
        from app.data.fedstat_adapter import preview_fedstat_coverage

        card = self._make_source_card(tmp_path)
        filters = {"geography": "Германия"}  # not in the data
        report = preview_fedstat_coverage(card, filters=filters)

        assert report.matched_geographies == []
        assert report.requested_slice_rows == 0
        assert report.extraction_ready is False

    def test_extraction_ready_true_when_no_filter_specified(self, tmp_path):
        """Without geography filter, any data means extraction_ready=True."""
        from app.data.fedstat_adapter import preview_fedstat_coverage

        card = self._make_source_card(tmp_path)
        filters = {}  # no filter
        report = preview_fedstat_coverage(card, filters=filters)

        assert report.extraction_ready is True
        assert report.requested_slice_rows > 0


class TestWorldBankSliceCoverage:
    """preview_world_bank_coverage must populate slice fields."""

    def _make_wb_source_card(self, tmp_path) -> dict:
        import pyarrow as pa
        import pyarrow.parquet as pq

        # World Bank parquet: long format with countryiso3code, date, value
        table = pa.table({
            "countryiso3code": ["RUS", "RUS", "KAZ", "KAZ"],
            "date": ["2020", "2021", "2020", "2021"],
            "value": [1.5, 2.3, 1.1, 1.8],
            "indicator": ["NY.GDP.MKTP.CD"] * 4,
        })
        parquet_path = tmp_path / "NY.GDP.MKTP.CD.parquet"
        pq.write_table(table, parquet_path)

        return {
            "dataset_id": "NY.GDP.MKTP.CD",
            "local_path": str(parquet_path),
            "title": "GDP (current US$)",
        }

    def test_matched_geographies_populated_for_russia(self, tmp_path):
        from app.data.world_bank_adapter import preview_world_bank_coverage

        card = self._make_wb_source_card(tmp_path)
        report = preview_world_bank_coverage(
            card, countries=["RUS"], periods=[], indicator_id="NY.GDP.MKTP.CD"
        )

        assert "RUS" in report.matched_geographies or any("RUS" in g for g in report.matched_geographies)
        assert report.requested_slice_rows > 0
        assert report.extraction_ready is True

    def test_matched_geographies_empty_for_unknown_country(self, tmp_path):
        from app.data.world_bank_adapter import preview_world_bank_coverage

        card = self._make_wb_source_card(tmp_path)
        report = preview_world_bank_coverage(
            card, countries=["DEU"], periods=[], indicator_id="NY.GDP.MKTP.CD"
        )

        assert report.matched_geographies == []
        assert report.requested_slice_rows == 0
        assert report.extraction_ready is False

    def test_extraction_ready_true_without_country_filter(self, tmp_path):
        from app.data.world_bank_adapter import preview_world_bank_coverage

        card = self._make_wb_source_card(tmp_path)
        report = preview_world_bank_coverage(
            card, countries=[], periods=[], indicator_id="NY.GDP.MKTP.CD"
        )

        assert report.extraction_ready is True


class TestZeroRowDatasetHandling:
    """run_deterministic_tools must mark zero-row datasets with quality_flag and gated status."""

    def test_zero_row_dataset_gets_empty_slice_flag(self):
        """When extraction returns 0 rows, DatasetArtifact must have quality_flags=['empty_slice'] and status='gated'."""
        from unittest.mock import patch, MagicMock
        from pathlib import Path
        from app.artifacts.workflow_artifacts import (
            DatasetArtifact, ExtractionPlan, IntentFrame
        )
        from app.workflow.nodes.deterministic_tools import run_deterministic_tools
        from uuid import uuid4

        zero_row_dataset = DatasetArtifact(
            artifact_id=f"ds-{uuid4().hex[:8]}",
            status="ok",
            source_id="fedstat:12345",
            rows=0,
            records=[],
            provenance=[{"source": "fedstat", "dataset_id": "12345"}],
        )

        plan = ExtractionPlan(
            artifact_id="plan-001",
            source_id="fedstat:12345",
            status="ok",
            operations=["filter_rows", "export_dataset"],
            filters={"geography": "Казахстан"},
        )

        intent = IntentFrame(
            query="ВВП Казахстана",
            category="simple",
            known_fields={"geography": "Казахстан"},
        )

        state = {
            "run_id": "test-run",
            "extraction_plan": plan,
            "intent": intent,
            "dataset_artifacts": [],
            "script_artifacts": [],
            "trace_events": [],
            "component_statuses": {},
        }

        with patch("app.workflow.nodes.deterministic_tools._dispatch_extraction") as mock_dispatch:
            mock_dispatch.return_value = zero_row_dataset
            with patch("app.workflow.nodes.deterministic_tools.export_dataset_with_script") as mock_export:
                mock_export.return_value = None
                result = run_deterministic_tools(state, output_dir=Path("/tmp/test-artifacts"))

        datasets = result["dataset_artifacts"]
        assert len(datasets) == 1
        dataset = datasets[0]
        assert "empty_slice" in dataset.quality_flags, (
            f"Expected 'empty_slice' in quality_flags, got {dataset.quality_flags}"
        )
        assert dataset.status == "gated", (
            f"Expected status='gated' for zero-row dataset, got '{dataset.status}'"
        )
        assert result["component_statuses"]["deterministic_tools"] == "empty_slice"

    def test_nonzero_row_dataset_stays_ok(self):
        """When extraction returns rows > 0, DatasetArtifact keeps status='ok'."""
        from unittest.mock import patch
        from pathlib import Path
        from app.artifacts.workflow_artifacts import (
            DatasetArtifact, ExtractionPlan, IntentFrame
        )
        from app.workflow.nodes.deterministic_tools import run_deterministic_tools
        from uuid import uuid4

        ok_dataset = DatasetArtifact(
            artifact_id=f"ds-{uuid4().hex[:8]}",
            status="ok",
            source_id="fedstat:12345",
            rows=150,
            records=[{"value": 1.0}],
            provenance=[{"source": "fedstat"}],
        )

        plan = ExtractionPlan(
            artifact_id="plan-001",
            source_id="fedstat:12345",
            status="ok",
            operations=["filter_rows", "export_dataset"],
        )

        state = {
            "run_id": "test-run",
            "extraction_plan": plan,
            "intent": None,
            "dataset_artifacts": [],
            "script_artifacts": [],
            "trace_events": [],
            "component_statuses": {},
        }

        with patch("app.workflow.nodes.deterministic_tools._dispatch_extraction") as mock_dispatch, \
             patch("app.workflow.nodes.deterministic_tools.export_dataset_with_script") as mock_export:
            mock_dispatch.return_value = ok_dataset
            mock_export.return_value = None
            result = run_deterministic_tools(state, output_dir=Path("/tmp/test-artifacts"))

        dataset = result["dataset_artifacts"][0]
        assert dataset.status == "ok"
        assert "empty_slice" not in dataset.quality_flags
