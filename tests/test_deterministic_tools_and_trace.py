from __future__ import annotations

import json
from pathlib import Path


def test_deterministic_tool_contracts_export_dataset_and_visualization(tmp_path: Path) -> None:
    from app.artifacts.workflow_artifacts import DatasetArtifact, ScriptArtifact, VisualizationSpec
    from app.data.deterministic_tools import (
        build_dataset_artifact,
        export_csv_parquet_manifest,
        export_dataset_with_script,
        render_visualization_from_dataset_artifact,
        run_duckdb_query,
    )

    rows = run_duckdb_query("SELECT 1 AS value, 'source-bound' AS label")
    dataset = build_dataset_artifact(
        rows=rows,
        artifact_id="dataset-test",
        source_id="unit-test",
        provenance=[{"source_url": "file://unit-test"}],
    )
    exported = export_csv_parquet_manifest(dataset, output_dir=tmp_path)
    spec = render_visualization_from_dataset_artifact(exported)

    assert isinstance(exported, DatasetArtifact)
    assert exported.csv_path and Path(exported.csv_path).exists()
    assert exported.manifest_path and Path(exported.manifest_path).exists()
    assert isinstance(spec, VisualizationSpec)
    assert spec.status == "ok"
    assert "Altair" in spec.encoding.get("renderer", "") or "Plotly" in spec.encoding.get("renderer", "")

    exported_with_script, script = export_dataset_with_script(
        dataset,
        output_dir=tmp_path / "scripted",
        script_text=(
            "from pathlib import Path\n"
            "\n"
            "DATASET_ID = 'dataset-test'\n"
            "OUTPUT_DIR = Path('artifacts')\n"
        ),
    )

    assert isinstance(exported_with_script, DatasetArtifact)
    assert isinstance(script, ScriptArtifact)
    assert script.language == "python"
    assert script.source_dataset_artifact_id == dataset.artifact_id
    assert len(script.sha256) == 64
    assert script.download_filename == "dataset-test.py"
    assert Path(script.path).exists()
    assert Path(script.path).suffix == ".py"


def test_trace_models_reuse_canonical_trace_event() -> None:
    from app.artifacts.workflow_artifacts import TraceEvent
    from app.ui.trace_models import (
        FeedbackRequest,
        FixRequest,
        IndexStatusView,
        WorkflowTraceViewModel,
    )

    event = TraceEvent(
        run_id="run-ui",
        state="index",
        agent="Supervisor",
        decision="ready",
    )
    view = WorkflowTraceViewModel(
        run_id="run-ui",
        index_status=IndexStatusView(state="gated_skip"),
        trace_events=[event],
    )

    assert view.trace_events[0] is event
    assert view.index_status.state in {"building", "ready", "stale", "gated_skip"}
    assert FeedbackRequest(run_id="run-ui").diagnostic is True
    assert FixRequest(run_id="run-ui", target_state="coverage").target_state == "coverage"


def test_extraction_probe_runner_writes_machine_readable_evidence(tmp_path: Path) -> None:
    from scripts.run_extraction_probes import run_extraction_probes

    manifest = Path(".planning/phases/01-data-architecture-research/source-catalog-manifest.json")
    report = tmp_path / "extraction-probes.md"
    evidence = tmp_path / "extraction-probes.json"

    result = run_extraction_probes(
        source_catalog_manifest=manifest,
        report_path=report,
        json_output=evidence,
    )

    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "## FedStat wide Parquet probe" in text
    assert "## World Bank parquet probe" in text
    assert "## CKAN resource path probe" in text
    assert "DuckDB SQL-first" in text
    assert "PyArrow" in text
    assert "Polars" in text
    data = json.loads(evidence.read_text(encoding="utf-8"))
    families = {item["source_family"] for item in data["probes"]}
    assert {"FedStat", "World Bank", "CKAN"}.issubset(families)
    assert result["probe_count"] >= 3
