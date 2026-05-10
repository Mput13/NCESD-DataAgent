"""CKAN adapter for bounded trusted NSED catalog access.

Provides bounded discovery, promotion, coverage preview, and deterministic
extraction for supported CSV, CSV.GZ, and Parquet resources.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Union

import requests

from app.artifacts.workflow_artifacts import (
    CoverageReport,
    DatasetArtifact,
    NoDataExplanationArtifact,
    utc_now_iso,
)
from app.data.deterministic_tools import ckan_package_search, ckan_package_show
from app.data.fedstat_adapter import CANONICAL_DATASET_COLUMNS

# Only these formats support deterministic extraction
_SUPPORTED_FORMATS = {"csv", "csv.gz", "parquet"}

_MAX_SEARCH_ROWS = 5
_MAX_PROMOTED_RESOURCES = 20

_NO_SUPPORT_REASON = "ckan_resource_format_not_supported_for_deterministic_extraction"


def search_ckan_source_cards(
    query: str,
    *,
    rows: int = 5,
) -> list[dict[str, Any]]:
    """Bounded CKAN package_search returning compressed source-card dicts.

    Always caps rows at 5 regardless of the caller-supplied value.
    """
    rows = min(rows, _MAX_SEARCH_ROWS)
    payload = ckan_package_search(query, rows=rows)
    results = payload.get("results") or []
    cards: list[dict[str, Any]] = []
    for pkg in results[:rows]:
        cards.append(_compress_package_to_card(pkg))
    return cards


def promote_ckan_package(
    package_id: str,
    *,
    cache_dir: Path = Path(".local/dataagent/phase2/ckan-cache"),
) -> dict[str, Any]:
    """Call package_show and return a promoted dict with compressed metadata.

    Caches the raw JSON response under cache_dir (not committed).
    Caps promoted resources at 20.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{package_id}.json"

    raw: dict[str, Any]
    if cache_file.exists():
        raw = json.loads(cache_file.read_text(encoding="utf-8"))
    else:
        payload = ckan_package_show(package_id)
        raw = payload.get("result") or payload
        cache_file.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    resources: list[dict[str, Any]] = raw.get("resources") or []
    total_resource_count = len(resources)
    promoted_resources = resources[:_MAX_PROMOTED_RESOURCES]

    formats = sorted({str(r.get("format") or "").strip().upper() for r in promoted_resources if r.get("format")})

    return {
        "source_family": "ckan",
        "dataset_id": str(raw.get("id") or package_id),
        "title": str(raw.get("title") or ""),
        "notes": str(raw.get("notes") or "")[:500],
        "formats": formats,
        "resource_count": total_resource_count,
        "promoted_resources": [_compress_resource(r) for r in promoted_resources],
        "provenance_url": str(raw.get("url") or f"https://repository.nsedc.ru/dataset/{package_id}"),
        "why_matched": "",
        "risk_flags": _detect_risk_flags(promoted_resources),
    }


def preview_ckan_coverage(
    promoted: dict[str, Any],
) -> CoverageReport:
    """Return a CoverageReport for a promoted CKAN package without extraction.

    Does not download data; inspects promoted metadata only.
    """
    source_id = str(promoted.get("dataset_id") or "ckan_unknown")
    formats = promoted.get("formats") or []
    promoted_resources = promoted.get("promoted_resources") or []

    supported = [
        r for r in promoted_resources
        if str(r.get("format") or "").lower().strip() in _SUPPORTED_FORMATS
    ]

    risk_flags = list(promoted.get("risk_flags") or [])
    if not supported:
        risk_flags.append("no_supported_format_for_deterministic_extraction")
        status: str = "skipped_with_reason"
    else:
        status = "ok"

    return CoverageReport(
        source_id=source_id,
        status=status,  # type: ignore[arg-type]
        checks=[
            "ckan_package_show_metadata_inspected",
            f"formats_found:{','.join(formats) or 'none'}",
        ],
        available_periods=[],
        available_geographies=[],
        unit=None,
        frequency=None,
        evidence={
            "resource_count": promoted.get("resource_count", 0),
            "supported_resources": len(supported),
            "formats": formats,
            "source_specific_risks": risk_flags,
        },
        gated_reason="no_supported_format" if not supported else None,
    )


