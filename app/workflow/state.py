"""Phase 2 typed workflow state and LLM service functions.

Defines Phase2State(TypedDict) as the single state object through the graph,
plus analyze_intent and design_research backed by real Qwen (Yandex AI Studio) calls.
"""
from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, field_validator, model_validator

from app.artifacts.workflow_artifacts import (
    AmbiguityPolicy,
    DatasetArtifact,
    DimensionConstraints,
    DimensionIntent,
    EvidenceBundleArtifact,
    ExtractionPlan,
    GeographyIntent,
    IntentFrame,
    MeasureIntent,
    OperationIntent,
    PeriodIntent,
    ResearchDesignArtifact,
    RetrievalInput,
    RetrievalSourceScope,
    ScriptArtifact,
    SearchProbe,
    SourceBudgetPolicy,
    SourceScope,
    TaskIntent,
    TraceEvent,
    UserIntentArtifact,
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
    canonical_intent: UserIntentArtifact | None
    intent: IntentFrame | None
    retrieval_input: RetrievalInput | None
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


class _UserIntentAnalysisSchema(UserIntentArtifact):
    """Canonical structured Qwen output schema for durable user intent."""

    pass


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
        raise RuntimeError("Intent analysis requires a live LLM call through Yandex AI Studio / Qwen.")
    return analyze_user_intent(query, live_llm_required=live_llm_required).to_intent_frame()


def analyze_user_intent(
    query: str,
    *,
    live_llm_required: bool = True,
) -> UserIntentArtifact:
    """Analyze user intent into the canonical durable UserIntentArtifact."""
    if not live_llm_required:
        raise RuntimeError("Intent analysis requires a live LLM call through Yandex AI Studio / Qwen.")
    return _analyze_user_intent_live(query)


def _analyze_user_intent_live(query: str) -> UserIntentArtifact:
    """Call Yandex AI Studio Qwen structured output for intent analysis."""
    from app.llm.yandex_ai_studio import YandexAIStudioClient, qwen_credential_gate

    gate = qwen_credential_gate()
    if gate["status"] == "gated_skip":
        # Per D-37/D-38: never fake live success when credentials are missing
        raise RuntimeError(
            f"Qwen credentials are not configured (gated_skip). "
            f"Missing env vars: {gate['missing_env_vars']}. "
            f"Set up credentials before calling analyze_user_intent(live_llm_required=True)."
        )

    client = YandexAIStudioClient()
    system_prompt = (
        "Ты — ведущий эксперт-методолог по макроэкономической статистике DataAgent. "
        "Твоя задача — провести глубокий анализ запроса пользователя, классифицировать его "
        "и извлечь durable semantic intent для всего workflow. Источники: "
        "(Росстат/FedStat, World Bank, НЦСЭД/CKAN).\n\n"
        "ПРАВИЛА:\n"
        "1. Интерпретируй термины профессионально (например, 'динамика' = временной ряд).\n"
        "2. Определяй географию и периоды максимально точно.\n"
        "3. Если запрос неполный — запрашивай уточнение.\n"
        "4. ВАЖНО: needs_clarification=true только если запрос объективно неполный — "
        "не указана ни страна, ни период, ни предметная область. "
        "Составные концепты ('основные экономические показатели', 'макроэкономика', "
        "'социальные индикаторы', 'демографические показатели') — это НЕ повод для уточнения. "
        "Они хорошо известны и будут разложены на конкретные показатели автоматически. "
        "Если geography и period указаны, а indicator — составной концепт, "
        "ставь needs_clarification=false and category=research.\n"
        "5. Заполняй source_preferences только по явным подсказкам об источнике. "
        "Если пользователь упоминает Росстат, FedStat, Федстат, официальную российскую "
        "статистику или ЕМИСС, включай 'fedstat'. "
        "Если пользователь упоминает World Bank, Всемирный банк или WB, включай 'world_bank'. "
        "Если пользователь упоминает НЦСЭД, CKAN, package/resource, dataset/catalog "
        "или 5-значный код показателя, включай 'ckan'. "
        "Если есть несколько подсказок, включай все подходящие источники. "
        "Если явной подсказки об источнике нет, оставь source_preferences пустым списком, "
        "чтобы scouts могли искать по всем источникам.\n"
        "6. Возвращай UserIntentArtifact: task, measures, dimensions, operations, "
        "source_scope, ambiguity, assumptions. Разлагай составные концепты на несколько "
        "MeasureIntent. Не добавляй SearchProbe, retrieval budget, source-family search "
        "strings или guessed indicator codes. possible_indicator_codes заполняй только если "
        "пользователь явно указал код.\n"
        "Отвечай только в формате JSON согласно схеме."
    )
    user_prompt = (
        f"Запрос пользователя: {query}\n\n"
        "Определи:\n"
        "Верни canonical UserIntentArtifact:\n"
        "- task.category: direct_lookup | time_series | comparison | research | derived_metric | metadata_lookup | clarification_needed\n"
        "- measures: конкретные показатели, с official terms и aliases\n"
        "- dimensions: geographies, period, frequency, breakdowns\n"
        "- operations: флаги сравнения, временного ряда, темпов роста и т.п.\n"
        "- source_scope: explicit source hints/constraints only\n"
        "- ambiguity: blocking clarification policy"
    )

    result = client.structured_chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        schema=_UserIntentAnalysisSchema,
        temperature=0.0,
        max_tokens=2048,
    )

    if isinstance(result, UserIntentArtifact):
        return _sanitize_user_intent(result, query)
    return _legacy_intent_schema_to_user_intent(query, result)


