"""Coverage preview node for Phase 2 workflow.

Two-phase process per ARCHITECTURE_STACK.md:
1. Deterministic: route each source card to the adapter for real metadata inspection.
2. LLM: Qwen assesses the collected coverage maps — best slice, alternatives,
   risks, whether to continue without asking the user — and updates report status/evidence.
"""
from __future__ import annotations

from typing import Any

from app.artifacts.workflow_artifacts import CoverageReport, EvidenceBundleArtifact
from app.data.source_card_lookup import hydrate_source_card


def run_coverage_preview(
    evidence: EvidenceBundleArtifact,
    *,
    intent_fields: dict[str, Any],
    live_llm_required: bool = True,
) -> list[CoverageReport]:
    """Run coverage preview for each selected source card.

    Phase 1 — deterministic adapter inspection per source_family.
    Phase 2 — LLM (Qwen) assesses coverage quality, proposes best slice,
               alternatives, and whether extraction can proceed.
    """
    reports: list[CoverageReport] = []
    for source_card in evidence.selected_sources:
        report = _preview_one_source(source_card, intent_fields=intent_fields)
        reports.append(report)

    if live_llm_required and reports:
        reports = _llm_assess_coverage(reports, intent_fields=intent_fields)

    return reports


def _llm_assess_coverage(
    reports: list[CoverageReport],
    *,
    intent_fields: dict[str, Any],
) -> list[CoverageReport]:
    """Ask Qwen to assess coverage quality and enrich reports.

    Per ARCHITECTURE_STACK.md Coverage & Schema Agent:
    - best available slice
    - alternative slices
    - quality trade-offs
    - whether to continue without asking user
    - methodology risks
    """
    try:
        from pydantic import BaseModel
        from app.llm.yandex_ai_studio import YandexAIStudioClient, qwen_credential_gate

        gate = qwen_credential_gate()
        if gate["status"] == "gated_skip":
            return reports

        class _CoverageAssessment(BaseModel):
            source_id: str = ""
            can_proceed: bool = True
            best_slice: str = ""
            alternative_slices: list[str] = []
            quality_risks: list[str] = []
            ask_user: bool = False
            ask_user_reason: str = ""

        class _CoverageAssessmentList(BaseModel):
            assessments: list[_CoverageAssessment] = []

        coverage_summaries = [
            {
                "source_id": r.source_id,
                "status": r.status,
                "checks": r.checks[:10],
                "available_periods": r.available_periods[:10],
                "available_geographies": r.available_geographies[:10],
                "unit": r.unit,
                "frequency": r.frequency,
                "evidence": {k: v for k, v in (r.evidence or {}).items()
                             if k in ("source_specific_risks", "missing_values_pct",
                                      "period_range", "coverage_pct")},
            }
            for r in reports
        ]

        client = YandexAIStudioClient()
        result = client.structured_chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Ты — Coverage & Schema Agent DataAgent. "
                        "Оцени покрытие источников и определи: "
                        "можно ли продолжить извлечение данных, какой срез лучший, "
                        "какие есть риски и нужно ли уточнение у пользователя. "
                        "Отвечай строго в формате JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Запрос: {intent_fields}\n"
                        f"Покрытие источников:\n{coverage_summaries}"
                    ),
                },
            ],
            schema=_CoverageAssessmentList,
            temperature=0.0,
            max_tokens=1024,
        )

        # Merge LLM assessments back into CoverageReports
        assessment_map = {a.source_id: a for a in result.assessments}
        enriched: list[CoverageReport] = []
        for report in reports:
            assessment = assessment_map.get(report.source_id)
            if assessment:
                evidence = dict(report.evidence or {})
                evidence["llm_best_slice"] = assessment.best_slice
                evidence["llm_alternative_slices"] = assessment.alternative_slices
                evidence["llm_quality_risks"] = assessment.quality_risks
                evidence["llm_ask_user"] = assessment.ask_user
                if assessment.ask_user_reason:
                    evidence["llm_ask_user_reason"] = assessment.ask_user_reason
                # Override status if LLM says cannot proceed
                status = report.status
                if not assessment.can_proceed and status == "ok":
                    status = "skipped_with_reason"
                enriched.append(report.model_copy(update={"evidence": evidence, "status": status}))
            else:
                enriched.append(report)
        return enriched

    except Exception:
        # LLM assessment failed — return deterministic reports as-is
        return reports


def _preview_one_source(
    source_card: dict[str, Any],
    *,
    intent_fields: dict[str, Any],
) -> CoverageReport:
    """Dispatch coverage preview to the correct adapter by source_family."""
    source_card = hydrate_source_card(source_card)
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
        periods = intent_fields.get("periods") or intent_fields.get("period") or []
        if isinstance(periods, str):
            periods = [periods]
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
