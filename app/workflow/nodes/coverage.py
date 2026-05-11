"""Coverage preview node for Phase 2 workflow.

Two-phase process per ARCHITECTURE_STACK.md:
1. Deterministic: route each source card to the adapter for real metadata inspection.
2. LLM: Qwen assesses the collected coverage maps — best slice, alternatives,
   risks, whether to continue without asking the user — and updates report status/evidence.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.artifacts.workflow_artifacts import (
    CoverageReport,
    EvidenceBundleArtifact,
    IntentFrame,
    ResearchDesignArtifact,
    SourceCandidate,
)
from app.data.source_card_lookup import hydrate_source_card


class CoverageInput(BaseModel):
    """Typed input for coverage while retaining legacy function arguments."""

    evidence: EvidenceBundleArtifact
    intent: IntentFrame | None = None
    research_design: ResearchDesignArtifact | None = None
    intent_fields: dict[str, Any] = Field(default_factory=dict)
    live_llm_required: bool = True

    model_config = ConfigDict(extra="forbid")


def run_coverage_preview(
    evidence: EvidenceBundleArtifact | CoverageInput,
    *,
    intent_fields: dict[str, Any] | None = None,
    intent: IntentFrame | None = None,
    research_design: ResearchDesignArtifact | None = None,
    live_llm_required: bool = True,
) -> list[CoverageReport]:
    """Run coverage preview for each selected source card.

    Phase 1 — deterministic adapter inspection per source_family.
    Phase 2 — LLM (Qwen) assesses coverage quality, proposes best slice,
               alternatives, and whether extraction can proceed.
    """
    coverage_input = _coerce_coverage_input(
        evidence,
        intent_fields=intent_fields,
        intent=intent,
        research_design=research_design,
        live_llm_required=live_llm_required,
    )
    fields = coverage_input.intent_fields
    reports: list[CoverageReport] = []
    for source_candidate in coverage_input.evidence.selected_for_coverage:
        source_card = source_candidate.model_dump(exclude_none=True)
        report = _preview_one_source(source_card, intent_fields=fields)
        reports.append(_attach_candidate_contract(report, source_candidate))

    if coverage_input.live_llm_required and reports:
        reports = _llm_assess_coverage(reports, intent_fields=fields)

    return reports


def aggregate_coverage_status(reports: list[CoverageReport], *, had_sources: bool) -> str:
    """Return a graph component status from per-source coverage reports."""
    if not had_sources:
        return "skipped_no_sources"
    if not reports:
        return "no_covered_slice"
    statuses = {report.status for report in reports}
    if any(
        report.status == "ok"
        and (report.extraction_ready is not False)
        and not report.extraction_blockers
        for report in reports
    ):
        return "partial" if statuses & {"gated", "skipped_with_reason", "no_covered_slice"} else "ok"
    if statuses <= {"gated"}:
        return "gated"
    if statuses <= {"skipped_no_sources"}:
        return "skipped_no_sources"
    return "no_covered_slice"


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
            return [
                _mark_llm_coverage_failure(
                    report,
                    reason="llm_coverage_gated",
                    detail=f"missing_env_vars:{gate.get('missing_env_vars', [])}",
                )
                for report in reports
            ]

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
                extraction_ready = report.extraction_ready and status == "ok" and not assessment.ask_user
                blockers = list(report.extraction_blockers)
                if not extraction_ready and "llm_coverage_not_ready" not in blockers:
                    blockers.append("llm_coverage_not_ready")
                enriched.append(
                    report.model_copy(
                        update={
                            "evidence": evidence,
                            "status": status,
                            "extraction_ready": extraction_ready,
                            "extraction_blockers": blockers,
                        }
                    )
                )
            else:
                enriched.append(report)
        return enriched

    except Exception as exc:
        return [
            _mark_llm_coverage_failure(report, reason="llm_coverage_error", detail=str(exc))
            for report in reports
        ]


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
        extraction_ready=False,
        extraction_blockers=[f"unknown_source_family:{family}"],
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
        return report.model_copy(
            update={
                "evidence": evidence,
                "extraction_ready": report.status == "ok",
                "extraction_blockers": [] if report.status == "ok" else ["fedstat_coverage_not_ok"],
            }
        )
    except FileNotFoundError as exc:
        return CoverageReport(
            source_id=str(source_card.get("dataset_id") or source_card.get("card_id") or "fedstat"),
            status="gated",
            extraction_ready=False,
            extraction_blockers=["fedstat_local_parquet_unavailable"],
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
            extraction_ready=False,
            extraction_blockers=["fedstat_coverage_preview_error"],
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
        return report.model_copy(
            update={
                "evidence": evidence,
                "extraction_ready": report.status == "ok",
                "extraction_blockers": [] if report.status == "ok" else ["world_bank_coverage_not_ok"],
            }
        )
    except FileNotFoundError as exc:
        return CoverageReport(
            source_id=str(source_card.get("dataset_id") or source_card.get("card_id") or "world_bank"),
            status="gated",
            extraction_ready=False,
            extraction_blockers=["world_bank_local_parquet_unavailable"],
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
            extraction_ready=False,
            extraction_blockers=["world_bank_coverage_preview_error"],
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
        blockers = list(evidence.get("source_specific_risks") or [])
        ready = report.status == "ok" and "no_supported_format_for_deterministic_extraction" not in blockers
        return report.model_copy(
            update={
                "evidence": evidence,
                "extraction_ready": ready,
                "extraction_blockers": [] if ready else blockers or ["ckan_coverage_not_ok"],
            }
        )
    except Exception as exc:
        return CoverageReport(
            source_id=str(source_card.get("dataset_id") or source_card.get("card_id") or "ckan"),
            status="skipped_with_reason",
            extraction_ready=False,
            extraction_blockers=["ckan_coverage_preview_error"],
            checks=["ckan_coverage_error"],
            available_periods=[],
            available_geographies=[],
            evidence={
                "source_specific_risks": ["ckan_coverage_preview_error"],
                "error": str(exc),
            },
            gated_reason=f"ckan preview error: {exc}",
        )


def _coerce_coverage_input(
    evidence: EvidenceBundleArtifact | CoverageInput,
    *,
    intent_fields: dict[str, Any] | None,
    intent: IntentFrame | None,
    research_design: ResearchDesignArtifact | None,
    live_llm_required: bool,
) -> CoverageInput:
    if isinstance(evidence, CoverageInput):
        return evidence
    fields = dict(intent_fields or {})
    if intent is not None:
        fields = {**dict(intent.known_fields or {}), **fields}
    return CoverageInput(
        evidence=evidence,
        intent=intent,
        research_design=research_design,
        intent_fields=fields,
        live_llm_required=live_llm_required,
    )


def _attach_candidate_contract(
    report: CoverageReport,
    source_candidate: SourceCandidate,
) -> CoverageReport:
    evidence = dict(report.evidence or {})
    evidence.setdefault("source_candidate_id", source_candidate.source_candidate_id)
    evidence.setdefault("retrieval_provenance", source_candidate.retrieval_provenance)
    blockers = list(report.extraction_blockers or [])
    blockers.extend(
        blocker for blocker in source_candidate.extraction_blockers
        if blocker not in blockers
    )
    extraction_ready = (
        report.extraction_ready
        and source_candidate.extraction_ready
        and report.status == "ok"
        and not blockers
    )
    return report.model_copy(
        update={
            "source_candidate_id": source_candidate.source_candidate_id,
            "source_family": source_candidate.source_family,
            "retrieval_provenance": source_candidate.retrieval_provenance,
            "extraction_ready": extraction_ready,
            "extraction_blockers": blockers,
            "evidence": evidence,
        }
    )


def _mark_llm_coverage_failure(
    report: CoverageReport,
    *,
    reason: str,
    detail: str,
) -> CoverageReport:
    evidence = dict(report.evidence or {})
    evidence["llm_coverage_status"] = reason
    evidence["llm_coverage_detail"] = detail
    blockers = list(report.extraction_blockers or [])
    if reason not in blockers:
        blockers.append(reason)
    return report.model_copy(
        update={
            "status": "gated",
            "gated_reason": reason,
            "evidence": evidence,
            "extraction_ready": False,
            "extraction_blockers": blockers,
        }
    )
