"""Safe extraction planner node for Phase 2 workflow.

build_extraction_plan produces structured, allowlist-constrained extraction
plans from coverage reports. It never emits arbitrary user-provided SQL.

Dispatch keys:
- 'fedstat' -> extract_fedstat_dataset
- 'world_bank' -> extract_world_bank_dataset
- 'ckan' -> extract_ckan_dataset (for promoted supported resources)
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.artifacts.workflow_artifacts import (
    CoverageReport,
    ExtractionPlan,
    IntentFrame,
)

# Allowlist of safe extraction operations.
# Free-form SQL is NOT in this list — deterministic adapters compile SQL internally.
ALLOWED_OPERATIONS: frozenset[str] = frozenset({
    "coverage_preview",
    "filter_rows",
    "join_indicators",
    "normalize_index",
    "export_dataset",
})

# Dispatch map from source_family to deterministic extractor function name
_EXTRACTOR_DISPATCH: dict[str, str] = {
    "fedstat": "extract_fedstat_dataset",
    "world_bank": "extract_world_bank_dataset",
    "ckan": "extract_ckan_dataset",
}


def build_extraction_plan(
    intent: IntentFrame,
    coverage_reports: list[CoverageReport],
    *,
    live_llm_required: bool = True,
) -> ExtractionPlan:
    """Build a safe structured extraction plan from intent and coverage reports.

    Per ARCHITECTURE_STACK.md Extraction Planner Agent:
    LLM (Qwen) chooses which allowlist operations to apply and which filters to use.
    The allowlist guarantees safety; LLM provides the reasoning for the choice.

    Falls back to rule-based selection if LLM is unavailable.

    Returns:
    - status='ok' with allowlist operations when coverage is sufficient
    - status='needs_clarification' when intent is ambiguous
    - status='skipped_with_reason' when coverage is gated or insufficient
    - status='gated' when all coverage reports are gated

    Never includes arbitrary SQL or user-provided string fragments in operations.
    """
    artifact_id = f"extraction-plan-{uuid4().hex[:8]}"

    if not coverage_reports:
        return ExtractionPlan(
            artifact_id=artifact_id,
            status="skipped_with_reason",
            operations=[],
            filters={},
            output_columns=_canonical_output_columns(),
            skip_reason="no_coverage_reports_provided",
            validation_errors=["no_coverage_reports_provided"],
            compile_mode="gated",
        )

    # Check if all coverage reports are gated or skipped
    ok_reports = [r for r in coverage_reports if _report_is_extraction_ready(r)]
    gated_reports = [r for r in coverage_reports if r.status == "gated"]
    skipped_reports = [r for r in coverage_reports if r.status == "skipped_with_reason"]

    if not ok_reports:
        validation_errors = _coverage_validation_errors(coverage_reports)
        if gated_reports:
            return ExtractionPlan(
                artifact_id=artifact_id,
                status="gated",
                operations=[],
                filters={},
                output_columns=_canonical_output_columns(),
                skip_reason="; ".join(
                    r.gated_reason for r in gated_reports if r.gated_reason
                ) or "coverage_gated",
                validation_errors=validation_errors,
                compile_mode="gated",
            )
        return ExtractionPlan(
            artifact_id=artifact_id,
            status="skipped_with_reason",
            operations=[],
            filters={},
            output_columns=_canonical_output_columns(),
            skip_reason="; ".join(
                r.gated_reason for r in skipped_reports if r.gated_reason
            ) or "coverage_not_extraction_ready",
            validation_errors=validation_errors,
            compile_mode="gated",
        )

    # We have at least one ok coverage report — build the plan
    if intent.needs_clarification:
        return ExtractionPlan(
            artifact_id=artifact_id,
            status="needs_clarification",
            operations=[],
            filters=_safe_filters_from_intent(intent),
            output_columns=_canonical_output_columns(),
            skip_reason="intent_requires_clarification",
            validation_errors=["intent_requires_clarification"],
            compile_mode="gated",
        )

    # Direct one-source plans compile deterministically; complex live plans must
    # surface LLM failures explicitly instead of silently falling back.
    compile_mode = "deterministic"
    if _is_direct_deterministic_plan(intent, ok_reports):
        operations = _select_operations(intent, ok_reports)
        filters = _safe_filters_from_intent(intent)
    elif live_llm_required:
        try:
            operations, filters = _llm_select_plan(intent, ok_reports)
            compile_mode = "llm"
        except Exception as exc:
            return ExtractionPlan(
                artifact_id=artifact_id,
                status="gated",
                operations=[],
                filters=_safe_filters_from_intent(intent),
                output_columns=_canonical_output_columns(),
                skip_reason=f"llm_extraction_planner_error:{exc}",
                validation_errors=[f"llm_extraction_planner_error:{exc}"],
                compile_mode="gated",
            )
    else:
        operations = _select_operations(intent, ok_reports)
        filters = _safe_filters_from_intent(intent)

    # Pick the best covered report for dispatch routing.
    primary_report = _select_primary_report(ok_reports, filters)
    source_id = primary_report.source_id
    source_family = primary_report.source_family or _source_family_from_report(primary_report)
    adapter_name = get_extractor_for_source(source_family) if source_family else None

    # Determine output columns from canonical adapter schema
    output_columns = _canonical_output_columns()

    return ExtractionPlan(
        artifact_id=artifact_id,
        source_id=source_id,
        source_family=source_family,
        adapter_name=adapter_name,
        source_candidate_ids=[
            str(r.source_candidate_id) for r in ok_reports if r.source_candidate_id
        ],
        coverage_report_ids=[_coverage_report_id(r) for r in ok_reports],
        validation_errors=[],
        compile_mode=compile_mode,  # type: ignore[arg-type]
        status="ok",
        operations=operations,
        filters=filters,
        output_columns=output_columns,
        # duckdb_sql is never set here; adapters compile SQL internally
        duckdb_sql=None,
    )


def get_extractor_for_source(source_family: str) -> str:
    """Return the deterministic extractor function name for the source family.

    Used by downstream tools to dispatch extraction to the correct adapter.
    Supports 'fedstat', 'world_bank', and 'ckan' (extract_ckan_dataset).
    """
    family = str(source_family).strip().lower()
    return _EXTRACTOR_DISPATCH.get(family, f"extract_{family}_dataset")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _select_operations(
    intent: IntentFrame,
    ok_reports: list[CoverageReport],
) -> list[str]:
    """Select safe operations from ALLOWED_OPERATIONS based on intent and coverage."""
    ops: list[str] = ["coverage_preview", "filter_rows"]

    # Add join if multiple sources or comparative query
    if len(ok_reports) > 1 or intent.category in ("comparative", "research", "derived_metric"):
        ops.append("join_indicators")

    # Add normalize_index for derived metric / index queries
    if intent.category == "derived_metric":
        ops.append("normalize_index")

    ops.append("export_dataset")

    # Guarantee all selected ops are in the allowlist (safety assertion)
    return [op for op in ops if op in ALLOWED_OPERATIONS]


def _report_is_extraction_ready(report: CoverageReport) -> bool:
    if report.status != "ok":
        return False
    if report.extraction_ready is None:
        return not report.extraction_blockers
    return bool(report.extraction_ready) and not report.extraction_blockers


def _coverage_validation_errors(reports: list[CoverageReport]) -> list[str]:
    errors: list[str] = []
    for report in reports:
        if report.extraction_blockers:
            errors.extend(f"{report.source_id}:{blocker}" for blocker in report.extraction_blockers)
        elif report.status != "ok":
            errors.append(f"{report.source_id}:coverage_status:{report.status}")
        elif report.extraction_ready is False:
            errors.append(f"{report.source_id}:not_extraction_ready")
    return errors or ["no_extraction_ready_coverage_reports"]


def _is_direct_deterministic_plan(
    intent: IntentFrame,
    ok_reports: list[CoverageReport],
) -> bool:
    return len(ok_reports) == 1 and intent.category in {"simple", "ambiguous"}


def _safe_filters_from_intent(intent: IntentFrame) -> dict[str, Any]:
    """Extract safe typed filters from intent known_fields.

    Never includes raw user query strings or SQL fragments.
    """
    known = intent.known_fields or {}
    safe: dict[str, Any] = {}

    # Periods: list of strings (e.g. ["2020", "2021"])
    if "periods" in known:
        periods = known["periods"]
        if isinstance(periods, (list, tuple)):
            safe["periods"] = [str(p) for p in periods if str(p).isdigit() or _is_date_like(str(p))]
        elif isinstance(periods, str) and (_is_date_like(periods) or periods.isdigit()):
            safe["periods"] = [periods]
    elif "period" in known:
        period = str(known["period"]).strip()
        if _is_date_like(period) or period.isdigit():
            safe["periods"] = [period]

    # Geography
    if "geography" in known:
        geo = str(known["geography"]).strip()
        if geo and len(geo) <= 100:  # bounded
            safe["geography"] = geo

    # Countries list
    if "countries" in known:
        countries = known["countries"]
        if isinstance(countries, (list, tuple)):
            safe["countries"] = [str(c).strip() for c in countries if str(c).strip()]

    # Indicator name (bounded)
    for key in ("indicator", "indicator_name", "indicator_id"):
        if key in known:
            val = str(known[key]).strip()
            if val and len(val) <= 200:
                safe[key] = val
                break

    return safe


def _select_primary_report(
    ok_reports: list[CoverageReport],
    filters: dict[str, Any],
) -> CoverageReport:
    requested_periods = {str(period) for period in filters.get("periods", [])}

    def score(report: CoverageReport) -> tuple[int, int]:
        available_periods = {str(period) for period in report.available_periods}
        evidence = report.evidence or {}
        row_count = int(evidence.get("row_count") or 0)
        period_score = 1 if not requested_periods or requested_periods <= available_periods else 0
        return (period_score, row_count)

    return max(ok_reports, key=score)


def _source_family_from_report(report: CoverageReport) -> str | None:
    if report.source_family:
        return report.source_family
    evidence = report.evidence or {}
    family = evidence.get("family") or evidence.get("source_family")
    return str(family) if family else None


def _coverage_report_id(report: CoverageReport) -> str:
    return str(report.source_candidate_id or report.source_id)


def _is_date_like(value: str) -> bool:
    """Return True if value looks like a year or ISO date."""
    import re
    return bool(re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", value))


def _canonical_output_columns() -> list[str]:
    """Return canonical dataset output columns matching FedStat/WB/CKAN adapters."""
    return [
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


def _llm_select_plan(
    intent: IntentFrame,
    ok_reports: list[CoverageReport],
) -> tuple[list[str], dict[str, Any]]:
    """Ask Qwen to select extraction operations and filters from the allowlist.

    Per ARCHITECTURE_STACK.md: LLM chooses plan operations, not writes pipeline.
    Returns (operations, filters). Falls back to rule-based on LLM error.
    """
    try:
        from pydantic import BaseModel
        from app.llm.yandex_ai_studio import YandexAIStudioClient, qwen_credential_gate

        gate = qwen_credential_gate()
        if gate["status"] == "gated_skip":
            raise RuntimeError(f"llm_extraction_planner_gated:{gate.get('missing_env_vars', [])}")

        class _PlanChoice(BaseModel):
            operations: list[str] = []
            filters: dict[str, Any] = {}
            reasoning: str = ""

        coverage_summary = [
            {
                "source_id": r.source_id,
                "status": r.status,
                "available_periods": r.available_periods[:5],
                "available_geographies": r.available_geographies[:5],
                "unit": r.unit,
                "llm_best_slice": (r.evidence or {}).get("llm_best_slice", ""),
                "llm_quality_risks": (r.evidence or {}).get("llm_quality_risks", []),
            }
            for r in ok_reports
        ]

        client = YandexAIStudioClient()
        result = client.structured_chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Ты — Extraction Planner Agent DataAgent. "
                        f"Разрешённые операции: {sorted(ALLOWED_OPERATIONS)}. "
                        "Выбери операции и фильтры для извлечения данных. "
                        "ЗАПРЕЩЕНО: произвольный SQL, строки из запроса пользователя в фильтрах. "
                        "Фильтры только из проверенных полей: geography, indicator, period, countries. "
                        "Отвечай строго в формате JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Запрос: {intent.query}\n"
                        f"Категория: {intent.category}\n"
                        f"Известные поля: {intent.known_fields}\n"
                        f"Покрытие источников: {coverage_summary}"
                    ),
                },
            ],
            schema=_PlanChoice,
            temperature=0.0,
            max_tokens=512,
        )

        # Enforce allowlist — LLM output cannot add unsafe operations
        safe_ops = [op for op in result.operations if op in ALLOWED_OPERATIONS]
        if not safe_ops:
            safe_ops = _select_operations(intent, ok_reports)

        # Enforce safe filters — only known typed keys
        safe_filters = _safe_filters_from_intent(intent)
        for key in ("geography", "indicator", "period", "countries", "indicator_id",
                    "indicator_name", "periods"):
            if key in result.filters:
                val = result.filters[key]
                if isinstance(val, (str, list)) and val:
                    safe_filters[key] = val

        return safe_ops, safe_filters

    except Exception as exc:
        raise RuntimeError(str(exc)) from exc
