from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import duckdb
import pyarrow.parquet as pq

from app.artifacts.workflow_artifacts import CoverageReport, DatasetArtifact, utc_now_iso
from app.data.deterministic_tools import export_csv_parquet_manifest


CANONICAL_DATASET_COLUMNS = [
    "source",
    "dataset_id",
    "indicator_id",
    "indicator_name",
    "geo_id",
    "geo_name",
    "period",
    "period_type",
    "value",
    "unit",
    "dimensions",
    "source_url",
    "retrieved_at",
    "quality_flags",
]


def preview_fedstat_coverage(
    source_card: dict[str, Any],
    *,
    filters: dict[str, Any],
) -> CoverageReport:
    """Inspect a FedStat wide Parquet file without using LLM extraction."""

    rows, metadata = _load_normalized_rows(source_card)
    indicator = _optional_text(filters.get("indicator") or filters.get("indicator_name"))
    filtered = _filter_rows(rows, indicator=indicator, metadata=metadata)
    period_columns = metadata["period_columns"]
    geographies = sorted({_geo_name(row, metadata) for row in filtered if _geo_name(row, metadata)})
    missing_values = sum(
        1
        for row in filtered
        for period in period_columns
        if row.get(period) in (None, "")
    )
    units = {
        _optional_text(row.get(metadata["unit_column"]))
        for row in filtered
        if metadata.get("unit_column") and _optional_text(row.get(metadata["unit_column"]))
    }

    return CoverageReport(
        source_id=str(source_card.get("dataset_id") or source_card.get("resource_id") or "fedstat"),
        status="ok",
        checks=[
            "pyarrow_parquet_metadata_read",
            "duckdb_rows_read",
            "fedstat_wide_first_row_header_normalized"
            if metadata["first_row_header"]
            else "fedstat_columns_used_as_headers",
        ],
        available_periods=period_columns,
        available_geographies=geographies,
        unit=_optional_text(source_card.get("units")) or sorted(units)[0] if units else _optional_text(source_card.get("units")),
        frequency=_optional_text(source_card.get("frequency")) or "annual",
        evidence={
            "missing_values": missing_values,
            "row_count": len(filtered),
            "source_path": str(_parquet_path(source_card)),
            "physical_columns": metadata["physical_columns"],
            "logical_columns": metadata["logical_columns"],
        },
    )


def extract_fedstat_dataset(
    source_card: dict[str, Any],
    *,
    filters: dict[str, Any],
    output_dir: Path,
    artifact_id: str,
) -> DatasetArtifact:
    """Extract canonical long rows from a FedStat wide Parquet source."""

    rows, metadata = _load_normalized_rows(source_card)
    indicator = _optional_text(filters.get("indicator") or filters.get("indicator_name"))
    geography = _optional_text(filters.get("geography") or filters.get("geo_name"))
    requested_periods = {str(period) for period in filters.get("periods", [])}
    period_columns = [
        period for period in metadata["period_columns"] if not requested_periods or period in requested_periods
    ]
    filtered = _filter_rows(rows, indicator=indicator, geography=geography, metadata=metadata)
    source_url = _source_url(source_card)
    retrieved_at = utc_now_iso()
    records: list[dict[str, Any]] = []
    for row in filtered:
        geo_name = _geo_name(row, metadata)
        indicator_name = _indicator_name(row, metadata) or indicator or str(source_card.get("title") or "")
        unit = (
            _optional_text(row.get(metadata["unit_column"]))
            if metadata.get("unit_column")
            else None
        ) or _optional_text(source_card.get("units"))
        dimensions = {
            column: row.get(column)
            for column in metadata["dimension_columns"]
            if column not in {metadata.get("geo_column"), metadata.get("indicator_column"), metadata.get("unit_column")}
        }
        for period in period_columns:
            value = _coerce_value(row.get(period))
            quality_flags = []
            if value in (None, ""):
                quality_flags.append("missing_value")
            records.append(
                {
                    "source": "fedstat",
                    "dataset_id": str(source_card.get("dataset_id") or ""),
                    "indicator_id": str(source_card.get("dataset_id") or ""),
                    "indicator_name": indicator_name,
                    "geo_id": geo_name,
                    "geo_name": geo_name,
                    "period": period,
                    "period_type": _period_type(period, source_card),
                    "value": value,
                    "unit": unit,
                    "dimensions": dimensions,
                    "source_url": source_url,
                    "retrieved_at": retrieved_at,
                    "quality_flags": quality_flags,
                }
            )

    dataset = DatasetArtifact(
        artifact_id=artifact_id,
        status="ok",
        source_id=str(source_card.get("dataset_id") or ""),
        rows=len(records),
        columns=CANONICAL_DATASET_COLUMNS,
        records=records,
        provenance=[
            {
                "source": "fedstat",
                "source_url": source_url,
                "resource_id": source_card.get("resource_id"),
                "retrieved_at": retrieved_at,
            }
        ],
        quality_flags=["deterministic_fedstat_adapter"],
    )
    return export_csv_parquet_manifest(dataset, output_dir=output_dir)