def extract_ckan_dataset(
    promoted: dict[str, Any],
    *,
    resource_id: str,
    filters: dict[str, Any],
    output_dir: Path,
    artifact_id: str,
) -> Union[DatasetArtifact, NoDataExplanationArtifact]:
    """Deterministically extract a promoted CKAN resource.

    Supports CSV, CSV.GZ, and Parquet formats. Returns
    NoDataExplanationArtifact for unsupported formats.
    """
    promoted_resources = promoted.get("promoted_resources") or []
    # Find the specific resource
    resource: dict[str, Any] | None = None
    for r in promoted_resources:
        if str(r.get("id") or "") == resource_id:
            resource = r
            break

    if resource is None:
        # Try by matching any available resource if resource_id not found
        for r in promoted_resources:
            resource = r
            break

    if resource is None:
        return NoDataExplanationArtifact(
            artifact_id=artifact_id,
            checked_sources=[{"dataset_id": promoted.get("dataset_id"), "resource_id": resource_id}],
            rejected_sources=[{"dataset_id": promoted.get("dataset_id"), "resource_id": resource_id}],
            rejection_reasons=[_NO_SUPPORT_REASON, "resource_not_found_in_promoted_package"],
            search_strategy="ckan_promoted_resource_lookup",
            alternatives=[],
            limitations=["Resource ID not found in promoted package"],
        )

    fmt = str(resource.get("format") or "").lower().strip()
    if fmt not in _SUPPORTED_FORMATS:
        return NoDataExplanationArtifact(
            artifact_id=artifact_id,
            checked_sources=[{"dataset_id": promoted.get("dataset_id"), "resource_id": resource_id, "format": fmt}],
            rejected_sources=[{"dataset_id": promoted.get("dataset_id"), "resource_id": resource_id, "format": fmt}],
            rejection_reasons=[_NO_SUPPORT_REASON],
            search_strategy="ckan_promoted_resource_extraction",
            alternatives=[],
            limitations=[f"Format '{fmt}' is not supported for deterministic extraction. Supported: {sorted(_SUPPORTED_FORMATS)}"],
        )

    # Proceed with deterministic extraction
    url = str(resource.get("url") or "")
    return _extract_supported_resource(
        promoted=promoted,
        resource=resource,
        url=url,
        fmt=fmt,
        filters=filters,
        output_dir=output_dir,
        artifact_id=artifact_id,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compress_package_to_card(pkg: dict[str, Any]) -> dict[str, Any]:
    """Compress a raw CKAN package dict to a bounded source-card dict."""
    resources: list[dict[str, Any]] = pkg.get("resources") or []
    formats = sorted({str(r.get("format") or "").strip().upper() for r in resources if r.get("format")})
    first_resource_id = resources[0].get("id") if resources else None
    return {
        "source_family": "ckan",
        "dataset_id": str(pkg.get("id") or ""),
        "resource_id": first_resource_id,
        "title": str(pkg.get("title") or "")[:300],
        "formats": formats,
        "resource_count": len(resources),
        "provenance_url": str(pkg.get("url") or f"https://repository.nsedc.ru/dataset/{pkg.get('id', '')}"),
        "why_matched": "",
        "risk_flags": _detect_risk_flags(resources),
    }


def _compress_resource(resource: dict[str, Any]) -> dict[str, Any]:
    """Return a bounded dict for a single CKAN resource."""
    return {
        "id": str(resource.get("id") or ""),
        "format": str(resource.get("format") or "").upper(),
        "url": str(resource.get("url") or ""),
        "name": str(resource.get("name") or ""),
    }


def _detect_risk_flags(resources: list[dict[str, Any]]) -> list[str]:
    flags: list[str] = []
    formats_lower = {str(r.get("format") or "").lower() for r in resources}
    has_supported = bool(formats_lower.intersection(_SUPPORTED_FORMATS))
    if not has_supported:
        flags.append("no_supported_format_for_deterministic_extraction")
    if "xls" in formats_lower or "xlsx" in formats_lower:
        flags.append("excel_format_not_deterministically_extractable")
    if "pdf" in formats_lower:
        flags.append("pdf_format_not_extractable")
    return flags


def _extract_supported_resource(
    *,
    promoted: dict[str, Any],
    resource: dict[str, Any],
    url: str,
    fmt: str,
    filters: dict[str, Any],
    output_dir: Path,
    artifact_id: str,
) -> Union[DatasetArtifact, NoDataExplanationArtifact]:
    """Download and parse a supported resource deterministically."""
    output_dir.mkdir(parents=True, exist_ok=True)
    retrieved_at = utc_now_iso()

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        raw_bytes = response.content
    except Exception as exc:
        return NoDataExplanationArtifact(
            artifact_id=artifact_id,
            checked_sources=[{"dataset_id": promoted.get("dataset_id"), "resource_id": resource.get("id")}],
            rejected_sources=[{"dataset_id": promoted.get("dataset_id"), "resource_id": resource.get("id"), "error": str(exc)}],
            rejection_reasons=["ckan_resource_download_failed"],
            search_strategy="ckan_deterministic_extraction",
            alternatives=[],
            limitations=[f"Download failed: {exc}"],
        )

    try:
        if fmt == "parquet":
            records = _parse_parquet_bytes(raw_bytes, filters=filters)
        else:
            # csv or csv.gz
            if fmt == "csv.gz":
                import gzip
                raw_bytes = gzip.decompress(raw_bytes)
            text = raw_bytes.decode("utf-8", errors="replace")
            records = _parse_csv_text(text, filters=filters)
    except Exception as exc:
        return NoDataExplanationArtifact(
            artifact_id=artifact_id,
            checked_sources=[{"dataset_id": promoted.get("dataset_id"), "resource_id": resource.get("id")}],
            rejected_sources=[{"dataset_id": promoted.get("dataset_id"), "resource_id": resource.get("id"), "parse_error": str(exc)}],
            rejection_reasons=["ckan_resource_parse_failed"],
            search_strategy="ckan_deterministic_extraction",
            alternatives=[],
            limitations=[f"Parse failed: {exc}"],
        )

    # Build canonical records matching CANONICAL_DATASET_COLUMNS
    canonical_records = _to_canonical_records(records, promoted=promoted, retrieved_at=retrieved_at)

    dataset = DatasetArtifact(
        artifact_id=artifact_id,
        status="ok",
        source_id=str(promoted.get("dataset_id") or ""),
        rows=len(canonical_records),
        columns=CANONICAL_DATASET_COLUMNS,
        records=canonical_records,
        provenance=[{
            "source": "ckan",
            "dataset_id": promoted.get("dataset_id"),
            "resource_id": resource.get("id"),
            "url": url,
            "retrieved_at": retrieved_at,
        }],
        quality_flags=["deterministic_ckan_adapter", f"format:{fmt}"],
    )

    # Export CSV + manifest
    stem = artifact_id.replace(":", "_").replace("/", "_")
    csv_path = output_dir / f"{stem}.csv"
    import csv as csv_module
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv_module.DictWriter(fh, fieldnames=CANONICAL_DATASET_COLUMNS)
        writer.writeheader()
        writer.writerows(canonical_records)

    return dataset.model_copy(update={"csv_path": str(csv_path)})


def _parse_csv_text(text: str, *, filters: dict[str, Any]) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    rows = [dict(row) for row in reader]
    return rows


def _parse_parquet_bytes(raw_bytes: bytes, *, filters: dict[str, Any]) -> list[dict[str, Any]]:
    import io as _io
    import pyarrow.parquet as pq

    table = pq.read_table(_io.BytesIO(raw_bytes))
    return table.to_pylist()


def _to_canonical_records(
    rows: list[dict[str, Any]],
    *,
    promoted: dict[str, Any],
    retrieved_at: str,
) -> list[dict[str, Any]]:
    """Convert raw parsed rows to CANONICAL_DATASET_COLUMNS format."""
    canonical: list[dict[str, Any]] = []
    dataset_id = str(promoted.get("dataset_id") or "")
    source_url = str(promoted.get("provenance_url") or "")

    for row in rows:
        # Attempt to map common column names to canonical schema
        record: dict[str, Any] = {
            "source": "ckan",
            "dataset_id": dataset_id,
            "indicator_id": _coerce_field(row, ("indicator_id", "indicator", "code", "series_code")),
            "indicator_name": _coerce_field(row, ("indicator_name", "indicator", "name", "title", "series_name")),
            "geo_id": _coerce_field(row, ("geo_id", "country_id", "country_code", "region_id", "geo")),
            "geo_name": _coerce_field(row, ("geo_name", "country_name", "country", "region", "geo")),
            "period": _coerce_field(row, ("period", "date", "year", "time")),
            "period_type": "year",
            "value": _coerce_numeric(row, ("value", "val", "data")),
            "unit": _coerce_field(row, ("unit", "units", "measure")),
            "dimensions": {k: v for k, v in row.items() if k not in {
                "indicator_id", "indicator", "code", "series_code",
                "indicator_name", "name", "title", "series_name",
                "geo_id", "country_id", "country_code", "region_id",
                "geo_name", "country_name", "country", "region",
                "period", "date", "year", "time", "value", "val",
                "unit", "units", "measure",
            }},
            "source_url": source_url,
            "retrieved_at": retrieved_at,
            "quality_flags": [],
        }
        canonical.append(record)
    return canonical


def _coerce_field(row: dict[str, Any], candidates: tuple[str, ...]) -> str | None:
    for key in candidates:
        # Case-insensitive lookup
        for k, v in row.items():
            if k.casefold() == key.casefold() and v is not None:
                text = str(v).strip()
                if text:
                    return text
    return None


def _coerce_numeric(row: dict[str, Any], candidates: tuple[str, ...]) -> int | float | str | None:
    val = _coerce_field(row, candidates)
    if val is None:
        return None
    try:
        cleaned = val.replace(",", "").replace(" ", "")
        if "." in cleaned:
            return float(cleaned)
        return int(cleaned)
    except (ValueError, AttributeError):
        return val
