from __future__ import annotations

import re
import zipfile
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

    # Compute slice-level coverage
    requested_geo = _optional_text(filters.get("geography") or filters.get("geo_name")) or ""
    if requested_geo:
        aliases = _geography_aliases(requested_geo)
        matched_geos = [g for g in geographies if _geo_matches(g, aliases)]
        slice_rows = sum(
            1 for row in filtered
            if _geo_matches(_geo_name(row, metadata), aliases)
        )
    else:
        matched_geos = list(geographies)
        slice_rows = len(filtered)

    requested_periods_filter = {str(p) for p in (filters.get("periods") or [])}
    if requested_periods_filter:
        matched_periods = [p for p in period_columns if p in requested_periods_filter]
    else:
        matched_periods = list(period_columns)

    extraction_ready = slice_rows > 0

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
        matched_geographies=matched_geos,
        matched_periods=matched_periods,
        requested_slice_rows=slice_rows,
        extraction_ready=extraction_ready,
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
    geo_column = _find_column(logical_columns, ("geo", "region", "country", "territory", "террит", "регион", "окато", "оксм"))
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
        indicator_matches = [
            row
            for row in result
            if needle in (_optional_text(row.get(indicator_column)) or "").casefold()
            or any(needle == (_optional_text(value) or "").casefold() for value in row.values())
        ]
        if indicator_matches or indicator_column:
            result = indicator_matches
    if geography and metadata:
        aliases = _geography_aliases(geography)
        result = [row for row in result if _geo_matches(_geo_name(row, metadata), aliases)]
    return result


def resolve_fedstat_parquet_path(source_card: dict[str, Any]) -> Path:
    import os

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

    # Env-var fallback: look in FEDSTAT_DUMPS_DIR by dataset_id or resource_id
    dumps_dir_str = os.environ.get("FEDSTAT_DUMPS_DIR")
    if dumps_dir_str:
        dumps_dir = Path(dumps_dir_str)
        if dumps_dir.is_dir():
            for id_key in ("dataset_id", "resource_id", "card_id"):
                raw_id = source_card.get(id_key)
                if not raw_id:
                    continue
                # Try exact name and name + .parquet
                for name in [str(raw_id), f"{raw_id}.parquet"]:
                    candidate = dumps_dir / name
                    if candidate.exists():
                        return candidate

    archived = _extract_archived_parquet(source_card)
    if archived is not None:
        return archived
    raise FileNotFoundError(f"No readable FedStat parquet path in source card: {source_card!r}")


def _parquet_path(source_card: dict[str, Any]) -> Path:
    return resolve_fedstat_parquet_path(source_card)


def _extract_archived_parquet(source_card: dict[str, Any]) -> Path | None:
    member = _archive_member(source_card)
    if not member:
        return None
    for archive in source_card.get("local_paths") or []:
        archive_path = Path(str(archive))
        if not archive_path.exists() or archive_path.suffix.lower() != ".zip":
            continue
        try:
            with zipfile.ZipFile(archive_path) as zf:
                if member not in zf.namelist():
                    continue
                output = Path(".local/dataagent/phase1/extracted") / member
                output.parent.mkdir(parents=True, exist_ok=True)
                if not output.exists():
                    output.write_bytes(zf.read(member))
                return output
        except zipfile.BadZipFile:
            continue
    return None


def _archive_member(source_card: dict[str, Any]) -> str | None:
    resource_id = _optional_text(source_card.get("resource_id"))
    if resource_id and resource_id.endswith(".parquet"):
        return resource_id
    card_id = _optional_text(source_card.get("card_id"))
    if card_id:
        parts = card_id.split(":")
        for part in reversed(parts):
            if part.endswith(".parquet"):
                return part
    return None


def _has_technical_columns(columns: list[str]) -> bool:
    return all(re.fullmatch(r"column0*\d+", column) for column in columns)


def _safe_column_name(value: Any, index: int) -> str:
    text = _optional_text(value)
    if text:
        year = re.fullmatch(r"((?:19|20)\d{2})(?:\.0+)?", text)
        if year:
            return year.group(1)
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
    return _clean_geo_name(_optional_text(row.get(geo_column))) if geo_column else ""


def _clean_geo_name(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"\s+", " ", value).strip()
    text = re.sub(r"^\d+(?:[\w.]+)?\s+", "", text)
    return text.strip()


def _geography_aliases(geography: str) -> set[str]:
    normalized = _normalize_match_text(geography)
    aliases = {normalized}
    if normalized in {"russia", "russian federation", "россия", "российская федерация", "rf"}:
        aliases.update({"russia", "russian federation", "россия", "российская федерация"})
    return aliases


def _geo_matches(value: str, aliases: set[str]) -> bool:
    normalized = _normalize_match_text(value)
    if normalized in aliases:
        return True
    return any(alias and alias in normalized for alias in aliases)


def _normalize_match_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


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