def _load_normalized_rows(source_card: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = _parquet_path(source_card)
    parquet = pq.ParquetFile(path)
    physical_columns = list(parquet.schema_arrow.names)
    table = parquet.read()
    connection = duckdb.connect(database=":memory:")
    try:
        connection.register("fedstat_raw", table)
        cursor = connection.execute("SELECT * FROM fedstat_raw")
        rows = [dict(zip(physical_columns, row, strict=True)) for row in cursor.fetchall()]
    finally:
        connection.close()

    first_row_header = bool(rows and _has_technical_columns(physical_columns))
    if first_row_header:
        logical_columns = [_safe_column_name(value, index) for index, value in enumerate(rows[0].values())]
        rows = [dict(zip(logical_columns, row.values(), strict=True)) for row in rows[1:]]
    else:
        logical_columns = physical_columns

    period_columns = [column for column in logical_columns if re.fullmatch(r"\d{4}", str(column))]
    indicator_column = _find_column(logical_columns, ("indicator", "показатель", "name"))
    geo_column = _find_column(logical_columns, ("geo", "region", "country", "territory", "террит", "регион"))
    unit_column = _find_column(logical_columns, ("unit", "единиц", "measure"))
    dimension_columns = [column for column in logical_columns if column not in period_columns]
    return rows, {
        "physical_columns": physical_columns,
        "logical_columns": logical_columns,
        "first_row_header": first_row_header,
        "period_columns": period_columns,
        "indicator_column": indicator_column,
        "geo_column": geo_column,
        "unit_column": unit_column,
        "dimension_columns": dimension_columns,
    }


def _filter_rows(
    rows: list[dict[str, Any]],
    *,
    indicator: str | None = None,
    geography: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not indicator and not geography:
        return rows
    result = rows
    if indicator:
        needle = indicator.casefold()
        indicator_column = metadata.get("indicator_column") if metadata else None
        result = [
            row
            for row in result
            if needle in (_optional_text(row.get(indicator_column)) or "").casefold()
            or any(needle == (_optional_text(value) or "").casefold() for value in row.values())
        ]
    if geography and metadata:
        needle = geography.casefold()
        result = [row for row in result if _geo_name(row, metadata).casefold() == needle]
    return result


def _parquet_path(source_card: dict[str, Any]) -> Path:
    candidates = [
        source_card.get("local_path"),
        source_card.get("parquet_path"),
        source_card.get("resource_id"),
    ]
    metadata = source_card.get("metadata")
    if isinstance(metadata, dict):
        candidates.extend([metadata.get("local_path"), metadata.get("parquet_path")])
    for candidate in candidates:
        if candidate:
            path = Path(str(candidate))
            if path.exists():
                return path
    raise FileNotFoundError(f"No readable FedStat parquet path in source card: {source_card!r}")


def _has_technical_columns(columns: list[str]) -> bool:
    return all(re.fullmatch(r"column0*\d+", column) for column in columns)


def _safe_column_name(value: Any, index: int) -> str:
    text = _optional_text(value)
    return text or f"column_{index}"


def _find_column(columns: list[str], needles: tuple[str, ...]) -> str | None:
    for column in columns:
        lowered = column.casefold()
        if any(needle in lowered for needle in needles):
            return column
    return None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _geo_name(row: dict[str, Any], metadata: dict[str, Any]) -> str:
    geo_column = metadata.get("geo_column")
    return _optional_text(row.get(geo_column)) if geo_column else ""


def _indicator_name(row: dict[str, Any], metadata: dict[str, Any]) -> str | None:
    indicator_column = metadata.get("indicator_column")
    return _optional_text(row.get(indicator_column)) if indicator_column else None


def _source_url(source_card: dict[str, Any]) -> str | None:
    return _optional_text(source_card.get("provenance_url")) or _optional_text(source_card.get("source_url"))


def _coerce_value(value: Any) -> int | float | str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip().replace(" ", "")
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+[,.]\d+", text):
        return float(text.replace(",", "."))
    return value


def _period_type(period: str, source_card: dict[str, Any]) -> str:
    frequency = (_optional_text(source_card.get("frequency")) or "").casefold()
    if "quarter" in frequency or "кварт" in frequency:
        return "quarter"
    if "month" in frequency or "меся" in frequency:
        return "month"
    if re.fullmatch(r"\d{4}", period):
        return "year"
    return frequency or "period"