def _sanitize_user_intent(intent: UserIntentArtifact, query: str) -> UserIntentArtifact:
    """Remove retrieval-only fields the LLM may have guessed into semantic intent."""
    dumped = intent.model_dump()
    explicit_query = query.lower()
    for measure in dumped.get("measures", []):
        codes = measure.get("possible_indicator_codes") or []
        measure["possible_indicator_codes"] = [
            str(code) for code in codes if str(code).lower() in explicit_query
        ]
    return UserIntentArtifact.model_validate(dumped)


def _legacy_intent_schema_to_user_intent(query: str, result: Any) -> UserIntentArtifact:
    """Compatibility for tests/older mocks that still return _IntentAnalysisSchema."""
    known_fields: dict[str, Any] = {}
    geography = getattr(result, "geography", None)
    countries = list(getattr(result, "countries", []) or [])
    period = getattr(result, "period", None)
    indicator = getattr(result, "indicator", None)
    category = getattr(result, "category", "simple")
    needs_clarification = bool(getattr(result, "needs_clarification", False))
    source_preferences = list(getattr(result, "source_preferences", []) or [])
    missing_fields = list(getattr(result, "missing_fields", []) or [])

    if geography:
        known_fields["geography"] = result.geography
    if countries:
        known_fields["countries"] = countries
    elif geography:
        countries = [c.strip() for c in str(geography).split(",") if c.strip()]
    if period:
        known_fields["period"] = period
    if indicator:
        known_fields["indicator"] = indicator

    task_category: dict[str, str] = {
        "simple": "direct_lookup",
        "comparative": "comparison",
        "research": "research",
        "derived_metric": "derived_metric",
        "ambiguous": "clarification_needed",
        "no_data": "metadata_lookup",
    }
    measure = MeasureIntent(
        measure_id="m1",
        user_phrase=str(indicator or query),
        canonical_concept=str(indicator or query),
        aliases_ru=[str(indicator)] if indicator else [],
        measurement_form="unknown",
    )
    return UserIntentArtifact(
        original_query=query,
        task=TaskIntent(
            category=task_category.get(str(category), "direct_lookup"),  # type: ignore[arg-type]
            user_goal=query,
            expected_output="answer",
        ),
        measures=[measure] if indicator else [],
        dimensions=DimensionIntent(
            geographies=[GeographyIntent(name=str(country)) for country in countries],
            period=PeriodIntent(values=[str(period)]) if period else None,
            frequency="unknown",
        ),
        operations=OperationIntent(
            wants_comparison=str(category) == "comparative",
            wants_time_series=str(category) in {"comparative", "research"},
        ),
        source_scope=SourceScope(
            requested_sources=source_preferences,
            source_constraint="soft_preference" if source_preferences else "none",
            source_hints=source_preferences,
        ),
        ambiguity=AmbiguityPolicy(
            needs_clarification=needs_clarification,
            blocking_missing_fields=missing_fields,
        ),
        assumptions=[],
        rejected_interpretations=[],
        confidence=0.0,
    )


