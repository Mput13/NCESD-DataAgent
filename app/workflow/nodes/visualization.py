"""Visualization node for Phase 2 workflow.

Creates VisualizationSpec from DatasetArtifact deterministically.

Chart type selection rules:
- Time-series with single geo: line
- Time-series with multiple geo_id values: grouped_line
- Category comparison without time: bar
- Otherwise: table

Visualization is never generated from LLM text (D-28).
Visualization errors must NEVER change a valid final decision (passed/not_found/needs_clarification).
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.artifacts.workflow_artifacts import DatasetArtifact, VisualizationSpec
from app.data.deterministic_tools import render_visualization_from_dataset_artifact


def build_visualization(
    dataset: DatasetArtifact | None,
    *,
    query_category: str,
) -> VisualizationSpec:
    """Build a VisualizationSpec from a DatasetArtifact.

    Uses render_visualization_from_dataset_artifact for deterministic rendering,
    then overrides chart_type based on column analysis:
    - period column + one geo_id value -> line
    - period column + multiple geo_id values -> grouped_line
    - no period, multiple category values -> bar
    - otherwise -> table

    Never parses numbers from narrator text.
    On error: returns status='error' spec — never raises or changes final decision.
    """
    artifact_id = f"visualization-{uuid4().hex[:8]}"

    if dataset is None:
        return VisualizationSpec(
            artifact_id=artifact_id,
            chart_type="table",
            status="skipped_with_reason",
            skip_reason="no_dataset_provided",
        )

    records: list[dict[str, Any]] = list(dataset.records or [])
    columns: list[str] = list(dataset.columns or [])

    # Handle empty dataset
    if not records or not columns:
        return VisualizationSpec(
            artifact_id=artifact_id,
            chart_type="table",
            dataset_artifact_id=dataset.artifact_id,
            status="skipped_with_reason",
            skip_reason="empty_dataset_no_rows_or_columns",
        )

    # Get base visualization from deterministic renderer
    try:
        base_spec = render_visualization_from_dataset_artifact(dataset)
        encoding = dict(base_spec.encoding)
    except Exception as exc:
        encoding = {"error": str(exc)}

    # Determine chart type from columns and records
    chart_type = _infer_chart_type(columns, records, query_category)

    return VisualizationSpec(
        artifact_id=artifact_id,
        chart_type=chart_type,
        dataset_artifact_id=dataset.artifact_id,
        status="ok",
        encoding=encoding,
    )


def build_visualization_for_all_datasets(
    datasets: list[DatasetArtifact],
    *,
    query_category: str,
) -> list[VisualizationSpec]:
    """Build VisualizationSpec for every selected dataset.

    Returns one spec per dataset. Each spec has explicit status: ok, skipped_with_reason.
    Errors in individual datasets produce status='skipped_with_reason' with skip_reason,
    and never propagate to the caller as exceptions.

    The caller's final_outcome decision is NEVER modified by this function.
    """
    if not datasets:
        return [
            VisualizationSpec(
                artifact_id=f"visualization-{uuid4().hex[:8]}",
                chart_type="table",
                status="skipped_with_reason",
                skip_reason="no_datasets_provided",
            )
        ]

    specs: list[VisualizationSpec] = []
    for dataset in datasets:
        try:
            spec = build_visualization(dataset, query_category=query_category)
        except Exception as exc:
            spec = VisualizationSpec(
                artifact_id=f"visualization-error-{uuid4().hex[:8]}",
                chart_type="table",
                dataset_artifact_id=dataset.artifact_id,
                status="skipped_with_reason",
                skip_reason=f"visualization_build_error:{exc}",
            )
        specs.append(spec)
    return specs


def _infer_chart_type(
    columns: list[str],
    records: list[dict[str, Any]],
    query_category: str,
) -> str:
    """Determine the best chart type based on column structure and query category.

    Rules:
    - period column present + single geo_id value -> line
    - period column present + multiple geo_id values -> grouped_line
    - no period, geo/category variation -> bar
    - otherwise -> table
    """
    col_lower = [c.lower() for c in columns]

    has_period = any(c in ("period", "date", "year", "quarter", "month") for c in col_lower)
    has_geo = any(c in ("geo_id", "country_id", "country", "geo", "region") for c in col_lower)

    if has_period:
        if has_geo:
            # Count distinct geo_id values
            geo_col = next(
                (c for c in columns if c.lower() in ("geo_id", "country_id", "country", "geo", "region")),
                None,
            )
            if geo_col:
                geo_values = {str(r.get(geo_col, "")) for r in records if r.get(geo_col)}
                if len(geo_values) > 1:
                    return "grouped_line"
        return "line"

    # No period column — check for categorical comparison
    if query_category in ("comparative",) or has_geo:
        return "bar"

    return "table"
