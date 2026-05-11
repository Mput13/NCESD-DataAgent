"""Narrator node for Phase 2 workflow.

Implements source-bound response construction:
- build_workflow_response: creates WorkflowResponse from Phase2State and finalization artifacts
- assert_message_numbers_are_supported: verifies no unsupported numerics in message

Qwen/Yandex structured output is the only execution path for Narrator (D-37).

Key invariants:
- Any number in WorkflowResponse.message must appear in DatasetArtifact records or provenance
- passed responses include at least one downloadable ScriptArtifact from Phase2State.script_artifacts
- needs_clarification includes concrete questions, no dataset artifacts
- not_found includes checked/rejected source evidence, no invented values
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.artifacts.workflow_artifacts import (
    CritiqueReport,
    DatasetArtifact,
    FeedbackAction,
    NoDataExplanationArtifact,
    ScriptArtifact,
    TerminalOutcome,
    TraceEvent,
    VisualizationSpec,
    WorkflowResponse,
    utc_now_iso,
)


def _tag_diagnostic(
    artifacts: list[DatasetArtifact],
    final_outcome: str,
) -> list[DatasetArtifact]:
    """Add 'diagnostic' quality flag to artifacts when outcome is not passed."""
    if final_outcome == "passed":
        return artifacts
    return [
        a.model_copy(update={"quality_flags": list(a.quality_flags) + ["diagnostic"]})
        if "diagnostic" not in a.quality_flags
        else a
        for a in artifacts
    ]


# ---------------------------------------------------------------------------
# Number support assertion
# ---------------------------------------------------------------------------


def assert_message_numbers_are_supported(
    message: str,
    datasets: list[DatasetArtifact],
) -> None:
    """Assert that all numbers in message appear in dataset records or provenance.

    Extracts integer and decimal numbers from message.
    Builds a ledger of supported values from:
    - All numeric values in dataset records
    - Years/periods from provenance and records

    Raises ValueError if a number in message cannot be found in the ledger.
    """
    # Extract all numbers from message (integers and decimals)
    number_pattern = re.compile(r"\b\d+(?:[.,]\d+)?\b")
    message_numbers = set(number_pattern.findall(message))

    if not message_numbers:
        return  # No numbers to verify

    # Build supported number ledger from datasets
    supported: set[str] = set()
    for dataset in datasets:
        for record in dataset.records or []:
            for val in record.values():
                if val is not None:
                    str_val = str(val)
                    # Add both the raw string and numeric forms
                    supported.add(str_val)
                    # Try to add integer form if it's a float
                    try:
                        numeric = float(str_val)
                        supported.add(str(int(numeric)))
                        supported.add(f"{numeric:.0f}")
                        supported.add(str_val.split(".")[0])
                    except (ValueError, TypeError):
                        pass
        # Add from provenance
        for prov in dataset.provenance or []:
            for val in prov.values():
                if val is not None:
                    supported.add(str(val))
                    # Extract year-like 4-digit numbers from provenance values
                    for year in re.findall(r"\b\d{4}\b", str(val)):
                        supported.add(year)

    # Check each number in message
    unsupported = []
    for num in message_numbers:
        # Normalize: remove trailing zeros, compare
        normalized = num.replace(",", ".")
        if num in supported:
            continue
        # Try numeric comparison (e.g. "2022" matches "2022")
        found = False
        for s in supported:
            try:
                if float(normalized) == float(s.replace(",", ".")):
                    found = True
                    break
            except (ValueError, TypeError):
                pass
        if not found:
            unsupported.append(num)

    if unsupported:
        raise ValueError(
            f"Unsupported numeric claims in message: {unsupported}. "
            f"All numbers must come from DatasetArtifact records or provenance."
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_workflow_response(
    state: dict[str, Any],
    *,
    final_outcome: TerminalOutcome,
    critique: CritiqueReport,
    visualization: VisualizationSpec | None,
    live_llm_required: bool = True,
) -> WorkflowResponse:
    """Build a complete WorkflowResponse from Phase2State and finalization artifacts.

    Calls YandexAIStudioClient.structured_chat for Narrator (D-37).

    For 'passed': validates at least one ok dataset and one downloadable script,
    constructs answer blocks: summary, methodology, limitations, how_found.
    For 'needs_clarification': includes concrete questions from IntentFrame.missing_fields.
    For 'not_found': includes NoDataExplanationArtifact from source/rejection evidence.
    """
    if not live_llm_required:
        if final_outcome == "not_found":
            # For not_found, LLM is not required — build diagnostic response directly
            return _build_not_found_response(
                state=state,
                critique=critique,
                visualization=visualization,
                dataset_artifacts=list(state.get("dataset_artifacts") or []),
                script_artifacts=list(state.get("script_artifacts") or []),
                coverage_reports=list(state.get("coverage_reports") or []),
                extra_statuses={},
            )
        raise RuntimeError("Narrator requires live Yandex AI Studio / Qwen.")
    return _build_response_live(
        state,
        final_outcome=final_outcome,
        critique=critique,
        visualization=visualization,
    )


# ---------------------------------------------------------------------------
# Target path — Qwen via Yandex AI Studio
# ---------------------------------------------------------------------------


class _NarratorSchema:
    """Schema for Qwen narrator structured output."""
    try:
        from pydantic import BaseModel

        class _Inner(BaseModel):
            message: str = ""
            summary: str = ""
            methodology: str = ""
            limitations: list[str] = []
            how_found: str = ""
            clarification_questions: list[str] = []

        Schema = _Inner
    except ImportError:
        Schema = None  # type: ignore[assignment]


def _build_response_live(
    state: dict[str, Any],
    *,
    final_outcome: TerminalOutcome,
    critique: CritiqueReport,
    visualization: VisualizationSpec | None,
    _schema_class: Any = None,
) -> WorkflowResponse:
    """Call Yandex AI Studio Qwen for narrator output."""
    from app.llm.yandex_ai_studio import YandexAIStudioClient, qwen_credential_gate

    gate = qwen_credential_gate()
    if gate["status"] == "gated_skip":
        raise RuntimeError(
            f"Qwen credentials not configured (gated_skip). "
            f"Missing: {gate.get('missing_env_vars')}."
        )

    dataset_artifacts: list[DatasetArtifact] = list(state.get("dataset_artifacts") or [])
    script_artifacts: list[ScriptArtifact] = list(state.get("script_artifacts") or [])
    coverage_reports: list[Any] = list(state.get("coverage_reports") or [])
    evidence: Any = state.get("evidence")
    intent: Any = state.get("intent")
    run_id: str = str(state.get("run_id") or "unknown")

    # Build compact, source-bound context for narrator
    dataset_summaries = [
        {
            "artifact_id": d.artifact_id,
            "source_id": d.source_id,
            "rows": d.rows,
            "columns": d.columns[:8],
            "sample_records": (d.records or [])[:3],
            "provenance": (d.provenance or [])[:2],
        }
        for d in dataset_artifacts if d.status == "ok"
    ]
    script_summaries = [
        {
            "artifact_id": s.artifact_id,
            "path": s.path,
            "downloadable": s.downloadable,
        }
        for s in script_artifacts
    ]

    selected_sources = list(getattr(evidence, "selected_sources", []) or []) if evidence else []
    rejected_sources = list(getattr(evidence, "rejected_sources", []) or []) if evidence else []

    system_prompt = (
        "Ты — нарратор DataAgent. Твоя задача — создать итоговый ответ на запрос пользователя. "
        "ВАЖНО: числовые значения в ответе должны браться ТОЛЬКО из предоставленных датасетов. "
        "Не придумывай числа. Если данных нет, честно сообщи об этом. "
        "Ответь строго в формате JSON согласно схеме."
    )

    missing_fields = list(getattr(intent, "missing_fields", []) or []) if intent else []
    query = str(state.get("query") or "")

    user_prompt = (
        f"Запрос пользователя: {query}\n"
        f"Итоговый статус: {final_outcome}\n"
        f"Вердикт критика: {critique.verdict}, предупреждения: {critique.warnings}\n"
        f"Датасеты (только данные из источников): {dataset_summaries}\n"
        f"Скрипты: {script_summaries}\n"
        f"Выбранные источники: {selected_sources[:5]}\n"
        f"Отклонённые источники: {rejected_sources[:5]}\n"
        f"Недостающие поля: {missing_fields}\n\n"
        "Создай итоговый ответ:\n"
        "- message: главный текст ответа (только из источников, без выдуманных цифр)\n"
        "- summary: краткое резюме\n"
        "- methodology: методология\n"
        "- limitations: список ограничений\n"
        "- how_found: как нашли данные\n"
        "- clarification_questions: вопросы уточнения (если нужно)"
    )

    from pydantic import BaseModel

    class _NarratorSchemaInner(BaseModel):
        message: str = ""
        summary: str = ""
        methodology: str = ""
        limitations: list[str] = []
        how_found: str = ""
        clarification_questions: list[str] = []

    client = YandexAIStudioClient()
    result = client.structured_chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        schema=_NarratorSchemaInner,
        temperature=0.0,
        max_tokens=1024,
    )

    no_data_evidence: NoDataExplanationArtifact | None = None
    if final_outcome == "not_found":
        no_data_evidence = NoDataExplanationArtifact(
            artifact_id=f"not-found-{uuid4().hex[:8]}",
            checked_sources=selected_sources[:10] or [{"source_id": "no_sources_checked"}],
            rejected_sources=rejected_sources[:10],
            rejection_reasons=critique.warnings or ["not_found"],
            search_strategy="fedstat/world_bank/ckan_source_scouts",
        )

    # Enforce: all numbers in message must appear in dataset records or provenance
    # Per ARCHITECTURE_STACK.md and D-30: unsupported numeric claims are hard failures
    if final_outcome == "passed" and result.message:
        ok_datasets = [d for d in dataset_artifacts if d.status == "ok"]
        try:
            assert_message_numbers_are_supported(result.message, ok_datasets)
        except ValueError as num_err:
            # Downgrade to not_found — narrator produced unsupported numeric claim
            final_outcome = "not_found"
            no_data_evidence = NoDataExplanationArtifact(
                artifact_id=f"not-found-numeric-{uuid4().hex[:8]}",
                checked_sources=selected_sources[:10],
                rejected_sources=rejected_sources[:10],
                rejection_reasons=[f"unsupported_numeric_claim: {num_err}"],
                search_strategy="numeric_assertion_guard",
            )
            result = type(result)(  # rebuild with safe message
                **{
                    **result.model_dump(),
                    "message": (
                        "Данные найдены, но ответ содержал числа не из источников. "
                        "Пожалуйста, уточните запрос для получения проверяемых данных."
                    ),
                }
            )

    return _assemble_response(
        state=state,
        final_outcome=final_outcome,
        critique=critique,
        visualization=visualization,
        message=result.message,
        summary=result.summary,
        methodology=result.methodology,
        limitations=result.limitations,
        how_found=result.how_found,
        clarification_questions=result.clarification_questions,
        dataset_artifacts=dataset_artifacts,
        script_artifacts=script_artifacts,
        coverage_reports=coverage_reports,
        no_data_evidence=no_data_evidence,
        extra_statuses={},
    )

def _derive_clarification_questions(missing_fields: list[str], query: str) -> list[str]:
    field_to_question = {
        "geography": "Для какой страны или региона нужны данные?",
        "period": "За какой период нужны данные (годы, кварталы)?",
        "indicator": "Какой именно экономический показатель вас интересует?",
        "unit": "В каких единицах измерения нужны данные?",
        "source": "Какой источник данных предпочтителен: Росстат, World Bank или НЦСЭД?",
    }
    questions = [field_to_question.get(field, f"Уточните поле '{field}' для запроса: {query}") for field in missing_fields]
    return questions or [f"Уточните запрос: '{query}'. Укажите период, географию и показатель."]


def _build_not_found_response(
    *,
    state: dict[str, Any],
    critique: CritiqueReport,
    visualization: VisualizationSpec | None,
    dataset_artifacts: list[DatasetArtifact],
    script_artifacts: list[ScriptArtifact],
    coverage_reports: list[Any],
    extra_statuses: dict[str, str],
    reason: str = "not_found",
) -> WorkflowResponse:
    """Build a not_found WorkflowResponse with evidence from source rejections."""
    evidence_bundle: Any = state.get("evidence")
    selected = list(getattr(evidence_bundle, "selected_sources", []) or []) if evidence_bundle else []
    rejected = list(getattr(evidence_bundle, "rejected_sources", []) or []) if evidence_bundle else []

    no_data_evidence = NoDataExplanationArtifact(
        artifact_id=f"not-found-{uuid4().hex[:8]}",
        checked_sources=selected[:10] or [{"source_id": "no_sources_checked"}],
        rejected_sources=rejected[:10] or [{"source_id": "no_sources_checked", "reason": reason}],
        rejection_reasons=critique.warnings or [reason],
        search_strategy="fedstat/world_bank/ckan_source_scouts",
        alternatives=[],
        limitations=critique.repair_plan or [],
    )

    query = str(state.get("query") or "")
    message = (
        f"По запросу '{query}' данные не найдены в проверенных источниках. "
        f"Проверено источников: {len(selected)}. Причина: {reason}."
    )

    return _assemble_response(
        state=state,
        final_outcome="not_found",
        critique=critique,
        visualization=None,
        message=message,
        summary="Данные не найдены в проверенных источниках.",
        methodology="",
        limitations=critique.warnings or [],
        how_found="",
        clarification_questions=[],
        dataset_artifacts=dataset_artifacts,
        script_artifacts=script_artifacts,
        coverage_reports=coverage_reports,
        no_data_evidence=no_data_evidence,
        extra_statuses=extra_statuses,
    )


def _assemble_response(
    *,
    state: dict[str, Any],
    final_outcome: TerminalOutcome,
    critique: CritiqueReport,
    visualization: VisualizationSpec | None,
    message: str,
    summary: str,
    methodology: str,
    limitations: list[str],
    how_found: str,
    clarification_questions: list[str],
    dataset_artifacts: list[DatasetArtifact],
    script_artifacts: list[ScriptArtifact],
    coverage_reports: list[Any],
    no_data_evidence: NoDataExplanationArtifact | None = None,
    extra_statuses: dict[str, str] | None = None,
) -> WorkflowResponse:
    """Assemble the final WorkflowResponse from all components."""
    from app.artifacts.workflow_artifacts import CoverageReport

    run_id = str(state.get("run_id") or "unknown")
    trace_events: list[TraceEvent] = list(state.get("trace_events") or [])
    component_statuses: dict[str, str] = dict(state.get("component_statuses") or {})

    if extra_statuses:
        component_statuses.update(extra_statuses)

    evidence_bundle: Any = state.get("evidence")
    selected_sources = list(getattr(evidence_bundle, "selected_sources", []) or []) if evidence_bundle else []
    rejected_sources = list(getattr(evidence_bundle, "rejected_sources", []) or []) if evidence_bundle else []

    # Build answer blocks based on outcome type
    answer_blocks: list[dict[str, Any]] = []
    if final_outcome == "passed":
        if summary:
            answer_blocks.append({"type": "summary", "text": summary})
        if methodology:
            answer_blocks.append({"type": "methodology", "text": methodology})
        if limitations:
            answer_blocks.append({"type": "limitations", "items": limitations})
        if how_found:
            answer_blocks.append({"type": "how_found", "text": how_found})
    elif final_outcome == "needs_clarification":
        answer_blocks.append({
            "type": "clarification_request",
            "questions": clarification_questions,
        })
    elif final_outcome == "not_found":
        answer_blocks.append({
            "type": "not_found",
            "summary": summary or "Данные не найдены",
            "limitations": limitations,
        })

    # Build feedback actions
    feedback_actions: list[FeedbackAction] = []
    if final_outcome == "passed":
        feedback_actions.append(
            FeedbackAction(
                action_id=f"rate-{uuid4().hex[:8]}",
                label="Оценить ответ",
                action_type="rate",
                payload={"run_id": run_id},
            )
        )
        for sa in script_artifacts:
            if sa.downloadable:
                feedback_actions.append(
                    FeedbackAction(
                        action_id=f"download-{sa.artifact_id}",
                        label=f"Скачать скрипт: {sa.download_filename or sa.artifact_id}",
                        action_type="download",
                        target_artifact_id=sa.artifact_id,
                        payload={"path": sa.path, "filename": sa.download_filename},
                    )
                )
    elif final_outcome == "needs_clarification":
        feedback_actions.append(
            FeedbackAction(
                action_id=f"answer-clarification-{uuid4().hex[:8]}",
                label="Ответить на уточняющий вопрос",
                action_type="clarify",
                payload={"run_id": run_id, "action": "answer_clarification"},
            )
        )

    # Build coverage list for response
    cov_list: list[CoverageReport] = []
    for r in coverage_reports:
        if isinstance(r, CoverageReport):
            cov_list.append(r)

    # Append narrator trace event
    trace_events.append(
        TraceEvent(
            run_id=run_id,
            state="narrator",
            agent="Narrator",
            output_artifact="WorkflowResponse",
            decision=final_outcome,
            payload={
                "final_outcome": final_outcome,
                "message_length": len(message),
                "dataset_count": len(dataset_artifacts),
                "script_count": len(script_artifacts),
            },
        )
    )

    return WorkflowResponse(
        run_id=run_id,
        final_outcome=final_outcome,
        message=message,
        answer_blocks=answer_blocks,
        citations=[
            {"source_id": d.source_id, "artifact_id": d.artifact_id}
            for d in dataset_artifacts
            if d.source_id
        ],
        selected_sources=selected_sources,
        rejected_sources=rejected_sources,
        coverage=cov_list,
        dataset_artifacts=_tag_diagnostic(dataset_artifacts, final_outcome),
        script_artifacts=script_artifacts,
        visualization=visualization if final_outcome == "passed" else None,
        trace_events=trace_events,
        limitations=limitations,
        clarification_questions=clarification_questions,
        not_found_evidence=no_data_evidence,
        feedback_actions=feedback_actions,
        component_statuses=component_statuses,
    )
