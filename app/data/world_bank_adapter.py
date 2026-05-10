from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any
import zipfile

import duckdb
import pyarrow.parquet as pq

from app.artifacts.workflow_artifacts import CoverageReport, DatasetArtifact, utc_now_iso
from app.data.deterministic_tools import export_csv_parquet_manifest
from app.data.fedstat_adapter import CANONICAL_DATASET_COLUMNS


COUNTRY_ALIASES = {
    "russia": "RUS",
    "россия": "RUS",
    "russian federation": "RUS",
    "kazakhstan": "KAZ",
    "казахстан": "KAZ",
    "china": "CHN",
    "китай": "CHN",
}
BRICS = ["BRA", "RUS", "IND", "CHN", "ZAF"]
EAEU = ["ARM", "BLR", "KAZ", "KGZ", "RUS"]
GROUP_ALIASES = {
    "brics": BRICS,
    "брикс": BRICS,
    "eaeu": EAEU,
    "еаэс": EAEU,
}
AGGREGATE_CODES = {
    "ARB",
    "CEB",
    "CSS",
    "EAP",
    "EAR",
    "EAS",
    "ECA",
    "ECS",
    "EMU",
    "EUU",
    "FCS",
    "HIC",
    "IBD",
    "IBT",
    "IDA",
    "IDB",
    "IDX",
    "LAC",
    "LCN",
    "LDC",
    "LIC",
    "LMC",
    "LMY",
    "LTE",
    "MEA",
    "MIC",
    "MNA",
    "NAC",
    "OED",
    "OSS",
    "PRE",
    "PSS",
    "PST",
    "SAS",
    "SSA",
    "SSF",
    "SST",
    "TEA",
    "TEC",
    "TLA",
    "TMN",
    "TSA",
    "TSS",
    "UMC",
    "WLD",
}


def preview_world_bank_coverage(
    source_card: dict[str, Any],
    *,
    countries: list[str],
    periods: list[str],
    indicator_id: str,
) -> CoverageReport:
    """Inspect actual World Bank long-format country/period coverage."""

    rows = _load_rows(source_card)
    country_codes = _resolve_countries(countries)
    requested_periods = {str(period) for period in periods}
    filtered = _filter_rows(
        rows,
        country_codes=country_codes,
        requested_countries=countries,
        periods=requested_periods,
        indicator_id=indicator_id,
    )
    available_periods = sorted({str(row["date"]) for row in filtered if row.get("value") is not None})
    available_geographies = sorted({str(row["country_id"]) for row in filtered if row.get("value") is not None})
    missing_values = sum(1 for row in filtered if row.get("value") is None)

    return CoverageReport(
        source_id=str(source_card.get("dataset_id") or indicator_id),
        status="ok",
        checks=[
            "pyarrow_parquet_metadata_read",
            "duckdb_rows_read",
            "world_bank_long_parquet_filtered",
            "world_bank_aggregate_rows_excluded",
        ],
        available_periods=available_periods,
        available_geographies=available_geographies,
        unit=_optional_text(source_card.get("units")),
        frequency=_optional_text(source_card.get("frequency")) or "annual",
        evidence={
            "missing_values": missing_values,
            "row_count": len(filtered),
            "requested_countries": country_codes,
            "source_path": str(_parquet_path(source_card)),
        },
    )


def extract_world_bank_dataset(
    source_card: dict[str, Any],
    *,
    countries: list[str],
    periods: list[str],
    indicator_id: str,
    output_dir: Path,
    artifact_id: str,
) -> DatasetArtifact:
    """Extract canonical World Bank long rows for requested countries and periods."""

    rows = _load_rows(source_card)
    country_codes = _resolve_countries(countries)
    filtered = _filter_rows(
        rows,
        country_codes=country_codes,
        requested_countries=countries,
        periods={str(period) for period in periods},
        indicator_id=indicator_id,
    )
    source_url = _source_url(source_card, indicator_id)
    retrieved_at = utc_now_iso()
    records = [
        {
            "source": "world_bank",
            "dataset_id": str(source_card.get("dataset_id") or indicator_id),
            "indicator_id": str(row.get("indicator_id") or indicator_id),
            "indicator_name": str(row.get("indicator_name") or source_card.get("title") or indicator_id),
            "geo_id": str(row.get("country_id")),
            "geo_name": str(row.get("country_name") or row.get("country_id")),
            "period": str(row.get("date")),
            "period_type": "year",
            "value": row.get("value"),
            "unit": _optional_text(source_card.get("units")),
            "dimensions": {"country_id": row.get("country_id")},
            "source_url": source_url,
            "retrieved_at": retrieved_at,
            "quality_flags": [] if row.get("value") is not None else ["missing_value"],
        }
        for row in filtered
    ]
    dataset = DatasetArtifact(
        artifact_id=artifact_id,
        status="ok",
        source_id=str(source_card.get("dataset_id") or indicator_id),
        rows=len(records),
        columns=CANONICAL_DATASET_COLUMNS,
        records=records,
        provenance=[
            {
                "source": "world_bank",
                "source_url": source_url,
                "resource_id": source_card.get("resource_id"),
                "retrieved_at": retrieved_at,
            }
        ],
        quality_flags=["deterministic_world_bank_adapter"],
    )
    return export_csv_parquet_manifest(dataset, output_dir=output_dir)


