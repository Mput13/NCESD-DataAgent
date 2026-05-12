"""Phase 2 typed workflow state and LLM service functions.

Defines Phase2State(TypedDict) as the single state object through the graph,
plus analyze_intent and design_research backed by real Qwen (Yandex AI Studio) calls.
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, field_validator, model_validator

from app.artifacts.workflow_artifacts import (
    DatasetArtifact,
    EvidenceBundleArtifact,
    ExtractionPlan,
    IntentFrame,
    ResearchDesignArtifact,
    ScriptArtifact,
    TraceEvent,
)

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Phase2State — single typed state object through the LangGraph
# ---------------------------------------------------------------------------


class Phase2State(TypedDict, total=False):
    """Typed state passed through the Phase 2 LangGraph workflow."""

    run_id: str
    query: str
    intent: IntentFrame | None
    research_design: ResearchDesignArtifact | None
    evidence: EvidenceBundleArtifact
    coverage_reports: list[Any]
    extraction_plan: ExtractionPlan | None
    dataset_artifacts: list[DatasetArtifact]
    script_artifacts: list[ScriptArtifact]
    final_outcome: str | None
    finalization_pending: bool
    pending_reason: str | None
    trace_events: list[TraceEvent]
    component_statuses: dict[str, str]


def new_run_id() -> str:
    """Return a new unique run ID with the 'phase2-' prefix."""
    return f"phase2-{uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Intent analysis — Qwen target path
# ---------------------------------------------------------------------------


class _IntentAnalysisSchema(BaseModel):
    """Structured Qwen output schema for intent analysis."""

    category: str
    needs_clarification: bool
    geography: str | None = None
    period: str | None = None
    indicator: str | None = None
    source_preferences: list[str] = []
    missing_fields: list[str] = []
    countries: list[str] = []

    @field_validator("geography", mode="before")
    @classmethod
    def _coerce_geography_list(cls, v: Any) -> str | None:
        if isinstance(v, list):
            return ", ".join(str(item) for item in v if item)
        return v

    @field_validator("countries", mode="before")
    @classmethod
    def _coerce_countries(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return [str(item) for item in v if item]
        if isinstance(v, str) and v:
            return [v]
        return v if v is not None else []

    @model_validator(mode="after")
    def _derive_countries_from_geography(self) -> "_IntentAnalysisSchema":
        """If countries not explicitly set, derive from geography."""
        if not self.countries and self.geography:
            self.countries = [c.strip() for c in self.geography.split(",") if c.strip()]
        return self

    @field_validator("source_preferences", "missing_fields", mode="before")
    @classmethod
    def _coerce_str_to_list(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v] if v else []
        return v if v is not None else []



def analyze_intent(
    query: str,
    *,
    live_llm_required: bool = True,
) -> IntentFrame:
    """Analyze user intent using Qwen structured output.

    Query processing requires live Yandex AI Studio / Qwen. The
    live_llm_required argument is retained for API compatibility, but disabling
    it is not supported.
    """
    if not live_llm_required:
        raise RuntimeError("Intent analysis requires live Yandex AI Studio / Qwen.")
    return _analyze_intent_live(query)


def _analyze_intent_live(query: str) -> IntentFrame:
    """Call Yandex AI Studio Qwen structured output for intent analysis."""
    from app.llm.yandex_ai_studio import YandexAIStudioClient, YandexAIStudioConfig, qwen_credential_gate

    gate = qwen_credential_gate()
    if gate["status"] == "gated_skip":
        # Per D-37/D-38: never fake live success when credentials are missing
        raise RuntimeError(
            f"Qwen credentials are not configured (gated_skip). "
            f"Missing env vars: {gate['missing_env_vars']}. "
            f"Set up credentials before calling analyze_intent(live_llm_required=True)."
        )

    client = YandexAIStudioClient()
    system_prompt = (
        "Ты — аналитик запросов данных. "
        "Классифицируй запрос пользователя и определи ключевые поля запроса. "
        "Отвечай только в формате JSON согласно схеме.\n\n"
        "ВАЖНО: needs_clarification=true только если запрос объективно неполный — "
        "не указана ни страна, ни период, ни предметная область. "
        "Составные концепты ('основные экономические показатели', 'макроэкономика', "
        "'социальные индикаторы', 'демографические показатели') — это НЕ повод для уточнения. "
        "Они хорошо известны и будут разложены на конкретные показатели автоматически. "
        "Если geography и period указаны, а indicator — составной концепт, "
        "ставь needs_clarification=false и category=research."
    )
    user_prompt = (
        f"Запрос: {query}\n\n"
        "Определи:\n"
        "- category: simple | comparative | research | derived_metric | ambiguous | no_data\n"
        "- needs_clarification: нужно ли уточнять запрос (true/false)\n"
        "- geography: страна или регион (null если не указано)\n"
        "- period: временной период (null если не указано)\n"
        "- indicator: название показателя (null если не указано)\n"
        "- source_preferences: предпочтительные источники (fedstat, world_bank, ckan)\n"
        "- missing_fields: какие поля необходимо уточнить"
    )

    result = client.structured_chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        schema=_IntentAnalysisSchema,
        temperature=0.0,
        max_tokens=512,
    )

    known_fields: dict[str, Any] = {}
    if result.geography:
        known_fields["geography"] = result.geography
    if result.countries:
        known_fields["countries"] = result.countries
    elif result.geography:
        # Fallback: derive countries from geography string for multi-country queries
        known_fields["countries"] = [c.strip() for c in result.geography.split(",") if c.strip()]
    if result.period:
        known_fields["period"] = result.period
    if result.indicator:
        known_fields["indicator"] = result.indicator

    valid_categories = {"simple", "comparative", "research", "derived_metric", "ambiguous", "no_data"}
    category = result.category if result.category in valid_categories else "simple"

    return IntentFrame(
        query=query,
        category=category,  # type: ignore[arg-type]
        known_fields=known_fields,
        missing_fields=result.missing_fields,
        needs_clarification=result.needs_clarification,
        source_preferences=result.source_preferences,
        open_reasoning=["Qwen structured output via Yandex AI Studio"],
    )


# ---------------------------------------------------------------------------
# Research design — Qwen structured output target path
# ---------------------------------------------------------------------------


class _ResearchDesignSchema(BaseModel):
    """Structured Qwen output schema for research design."""

    hypotheses: list[str] = []
    dimensions: list[str] = []
    indicators: list[str] = []
    grouping_policy: str | None = None
    assumptions: list[str] = []
    expanded_indicators: list[dict] = []


def design_research(
    intent: IntentFrame,
    *,
    live_llm_required: bool = True,
    matrix_hint: dict[str, Any] | None = None,
) -> ResearchDesignArtifact:
    """Design a research plan from intent using Qwen structured output.

    matrix_hint: optional dict from golden-coverage-matrix.json providing
    source_family, source_id, filters, and expected terminal outcome.
    """
    if not live_llm_required:
        raise RuntimeError("Research design requires live Yandex AI Studio / Qwen.")
    return _design_research_live(intent, matrix_hint=matrix_hint)


def _design_research_live(
    intent: IntentFrame,
    *,
    matrix_hint: dict[str, Any] | None = None,
) -> ResearchDesignArtifact:
    """Call Yandex AI Studio Qwen to design the research structure."""
    from app.llm.yandex_ai_studio import YandexAIStudioClient, qwen_credential_gate

    gate = qwen_credential_gate()
    if gate["status"] == "gated_skip":
        raise RuntimeError(
            f"Qwen credentials are not configured (gated_skip). "
            f"Missing: {gate['missing_env_vars']}."
        )

    client = YandexAIStudioClient()
    hint_text = ""
    if matrix_hint:
        hint_text = (
            f"\nПодсказка из матрицы покрытия: источник={matrix_hint.get('source_family')}, "
            f"id={matrix_hint.get('source_id')}, фильтры={matrix_hint.get('filters')}."
        )

    system_prompt = (
        "Ты — аналитик-исследователь данных. "
        "Спроектируй структуру исследования на основе намерения пользователя. "
        "Отвечай только в формате JSON согласно схеме."
    )
    user_prompt = (
        f"Намерение: {intent.query}\n"
        f"Категория: {intent.category}\n"
        f"Известные поля: {intent.known_fields}\n"
        f"Предпочтительные источники: {intent.source_preferences}\n"
        f"{hint_text}\n\n"
        "Спроектируй исследование:\n"
        "- hypotheses: список гипотез исследования\n"
        "- dimensions: измерения (география, период, индикатор)\n"
        "- indicators: конкретные показатели для поиска\n"
        "- grouping_policy: политика группировки (null если не требуется)\n"
        "- assumptions: допущения исследования\n"
        "- expanded_indicators: если запрос содержит агрегатный концепт "
        "(например 'основные экономические показатели', 'макроэкономика', 'социальные индикаторы', "
        "'демографические показатели'), используй свои знания и разложи его на 3-7 конкретных "
        "экономических показателей. Для каждого укажи: "
        "  name_ru (название по-русски), "
        "  name_en (название по-английски), "
        "  search_query_ru (короткая поисковая фраза на русском, 2-5 слов), "
        "  search_query_en (короткая поисковая фраза на английском, 2-5 слов). "
        "Если запрос уже конкретен — оставь expanded_indicators пустым списком."
    )

    artifact_id = f"research-design-{uuid4().hex[:8]}"

    result = client.structured_chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        schema=_ResearchDesignSchema,
        temperature=0.0,
        max_tokens=512,
    )

    return ResearchDesignArtifact(
        artifact_id=artifact_id,
        route=intent.category,
        hypotheses=result.hypotheses,
        dimensions=result.dimensions,
        indicators=result.indicators,
        grouping_policy=result.grouping_policy,
        assumptions=result.assumptions,
        expanded_indicators=result.expanded_indicators,
    )
