"""Coverage preview node for Phase 2 workflow.

run_coverage_preview routes each selected source card to the appropriate
adapter (FedStat, World Bank, or CKAN) and returns a list of CoverageReports.
"""
from __future__ import annotations

from typing import Any

from app.artifacts.workflow_artifacts import CoverageReport, EvidenceBundleArtifact


def run_coverage_preview(
    evidence: EvidenceBundleArtifact,
    *,
    intent_fields: dict[str, Any],
) -> list[CoverageReport]:
    """Run coverage preview for each selected source card.

    Routes by source_family:
    - 'fedstat' -> fedstat_adapter.preview_fedstat_coverage (if parquet available)
    - 'world_bank' -> world_bank_adapter.preview_world_bank_coverage
    - 'ckan' -> ckan_adapter.preview_ckan_coverage

    Always includes 'source_specific_risks' in the evidence dict.
    """
    reports: list[CoverageReport] = []
    for source_card in evidence.selected_sources:
        report = _preview_one_source(source_card, intent_fields=intent_fields)
        reports.append(report)
    return reports


def _preview_one_source(
    source_card: dict[str, Any],
    *,
    intent_fields: dict[str, Any],
) -> CoverageReport:
    """Dispatch coverage preview to the correct adapter by source_family."""
    family = str(source_card.get("source_family") or "").lower().strip()

    if family == "fedstat":
        return _fedstat_coverage(source_card, intent_fields=intent_fields)
    if family in ("world_bank", "worldbank"):
        return _world_bank_coverage(source_card, intent_fields=intent_fields)
    if family == "ckan":
        return _ckan_coverage(source_card)

    # Unknown family: return a skipped report with source_specific_risks
    return CoverageReport(
        source_id=str(source_card.get("card_id") or source_card.get("dataset_id") or "unknown"),
        status="skipped_with_reason",
        checks=["unknown_source_family"],
        available_periods=[],
        available_geographies=[],
        evidence={
            "source_specific_risks": [f"unknown_source_family:{family}"],
            "family": family,
        },
        gated_reason=f"source family '{family}' not supported",
    )


def _fedstat_coverage(
    source_card: dict[str, Any],
    *,
    intent_fields: dict[str, Any],
) -> CoverageReport:
    """Preview FedStat coverage if local parquet is available."""
    try:
        from app.data.fedstat_adapter import preview_fedstat_coverage
        filters = {
            "indicator": intent_fields.get("indicator") or intent_fields.get("indicator_name"),
            "geography": intent_fields.get("geography") or intent_fields.get("geo_name"),
        }
        report = preview_fedstat_coverage(source_card, filters=filters)
        # Ensure source_specific_risks is present
        evidence = dict(report.evidence)
        if "source_specific_risks" not in evidence:
            evidence["source_specific_risks"] = []
        return report.model_copy(update={"evidence": evidence})
    except FileNotFoundError as exc:
        return CoverageReport(
            source_id=str(source_card.get("dataset_id") or source_card.get("card_id") or "fedstat"),
            status="gated",
            checks=["fedstat_parquet_not_found"],
            available_periods=[],
            available_geographies=[],
            evidence={
                "source_specific_risks": ["fedstat_local_parquet_unavailable"],
                "error": str(exc),
            },
            gated_reason="local FedStat parquet not found",
        )
    except Exception as exc:
        return CoverageReport(
            source_id=str(source_card.get("dataset_id") or source_card.get("card_id") or "fedstat"),
            status="skipped_with_reason",
            checks=["fedstat_coverage_error"],
            available_periods=[],
            available_geographies=[],
            evidence={
                "source_specific_risks": ["fedstat_coverage_preview_error"],
                "error": str(exc),
            },
            gated_reason=f"fedstat preview error: {exc}",
        )


def _world_bank_coverage(
    source_card: dict[str, Any],
    *,
    intent_fields: dict[str, Any],
) -> CoverageReport:
    """Preview World Bank coverage if local parquet is available."""
    try:
        from app.data.world_bank_adapter import preview_world_bank_coverage
        countries = intent_fields.get("countries") or intent_fields.get("geography") or []
        if isinstance(countries, str):
            countries = [countries]
        periods = intent_fields.get("periods") or []
        indicator_id = str(
            intent_fields.get("indicator_id")
            or source_card.get("dataset_id")
            or source_card.get("card_id")
            or ""
        )
        report = preview_world_bank_coverage(
            source_card,
            countries=countries,
            periods=periods,
            indicator_id=indicator_id,
        )
        # Ensure source_specific_risks is present
        evidence = dict(report.evidence)
        if "source_specific_risks" not in evidence:
            evidence["source_specific_risks"] = []
        return report.model_copy(update={"evidence": evidence})
    except FileNotFoundError as exc:
        return CoverageReport(
            source_id=str(source_card.get("dataset_id") or source_card.get("card_id") or "world_bank"),
            status="gated",
            checks=["world_bank_parquet_not_found"],
            available_periods=[],
            available_geographies=[],
            evidence={
                "source_specific_risks": ["world_bank_local_parquet_unavailable"],
                "error": str(exc),
            },
            gated_reason="local World Bank parquet not found",
        )
    except Exception as exc:
        return CoverageReport(
            source_id=str(source_card.get("dataset_id") or source_card.get("card_id") or "world_bank"),
            status="skipped_with_reason",
            checks=["world_bank_coverage_error"],
            available_periods=[],
            available_geographies=[],
            evidence={
                "source_specific_risks": ["world_bank_coverage_preview_error"],
                "error": str(exc),
            },
            gated_reason=f"world bank preview error: {exc}",
        )


def _ckan_coverage(source_card: dict[str, Any]) -> CoverageReport:
    """Preview CKAN coverage from promoted package metadata."""
    try:
        from app.data.ckan_adapter import preview_ckan_coverage
        # Build a promoted-compatible dict from the source card
        promoted = {
            "dataset_id": source_card.get("dataset_id") or source_card.get("card_id") or "",
            "title": source_card.get("title") or "",
            "formats": source_card.get("formats") or [],
            "promoted_resources": source_card.get("promoted_resources") or [],
            "resource_count": source_card.get("resource_count") or 0,
            "provenance_url": source_card.get("provenance_url") or "",
            "risk_flags": source_card.get("risk_flags") or [],
        }
        report = preview_ckan_coverage(promoted)
        # Ensure source_specific_risks is present
        evidence = dict(report.evidence)
        if "source_specific_risks" not in evidence:
            evidence["source_specific_risks"] = list(promoted.get("risk_flags") or [])
        return report.model_copy(update={"evidence": evidence})
    except Exception as exc:
        return CoverageReport(
            source_id=str(source_card.get("dataset_id") or source_card.get("card_id") or "ckan"),
            status="skipped_with_reason",
            checks=["ckan_coverage_error"],
            available_periods=[],
            available_geographies=[],
            evidence={
                "source_specific_risks": ["ckan_coverage_preview_error"],
                "error": str(exc),
            },
            gated_reason=f"ckan preview error: {exc}",
        )
