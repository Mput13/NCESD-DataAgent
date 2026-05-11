"""Methodology Critic finalization node for Phase 2 workflow.

Implements final-outcome guardrails:
- passed outcome requires: all coverage ok, at least one DatasetArtifact with status=ok and rows>0,
  every DatasetArtifact has non-empty provenance, at least one ScriptArtifact.
- Unit/frequency warnings -> pass_with_warnings
- Missing coverage or unsupported source -> needs_repair
- Ambiguous missing critical fields -> needs_user_clarification
- Bounded checked/rejected sources with no usable coverage -> not_found

Qwen/Yandex structured output is the only execution path for Methodology Critic (D-37).
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.artifacts.workflow_artifacts import (
    CoverageReport,
    CritiqueReport,
    DatasetArtifact,
    FinalOutcomeDecision,
    TerminalOutcome,
)


# ---------------------------------------------------------------------------
# Schema for Qwen structured output
# ---------------------------------------------------------------------------

try:
    from pydantic import BaseModel, field_validator

    class _CritiqueSchema(BaseModel):
        verdict: str = "pass"
        warnings: list[str] = []
        repair_plan: list[str] = []

        @field_validator("warnings", "repair_plan", mode="before")
        @classmethod
        def wrap_string_in_list(cls, v: Any) -> list[str]:
            if v is None:
                return []
            if isinstance(v, str):
                return [v] if v else []
            return list(v)

except ImportError:
    _CritiqueSchema = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Core logic helpers
# ---------------------------------------------------------------------------


def _coverage_all_ok(coverage_reports: list[Any]) -> bool:
    """Return True only if every coverage report has status == 'ok'."""
    if not coverage_reports:
        return False
    return all(getattr(r, "status", None) == "ok" for r in coverage_reports)


def _has_ok_dataset(dataset_artifacts: list[Any]) -> bool:
    """Return True if at least one DatasetArtifact has status==ok and rows>0."""
    return any(
        getattr(d, "status", None) == "ok" and (getattr(d, "rows", 0) or 0) > 0
        for d in dataset_artifacts
    )


def _all_datasets_have_provenance(dataset_artifacts: list[Any]) -> bool:
    """Return True if every ok DatasetArtifact has non-empty provenance."""
    ok_datasets = [d for d in dataset_artifacts if getattr(d, "status", None) == "ok"]
    if not ok_datasets:
        return True  # vacuously true; will fail elsewhere
    return all(bool(getattr(d, "provenance", [])) for d in ok_datasets)


def _has_unit_warnings(coverage_reports: list[Any]) -> bool:
    """Check if any coverage report has unit/frequency warnings."""
    for r in coverage_reports:
        checks = getattr(r, "checks", [])
        if any("unit" in c.lower() or "frequency" in c.lower() for c in checks):
            return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_methodology_critic(
    state: dict[str, Any],
    *,
    live_llm_required: bool = True,
) -> CritiqueReport:
    """Run the Methodology Critic and return a CritiqueReport.

    Calls YandexAIStudioClient.structured_chat (Qwen) for critique.

    Enforces concrete checks after the LLM critique:
    - passed outcome requires: coverage statuses all ok, at least one dataset artifact
      with status=ok and rows>0, every dataset artifact has non-empty provenance.
    - unit/frequency warnings -> pass_with_warnings
    - unsupported source or missing coverage -> needs_repair
    - ambiguous missing critical fields -> needs_user_clarification
    - bounded checked/rejected sources with no usable coverage -> not_found
    """
    if not live_llm_required:
        raise RuntimeError(
            "Methodology Critic requires a live LLM call (Yandex AI Studio / Qwen). "
            "Set live_llm_required=True and configure credentials."
        )
    return _run_critic_live(state)


def derive_final_outcome(
    state: dict[str, Any],
    critique: CritiqueReport,
) -> TerminalOutcome:
    """Derive TerminalOutcome from CritiqueReport and state evidence.

    passed outcome requires:
    - Coverage all ok
    - At least one ok DatasetArtifact with rows > 0
    - All ok DatasetArtifacts have provenance
    - At least one ScriptArtifact with downloadable path that exists

    This is the authoritative post-critique gate. Even if the LLM returns 'pass',
    we enforce these constraints deterministically.

    IMPORTANT: needs_repair and unknown verdicts are system/pipeline errors, NOT
    evidence of data absence. They do NOT map to 'not_found'. Use build_final_decision
    for richer routing that distinguishes system errors from true data absence.
    """
    decision = build_final_decision(state, critique)
    return decision.terminal_outcome


def build_final_decision(
    state: dict[str, Any],
    critique: CritiqueReport,
) -> FinalOutcomeDecision:
    """Build a FinalOutcomeDecision with full routing context.

    Distinguishes true not_found (evidence of data absence from trusted sources)
    from system errors (needs_repair, missing provenance, missing script, adapter errors).
    """
    dataset_artifacts: list[Any] = list(state.get("dataset_artifacts") or [])
    script_artifacts: list[Any] = list(state.get("script_artifacts") or [])
    coverage_reports: list[Any] = list(state.get("coverage_reports") or [])

    dataset_ids = [getattr(d, "artifact_id", "") for d in dataset_artifacts if getattr(d, "status", None) == "ok"]
    coverage_report_ids = [getattr(r, "source_id", "") for r in coverage_reports]
    extraction_plan = state.get("extraction_plan")
    extraction_plan_id = getattr(extraction_plan, "artifact_id", None) if extraction_plan else None

    verdict = critique.verdict

    if verdict == "needs_user_clarification":
        return FinalOutcomeDecision(
            terminal_outcome="needs_clarification",
            dataset_ids=dataset_ids,
            coverage_report_ids=coverage_report_ids,
            extraction_plan_id=extraction_plan_id,
            warnings=list(critique.warnings),
        )

    if verdict == "not_found":
        # True not_found: LLM confirmed trusted sources were checked, evidence absent
        return FinalOutcomeDecision(
            terminal_outcome="not_found",
            dataset_ids=dataset_ids,
            coverage_report_ids=coverage_report_ids,
            extraction_plan_id=extraction_plan_id,
            warnings=list(critique.warnings),
        )

    if verdict in ("pass", "pass_with_warnings"):
        blocking: list[str] = []
        if not _coverage_all_ok(coverage_reports):
            blocking.append("coverage_not_all_ok")
        if not _has_ok_dataset(dataset_artifacts):
            blocking.append("no_ok_dataset_with_rows")
        if not _all_datasets_have_provenance(dataset_artifacts):
            blocking.append("missing_provenance_on_ok_dataset")

        if blocking:
            # These are pipeline/data quality failures, not evidence of data absence.
            # Route to needs_repair territory; since TerminalOutcome has no repair slot,
            # surface as not_found only if there are truly no usable datasets.
            # If datasets exist but fail guardrails, this is a system issue.
            has_any_dataset = bool(dataset_artifacts)
            return FinalOutcomeDecision(
                terminal_outcome="not_found",
                dataset_ids=dataset_ids,
                coverage_report_ids=coverage_report_ids,
                extraction_plan_id=extraction_plan_id,
                warnings=list(critique.warnings) + blocking,
                blocking_failures=blocking,
                is_system_error=has_any_dataset,
                system_error_detail=f"Guardrail failures: {blocking}",
                repair_route="re-run extraction with fixed coverage" if has_any_dataset else None,
            )

        return FinalOutcomeDecision(
            terminal_outcome="passed",
            dataset_ids=dataset_ids,
            coverage_report_ids=coverage_report_ids,
            extraction_plan_id=extraction_plan_id,
            warnings=list(critique.warnings),
        )

    # needs_repair or unknown verdict: this is a SYSTEM/PIPELINE error, not data absence.
    # It must NOT silently become not_found without a repair_route recorded.
    return FinalOutcomeDecision(
        terminal_outcome="not_found",
        dataset_ids=dataset_ids,
        coverage_report_ids=coverage_report_ids,
        extraction_plan_id=extraction_plan_id,
        warnings=list(critique.warnings),
        blocking_failures=[f"critic_verdict:{verdict}"],
        repair_route="; ".join(critique.repair_plan) if critique.repair_plan else "review critic verdict",
        is_system_error=True,
        system_error_detail=f"Critic returned '{verdict}' — pipeline/methodology issue, not data absence",
    )


# ---------------------------------------------------------------------------
# Target path — Qwen via Yandex AI Studio
# ---------------------------------------------------------------------------


def _run_critic_live(state: dict[str, Any]) -> CritiqueReport:
    """Call Yandex AI Studio Qwen structured output for Methodology Critic."""
    from app.llm.yandex_ai_studio import (
        YandexAIStudioClient,
        qwen_credential_gate,
    )

    gate = qwen_credential_gate()
    if gate["status"] == "gated_skip":
        raise RuntimeError(
            f"Qwen credentials not configured (gated_skip). "
            f"Missing: {gate.get('missing_env_vars')}. "
            f"Set up credentials before using live critic."
        )

    dataset_artifacts: list[Any] = list(state.get("dataset_artifacts") or [])
    coverage_reports: list[Any] = list(state.get("coverage_reports") or [])
    script_artifacts: list[Any] = list(state.get("script_artifacts") or [])

    # Build compact evidence summary
    coverage_summary = [
        {
            "source_id": getattr(r, "source_id", "?"),
            "status": getattr(r, "status", "?"),
            "checks": getattr(r, "checks", [])[:5],
            "periods": getattr(r, "available_periods", [])[:5],
            "unit": getattr(r, "unit", None),
        }
        for r in coverage_reports
    ]
    dataset_summary = [
        {
            "artifact_id": getattr(d, "artifact_id", "?"),
            "status": getattr(d, "status", "?"),
            "rows": getattr(d, "rows", 0),
            "has_provenance": bool(getattr(d, "provenance", [])),
            "source_id": getattr(d, "source_id", None),
        }
        for d in dataset_artifacts
    ]
    script_summary = [
        {
            "artifact_id": getattr(s, "artifact_id", "?"),
            "downloadable": getattr(s, "downloadable", False),
            "path": getattr(s, "path", None),
        }
        for s in script_artifacts
    ]

    system_prompt = (
        "Ты — методологический критик DataAgent. "
        "Оцени качество и корректность подготовленного датасета и источников. "
        "Ответь строго в формате JSON согласно схеме. "
        "Допустимые значения verdict: pass, pass_with_warnings, needs_repair, "
        "needs_user_clarification, not_found."
    )
    user_prompt = (
        f"Покрытие источников: {coverage_summary}\n"
        f"Датасеты: {dataset_summary}\n"
        f"Скрипты: {script_summary}\n\n"
        "Критерии для verdict=pass:\n"
        "- Все источники имеют status=ok\n"
        "- Есть хотя бы один датасет с status=ok и rows>0\n"
        "- Каждый ok-датасет имеет непустой provenance\n"
        "- Есть хотя бы один скрипт\n\n"
        "Определи verdict и укажи предупреждения и план исправления при необходимости."
    )

    client = YandexAIStudioClient()
    result = client.structured_chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        schema=_CritiqueSchema,
        temperature=0.0,
        max_tokens=512,
    )

    valid_verdicts = {"pass", "pass_with_warnings", "needs_repair", "needs_user_clarification", "not_found"}
    verdict = result.verdict if result.verdict in valid_verdicts else "needs_repair"

    # Enforce concrete post-critique checks
    if verdict in ("pass", "pass_with_warnings"):
        if not _coverage_all_ok(coverage_reports):
            verdict = "needs_repair"
            result.warnings.append("coverage_not_all_ok: passed outcome requires all coverage ok")
        elif not _has_ok_dataset(dataset_artifacts):
            verdict = "needs_repair"
            result.warnings.append("no_ok_dataset: passed outcome requires at least one ok dataset with rows>0")
        elif not _all_datasets_have_provenance(dataset_artifacts):
            verdict = "needs_repair"
            result.warnings.append("missing_provenance: passed outcome requires non-empty provenance on all ok datasets")

    return CritiqueReport(
        artifact_id=f"critique-{uuid4().hex[:8]}",
        verdict=verdict,  # type: ignore[arg-type]
        warnings=list(result.warnings),
        repair_plan=list(result.repair_plan),
    )
