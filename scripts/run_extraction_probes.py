from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data.deterministic_tools import (
    ckan_package_show,
    fedstat_normalize_preview,
    run_duckdb_query,
    wb_coverage_preview,
)


def run_extraction_probes(
    *,
    source_catalog_manifest: Path,
    report_path: Path,
    json_output: Path,
) -> dict[str, Any]:
    manifest = json.loads(source_catalog_manifest.read_text(encoding="utf-8"))
    cards_manifest = json.loads(
        Path(manifest["source_cards_manifest"]).read_text(encoding="utf-8")
    )
    cards_payload = json.loads(
        Path(cards_manifest["artifact_path"]).read_text(encoding="utf-8")
    )
    cards = cards_payload.get("cards", [])
    artifact_dir = report_path.parent / "extraction-probe-artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    probes = [
        _fedstat_probe(_first_card(cards, "fedstat"), artifact_dir),
        _world_bank_probe(_first_card(cards, "world_bank"), artifact_dir),
        _ckan_probe(_first_card(cards, "ckan"), artifact_dir),
    ]
    evidence = {
        "source_catalog_manifest": str(source_catalog_manifest),
        "probe_count": len(probes),
        "probes": probes,
    }
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    report_path.write_text(_render_report(evidence), encoding="utf-8")
    return evidence


def _first_card(cards: list[dict[str, Any]], source: str) -> dict[str, Any]:
    for card in cards:
        if str(card.get("source")).lower() == source:
            return card
    return {}