def normalize_first_available_to_100(
    dataset: DatasetArtifact,
    *,
    group_column: str = "geo_id",
) -> DatasetArtifact:
    """Normalize each geography/group so the first non-null period equals 100."""

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in dataset.records:
        grouped[str(record.get(group_column))].append(record)

    normalized_records: list[dict[str, Any]] = []
    for group, records in grouped.items():
        ordered = sorted(records, key=lambda item: str(item.get("period")))
        base = next((record.get("value") for record in ordered if record.get("value") not in (None, 0)), None)
        for record in ordered:
            output = dict(record)
            flags = list(output.get("quality_flags") or [])
            value = output.get("value")
            if base in (None, 0) or value is None:
                output["value"] = None
                flags.append("normalization_base_missing")
            else:
                output["value"] = _round_index(float(value) / float(base) * 100)
            output["indicator_name"] = f"{output.get('indicator_name')} (first available = 100)"
            output["unit"] = "index, first available = 100"
            output["dimensions"] = {
                **(output.get("dimensions") or {}),
                "normalization": "first_available_to_100",
                "normalization_group": group,
            }
            output["quality_flags"] = flags
            normalized_records.append(output)

    return dataset.model_copy(
        update={
            "artifact_id": f"{dataset.artifact_id}:normalized-first-available-100",
            "rows": len(normalized_records),
            "records": normalized_records,
            "quality_flags": [
                *dataset.quality_flags,
                "normalized_first_available_to_100",
            ],
        }
    )


def _load_rows(source_card: dict[str, Any]) -> list[dict[str, Any]]:
    path = _parquet_path(source_card)
    parquet = pq.ParquetFile(path)
    columns = list(parquet.schema_arrow.names)
    table = parquet.read()
    connection = duckdb.connect(database=":memory:")
    try:
        connection.register("world_bank_raw", table)
        cursor = connection.execute("SELECT * FROM world_bank_raw")
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    finally:
        connection.close()


def _filter_rows(
    rows: list[dict[str, Any]],
    *,
    country_codes: list[str],
    requested_countries: list[str],
    periods: set[str],
    indicator_id: str,
) -> list[dict[str, Any]]:
    requested_codes = set(country_codes)
    explicitly_requested_aggregates = {
        _resolve_country(country)
        for country in requested_countries
        if _resolve_country(country) in AGGREGATE_CODES or str(country).upper() in AGGREGATE_CODES
    }
    result = []
    for row in rows:
        row_indicator = str(row.get("indicator_id") or "")
        country_id = str(row.get("country_id") or row.get("countryiso3code") or "")
        period = str(row.get("date") or row.get("year") or "")
        if indicator_id and row_indicator and row_indicator != indicator_id:
            continue
        if requested_codes and country_id not in requested_codes:
            continue
        if periods and period not in periods:
            continue
        if country_id in AGGREGATE_CODES and country_id not in explicitly_requested_aggregates:
            continue
        row = dict(row)
        row["country_id"] = country_id
        row["date"] = period
        result.append(row)
    result.sort(key=lambda item: (str(item.get("country_id")), str(item.get("date"))))
    return result


def _resolve_countries(countries: list[str]) -> list[str]:
    resolved: list[str] = []
    for country in countries:
        key = str(country).strip().casefold()
        codes = GROUP_ALIASES.get(key)
        if codes is None:
            codes = [_resolve_country(country)]
        for code in codes:
            if code and code not in resolved:
                resolved.append(code)
    return resolved


def _resolve_country(country: str) -> str:
    text = str(country).strip()
    return COUNTRY_ALIASES.get(text.casefold(), text.upper())


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
    archived = _extract_archived_parquet(source_card)
    if archived is not None:
        return archived
    raise FileNotFoundError(f"No readable World Bank parquet path in source card: {source_card!r}")


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


def _source_url(source_card: dict[str, Any], indicator_id: str) -> str:
    return (
        _optional_text(source_card.get("provenance_url"))
        or _optional_text(source_card.get("source_url"))
        or f"https://api.worldbank.org/v2/indicator/{indicator_id}"
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _round_index(value: float) -> int | float:
    rounded = round(value, 6)
    if rounded.is_integer():
        return int(rounded)
    return rounded