class _PlannerProbeSchema(BaseModel):
    probe_id: str | None = None
    text: str
    purpose: Literal[
        "raw_query_fallback",
        "canonical_concept",
        "official_term",
        "alias",
        "source_specific",
        "indicator_code",
        "broad_fallback",
    ]
    measure_id: str | None = None
    language: Literal["ru", "en", "mixed", "code"] = "mixed"
    priority: int = 50
    source_family_hint: Literal["fedstat", "world_bank", "ckan"] | None = None
    basis: str | None = None
    origin: Literal["llm", "mechanical_fallback"] = "llm"


class _RetrievalPlannerSchema(BaseModel):
    original_query: str | None = None
    probes: list[_PlannerProbeSchema] = []
    dimension_constraints: DimensionConstraints = DimensionConstraints()
    source_scope: RetrievalSourceScope = RetrievalSourceScope()
    budget_policy: SourceBudgetPolicy = SourceBudgetPolicy()
    trace_notes: list[str] = []


def plan_retrieval(intent: UserIntentArtifact) -> RetrievalInput:
    """Call Qwen/Yandex to convert durable intent into transient search probes."""
    return _plan_retrieval_live(intent)


def _plan_retrieval_live(intent: UserIntentArtifact) -> RetrievalInput:
    """Call Yandex AI Studio Qwen structured output for RetrievalInput planning."""
    from app.llm.yandex_ai_studio import YandexAIStudioClient, qwen_credential_gate

    gate = qwen_credential_gate()
    if gate["status"] == "gated_skip":
        raise RuntimeError(
            "retrieval_planner_llm_unavailable: Qwen credentials are not configured "
            f"(missing={gate['missing_env_vars']})"
        )

    client = YandexAIStudioClient()
    system_prompt = (
        "Ты — Retrieval Planner DataAgent. Твоя задача — превратить durable "
        "UserIntentArtifact в transient RetrievalInput для поиска source-card metadata.\n\n"
        "Жесткие правила:\n"
        "- Сгенерируй primary probes сам как LLM structured output; не проси deterministic code "
        "строить primary probes.\n"
        "- Probes ищут карточки источников/наборов данных, не строки таблиц и не финальные числа.\n"
        "- Делай probes measure-centric: короткий текст показателя, official terms, aliases, "
        "source-family wording.\n"
        "- Если source_scope.source_constraint == 'none', верни LLM-origin probes для fedstat, "
        "world_bank и ckan по каждому measure.\n"
        "- Не включай годы, страны, country groups (например BRICS/БРИКС), analysis verbs "
        "('сравни', 'проанализируй', 'динамика') и requested output shape в primary probe.text.\n"
        "- Положи period/geographies/geography_group/frequency в dimension_constraints.\n"
        "- Raw user query можно включить только как low-priority raw_query_fallback с "
        "origin='mechanical_fallback'; если опустишь, система добавит его механически.\n"
        "- Primary probes должны иметь origin='llm'.\n"
        "- Не выбирай final source count и не утверждай, что данные существуют.\n"
        "Возвращай только JSON согласно схеме."
    )
    user_prompt = (
        "Построй RetrievalInput для этого UserIntentArtifact:\n"
        f"{intent.model_dump_json(indent=2)}"
    )

    result = client.structured_chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        schema=_RetrievalPlannerSchema,
        temperature=0.0,
        max_tokens=3072,
    )
    return _postprocess_retrieval_plan(intent, result)


