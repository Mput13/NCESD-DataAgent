from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import duckdb
import requests

from app.artifacts.workflow_artifacts import DatasetArtifact, ScriptArtifact, VisualizationSpec


def fedstat_normalize_preview(source_card: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic FedStat wide-table normalization evidence."""

    dimensions = source_card.get("dimensions") or []
    resource_id = str(source_card.get("resource_id") or "")
    metadata = source_card.get("metadata") or {}
    return {
        "source_family": "FedStat",
        "source_id": source_card.get("dataset_id"),
        "resource_id": resource_id,
        "strategy": "DuckDB SQL-first over normalized preview; PyArrow reads Parquet metadata before melt.",
        "wide_table_normalization": {
            "first_row_header": True,
            "dimension_columns": dimensions,
            "period_column_detection": "year-like columns after internal header",
            "normalizer": "fedstat_normalize_preview",
        },
        "row_count_hint": metadata.get("rows"),
        "polars_rationale": "Polars not used in the Phase 1 probe because PyArrow + DuckDB are sufficient for bounded metadata/schema preview.",
    }


def wb_coverage_preview(source_card: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic World Bank canonical long-format coverage evidence."""

    coverage = source_card.get("period_coverage") or {}
    return {
        "source_family": "World Bank",
        "source_id": source_card.get("dataset_id"),
        "resource_id": source_card.get("resource_id"),
        "strategy": "DuckDB SQL-first over canonical long-format parquet.",
        "canonical_long_format": {
            "columns": ["indicator_id", "country_id", "date", "value"],
            "adapter": "World Bank canonical long-format adapter evidence",
        },
        "country_coverage": coverage.get("geography") or source_card.get("geography") or [],
        "period_coverage": coverage,
        "polars_rationale": "Polars not used; DuckDB can query the narrow long-format parquet directly.",
    }


def ckan_package_search(query: str, *, rows: int = 5, endpoint: str | None = None) -> dict[str, Any]:
    """Bounded CKAN package_search wrapper for trusted NSED catalog access."""

    endpoint = endpoint or "https://repository.nsedc.ru/api/3/action/package_search"
    response = requests.get(endpoint, params={"q": query, "rows": rows}, timeout=20)
    response.raise_for_status()
    payload = response.json()
    results = (payload.get("result") or {}).get("results") or []
    return {
        "query": query,
        "rows": rows,
        "endpoint": endpoint,
        "count": (payload.get("result") or {}).get("count"),
        "results": results[:rows],
    }


def ckan_package_show(package_id: str, *, endpoint_root: str | None = None) -> dict[str, Any]:
    """Bounded CKAN package_show wrapper for promoted package metadata."""

    endpoint_root = endpoint_root or "https://repository.nsedc.ru/api/3/action"
    response = requests.get(
        f"{endpoint_root.rstrip('/')}/package_show",
        params={"id": package_id},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def run_duckdb_query(sql: str, *, parameters: list[Any] | None = None) -> list[dict[str, Any]]:
    """Run a read-only DuckDB SQL query and return row dictionaries."""

    if not sql.strip().lower().startswith(("select", "with")):
        raise ValueError("Only read-only SELECT/WITH DuckDB queries are allowed")
    connection = duckdb.connect(database=":memory:")
    try:
        cursor = connection.execute(sql, parameters or [])
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    finally:
        connection.close()


def build_dataset_artifact(
    *,
    rows: list[dict[str, Any]],
    artifact_id: str,
    source_id: str,
    provenance: list[dict[str, Any]],
) -> DatasetArtifact:
    """Build a source-bound DatasetArtifact from deterministic tool rows."""

    columns = list(rows[0].keys()) if rows else []
    return DatasetArtifact(
        artifact_id=artifact_id,
        status="ok",
        source_id=source_id,
        rows=len(rows),
        columns=columns,
        records=rows,
        provenance=provenance,
        quality_flags=["deterministic_duckdb_output"],
    )


def export_csv_parquet_manifest(
    dataset: DatasetArtifact,
    *,
    output_dir: Path,
) -> DatasetArtifact:
    """Export DatasetArtifact records to CSV, Parquet when available, and manifest JSON."""

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = dataset.artifact_id.replace(":", "_").replace("/", "_")
    csv_path = output_dir / f"{stem}.csv"
    parquet_path = output_dir / f"{stem}.parquet"
    manifest_path = output_dir / f"{stem}.manifest.json"
    records = dataset.records
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=dataset.columns)
        writer.writeheader()
        writer.writerows(records)
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.Table.from_pylist(records)
        pq.write_table(table, parquet_path)
        parquet_value = str(parquet_path)
    except Exception as exc:  # pragma: no cover - depends on optional local pyarrow
        parquet_value = None
        dataset.quality_flags.append(f"parquet_export_skipped:{type(exc).__name__}")
    manifest = {
        "artifact_id": dataset.artifact_id,
        "status": dataset.status,
        "rows": dataset.rows,
        "columns": dataset.columns,
        "csv_path": str(csv_path),
        "parquet_path": parquet_value,
        "provenance": dataset.provenance,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return dataset.model_copy(
        update={
            "csv_path": str(csv_path),
            "parquet_path": parquet_value,
            "manifest_path": str(manifest_path),
        }
    )


def export_dataset_with_script(
    dataset: DatasetArtifact,
    *,
    output_dir: Path,
    script_text: str,
) -> tuple[DatasetArtifact, ScriptArtifact]:
    """Export a dataset and a deterministic reproducibility script artifact."""

    _validate_script_text(script_text)
    exported = export_csv_parquet_manifest(dataset, output_dir=output_dir)
    stem = dataset.artifact_id.replace(":", "_").replace("/", "_")
    script_path = output_dir / f"{stem}.py"
    script_path.write_text(script_text, encoding="utf-8")
    digest = hashlib.sha256(script_path.read_bytes()).hexdigest()
    script = ScriptArtifact(
        artifact_id=f"{dataset.artifact_id}:script",
        path=str(script_path),
        script_path=str(script_path),
        language="python",
        content=script_text,
        entrypoint=str(script_path),
        source_ids=[dataset.source_id] if dataset.source_id else [],
        source_dataset_artifact_id=dataset.artifact_id,
        dataset_artifact_id=dataset.artifact_id,
        sha256=digest,
        downloadable=True,
        download_filename=script_path.name,
        display_name=f"Reproduce {dataset.artifact_id}",
        mime_type="text/x-python",
        provenance=dataset.provenance,
        quality_flags=["deterministic_reproducibility_script"],
    )
    return exported, script


def _validate_script_text(script_text: str) -> None:
    lowered = script_text.casefold()
    if ".env" in lowered:
        raise ValueError("Reproducibility scripts must not reference .env files")
    forbidden_assignment = re.search(
        r"\b(api[_-]?key|token|secret|password)\b\s*=",
        lowered,
    )
    if forbidden_assignment:
        raise ValueError("Reproducibility scripts must not embed secrets")


def render_visualization_from_dataset_artifact(
    dataset: DatasetArtifact,
) -> VisualizationSpec:
    """Create deterministic Altair/Plotly rendering metadata from DatasetArtifact."""

    renderer = "Altair"
    try:
        import altair as alt

        chart_repr = (
            alt.Chart({"values": dataset.records})
            .mark_text()
            .encode(text=alt.value(f"{dataset.rows or 0} rows"))
            .to_dict()
        )
    except Exception:
        renderer = "Altair-compatible"
        chart_repr = {
            "mark": "table",
            "data": {"values": dataset.records},
            "columns": dataset.columns,
        }
    return VisualizationSpec(
        artifact_id=f"{dataset.artifact_id}:visualization",
        chart_type="table",
        dataset_artifact_id=dataset.artifact_id,
        status="ok",
        encoding={"renderer": renderer, "spec": chart_repr},
    )