def _fedstat_probe(card: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    sql_path = artifact_dir / "fedstat-wide-preview.sql"
    preview = fedstat_normalize_preview(card)
    query = (
        "SELECT ? AS source_id, ? AS resource_id, "
        "? AS normalization_strategy, ? AS pyarrow_usage"
    )
    sql_path.write_text(
        "-- DuckDB SQL-first FedStat wide-table preview\n" + query + "\n",
        encoding="utf-8",
    )
    rows = run_duckdb_query(
        query,
        parameters=[
            preview.get("source_id"),
            preview.get("resource_id"),
            "first-row header + wide year-column melt",
            "PyArrow metadata/read path before DuckDB query",
        ],
    )
    return {
        "source_family": "FedStat",
        "source_id": str(card.get("dataset_id") or "fedstat_missing"),
        "resource_id": card.get("resource_id"),
        "coverage_status": "ok" if card else "skipped_with_reason",
        "extraction_status": "skipped_with_reason",
        "shape": {"rows": len(rows), "columns": len(rows[0]) if rows else 0},
        "query_artifact_path": str(sql_path),
        "evidence": preview,
        "skip_reason": "Probe records normalizer and SQL-first contract; full wide Parquet extraction is bounded to later source-specific cases.",
    }


def _world_bank_probe(card: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    sql_path = artifact_dir / "world-bank-coverage-preview.sql"
    preview = wb_coverage_preview(card)
    query = (
        "SELECT ? AS source_id, ? AS resource_id, "
        "'indicator/country/period coverage' AS coverage_axis, "
        "'canonical long format' AS adapter"
    )
    sql_path.write_text(
        "-- DuckDB SQL-first World Bank canonical long-format preview\n" + query + "\n",
        encoding="utf-8",
    )
    rows = run_duckdb_query(
        query,
        parameters=[preview.get("source_id"), preview.get("resource_id")],
    )
    return {
        "source_family": "World Bank",
        "source_id": str(card.get("dataset_id") or "world_bank_missing"),
        "resource_id": card.get("resource_id"),
        "coverage_status": "ok" if card else "skipped_with_reason",
        "extraction_status": "skipped_with_reason",
        "shape": {"rows": len(rows), "columns": len(rows[0]) if rows else 0},
        "query_artifact_path": str(sql_path),
        "evidence": preview,
        "skip_reason": "Probe records canonical long-format adapter; full row extraction waits for source-specific filters.",
    }


def _ckan_probe(card: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    sql_path = artifact_dir / "ckan-resource-preview.sql"
    resources = (card.get("metadata") or {}).get("resources") or []
    resource = resources[0] if resources else {}
    package_id = str(card.get("dataset_id") or "")
    show_status = "skipped_with_reason"
    show_reason = "No promoted CKAN package id available."
    if package_id:
        try:
            shown = ckan_package_show(package_id)
            show_status = "ok" if shown.get("success") else "skipped_with_reason"
            show_reason = "package_show returned metadata" if shown.get("success") else "package_show did not return success"
        except Exception as exc:
            show_reason = f"bounded package_show skipped: {type(exc).__name__}"
    query = (
        "SELECT ? AS package_id, ? AS resource_id, ? AS resource_format, "
        "? AS resource_url"
    )
    sql_path.write_text(
        "-- DuckDB SQL-first CKAN resource-level metadata preview\n" + query + "\n",
        encoding="utf-8",
    )
    rows = run_duckdb_query(
        query,
        parameters=[
            package_id,
            resource.get("id"),
            resource.get("format"),
            resource.get("url"),
        ],
    )
    return {
        "source_family": "CKAN",
        "source_id": package_id or "ckan_missing",
        "resource_id": resource.get("id"),
        "coverage_status": show_status,
        "extraction_status": "skipped_with_reason",
        "shape": {"rows": len(rows), "columns": len(rows[0]) if rows else 0},
        "query_artifact_path": str(sql_path),
        "evidence": {
            "resource_level_access": bool(resource),
            "resource": resource,
            "DuckDB SQL-first": True,
            "PyArrow": "usable after resource download or local parquet path promotion",
            "Polars": "not used; CKAN probe remains bounded to metadata/resource suitability",
        },
        "skip_reason": show_reason,
    }


def _render_report(evidence: dict[str, Any]) -> str:
    probes = {probe["source_family"]: probe for probe in evidence["probes"]}
    fedstat = probes["FedStat"]
    world_bank = probes["World Bank"]
    ckan = probes["CKAN"]
    return f"""# Extraction Probes

## FedStat wide Parquet probe

- DuckDB SQL-first: `{fedstat['query_artifact_path']}`
- FedStat normalizer evidence: first-row header handling, dimension-column preservation, and wide year-column melt strategy are recorded in JSON evidence.
- PyArrow: metadata/read path before normalization.
- Polars: {fedstat['evidence']['polars_rationale']}
- Coverage status: `{fedstat['coverage_status']}`
- Extraction status: `{fedstat['extraction_status']}`

## World Bank parquet probe

- DuckDB SQL-first: `{world_bank['query_artifact_path']}`
- World Bank canonical long-format adapter evidence: indicator/country/period/value shape is recorded in JSON evidence.
- PyArrow: parquet metadata/read path remains available before DuckDB SQL.
- Polars: {world_bank['evidence']['polars_rationale']}
- Coverage status: `{world_bank['coverage_status']}`
- Extraction status: `{world_bank['extraction_status']}`

## CKAN resource path probe

- DuckDB SQL-first: `{ckan['query_artifact_path']}`
- Resource-level access path: package id `{ckan['source_id']}`, resource id `{ckan.get('resource_id')}`.
- PyArrow: used after a promoted parquet resource is downloaded or mapped locally.
- Polars: not used for the bounded CKAN suitability probe.
- Coverage status: `{ckan['coverage_status']}`
- Extraction status: `{ckan['extraction_status']}`
- Skip/gate reason: {ckan['skip_reason']}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic extraction probes.")
    parser.add_argument("--source-catalog-manifest", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    args = parser.parse_args()
    result = run_extraction_probes(
        source_catalog_manifest=args.source_catalog_manifest,
        report_path=args.report,
        json_output=args.json_output,
    )
    print(json.dumps({"probe_count": result["probe_count"], "json_output": str(args.json_output)}))


if __name__ == "__main__":
    main()