def _postprocess_retrieval_plan(
    intent: UserIntentArtifact,
    planner_output: _RetrievalPlannerSchema,
) -> RetrievalInput:
    constraints = _dimension_constraints_from_intent(intent)
    source_scope = RetrievalSourceScope.from_source_scope(intent.source_scope)
    valid_measure_ids = {measure.measure_id for measure in intent.measures}
    trusted_families = {"fedstat", "world_bank", "ckan"}
    hard_families = (
        set(source_scope.requested_sources)
        if source_scope.source_constraint == "hard_only" and source_scope.requested_sources
        else trusted_families
    )

    probes: list[SearchProbe] = []
    seen: set[tuple[str, str, str | None, str | None]] = set()
    used_ids: set[str] = set()
    raw_fallback_seen = False

    for raw_probe in planner_output.probes:
        text = " ".join(str(raw_probe.text).split())
        if not text:
            continue
        family = raw_probe.source_family_hint
        if family not in trusted_families:
            family = None
        if family is not None and family not in hard_families:
            continue

        purpose = raw_probe.purpose
        measure_id = raw_probe.measure_id if raw_probe.measure_id in valid_measure_ids else None
        if purpose != "raw_query_fallback" and intent.measures and measure_id is None:
            continue

        origin: Literal["llm", "mechanical_fallback"] = "llm"
        priority = _clamp_int(raw_probe.priority, 1, 100)
        basis = raw_probe.basis
        if purpose == "raw_query_fallback":
            if raw_fallback_seen:
                continue
            raw_fallback_seen = True
            origin = "mechanical_fallback"
            measure_id = None
            family = None
            priority = min(priority, 10)
            basis = basis or "Mechanical fallback for provenance and recall only"

        key = (text.lower(), purpose, measure_id, family)
        if key in seen:
            continue
        seen.add(key)
        probe_id = _stable_probe_id(raw_probe.probe_id, used_ids, len(probes) + 1, purpose)
        probes.append(
            SearchProbe(
                probe_id=probe_id,
                text=text,
                purpose=purpose,
                measure_id=measure_id,
                language=raw_probe.language or _guess_probe_language(text),
                priority=priority,
                source_family_hint=family,
                basis=basis,
                origin=origin,
            )
        )

    primary_probes = [
        probe for probe in probes
        if probe.purpose != "raw_query_fallback" and probe.origin == "llm"
    ]
    if intent.measures and not primary_probes:
        raise RuntimeError("llm_primary_probes_missing: Retrieval Planner returned no LLM-origin primary probes")

    _validate_required_family_coverage(intent, source_scope, primary_probes)

    if not any(probe.purpose == "raw_query_fallback" for probe in probes):
        probe_id = _stable_probe_id("p_raw_fallback", used_ids, len(probes) + 1, "raw_query_fallback")
        probes.append(
            SearchProbe(
                probe_id=probe_id,
                text=intent.original_query,
                purpose="raw_query_fallback",
                measure_id=None,
                language=_guess_probe_language(intent.original_query),
                priority=10,
                source_family_hint=None,
                basis="Mechanical fallback for provenance and recall only",
                origin="mechanical_fallback",
            )
        )

    budget = SourceBudgetPolicy(
        per_probe_limit=_clamp_int(planner_output.budget_policy.per_probe_limit, 1, 10),
        max_total_candidates=planner_output.budget_policy.max_total_candidates,
        final_source_count=None,
    )
    trace_notes = list(planner_output.trace_notes)
    trace_notes.append("Primary probes generated by Qwen/Yandex structured output.")
    trace_notes.append("Intent dimensions/source scope preserved by deterministic post-processing.")

    return RetrievalInput(
        original_query=intent.original_query,
        probes=sorted(probes, key=lambda probe: probe.priority, reverse=True),
        dimension_constraints=constraints,
        source_scope=source_scope,
        budget_policy=budget,
        trace_notes=trace_notes,
    )


def _dimension_constraints_from_intent(intent: UserIntentArtifact) -> DimensionConstraints:
    periods = intent.dimensions.period.expanded_values() if intent.dimensions.period else []
    period_start: int | None = None
    period_end: int | None = None
    if intent.dimensions.period:
        if intent.dimensions.period.start and intent.dimensions.period.start.isdigit():
            period_start = int(intent.dimensions.period.start)
        if intent.dimensions.period.end and intent.dimensions.period.end.isdigit():
            period_end = int(intent.dimensions.period.end)
    if period_start is None and periods and periods[0].isdigit():
        period_start = int(periods[0])
    if period_end is None and periods and periods[-1].isdigit():
        period_end = int(periods[-1])

    geography_group = next(
        (geo.group for geo in intent.dimensions.geographies if geo.group),
        None,
    )
    return DimensionConstraints(
        geographies=[geo.iso3 or geo.name for geo in intent.dimensions.geographies],
        geography_group=geography_group,
        periods=periods,
        period_start=period_start,
        period_end=period_end,
        frequency=intent.dimensions.frequency,
        breakdowns=list(intent.dimensions.breakdowns),
    )


def _stable_probe_id(
    raw_probe_id: str | None,
    used_ids: set[str],
    index: int,
    purpose: str,
) -> str:
    candidate = (raw_probe_id or "").strip() or (
        "p_raw_fallback" if purpose == "raw_query_fallback" else f"p{index}"
    )
    if candidate not in used_ids:
        used_ids.add(candidate)
        return candidate
    suffix = 2
    while f"{candidate}_{suffix}" in used_ids:
        suffix += 1
    unique = f"{candidate}_{suffix}"
    used_ids.add(unique)
    return unique


def _validate_required_family_coverage(
    intent: UserIntentArtifact,
    source_scope: RetrievalSourceScope,
    primary_probes: list[SearchProbe],
) -> None:
    if not intent.measures:
        return
    if source_scope.source_constraint != "none" or source_scope.requested_sources:
        return
    missing: list[str] = []
    for measure in intent.measures:
        families = {
            probe.source_family_hint
            for probe in primary_probes
            if probe.measure_id == measure.measure_id
        }
        for family in ["world_bank", "fedstat", "ckan"]:
            if family not in families:
                missing.append(f"{measure.measure_id}:{family}")
    if missing:
        raise RuntimeError(
            "llm_primary_probe_family_coverage_missing: " + ", ".join(missing)
        )


def _clamp_int(value: int | None, minimum: int, maximum: int) -> int:
    try:
        number = int(value) if value is not None else minimum
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


def _guess_probe_language(text: str) -> str:
    has_cyrillic = any("а" <= ch.lower() <= "я" or ch == "ё" for ch in text)
    has_latin = any("a" <= ch.lower() <= "z" for ch in text)
    if text.replace(".", "").replace("_", "").replace("-", "").isdigit():
        return "code"
    if has_cyrillic and has_latin:
        return "mixed"
    if has_cyrillic:
        return "ru"
    if has_latin:
        return "en"
    return "mixed"


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
        raise RuntimeError("Research design requires a live LLM call through Yandex AI Studio / Qwen.")
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
        "Ты — архитектор экономических исследований DataAgent. "
        "Твоя задача — спроектировать структуру глубокого исследования на основе намерения пользователя.\n\n"
        "ПРАВИЛА:\n"
        "1. Формулируй гипотезы на языке экономической теории.\n"
        "2. Определяй необходимые измерения и конкретные индикаторы для поиска в БД.\n"
        "3. Указывай методологические допущения (например, использование ППС или реальных цен).\n"
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
        max_tokens=1024,
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
