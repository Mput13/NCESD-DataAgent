# Intent Analyst and Retrieval Planner Vision - 2026-05-18

Status: detailed layer vision and pre-ADR context.

This document preserves the detailed design discussion for the first two layers
of the DataAgent workflow refactor:

`Intent Analyst -> Retrieval Planner`

Read this together with:

- `docs/superpowers/specs/2026-05-18-workflow-refactor-context.md`
- `docs/superpowers/specs/2026-05-18-workflow-intent-retrieval-v2.md`

This is not an implementation plan. Before code changes, create a small ADR for
the selected slice and get explicit user approval.

## Why These Layers Matter

The current workflow has a weak handoff:

`raw query -> HybridRetriever.search(...)`

The current `IntentFrame` extracts a small amount of structure, but retrieval is
still driven mostly by the raw user text. This forces retriever code to contain
handwritten statistical semantics: synonym maps, phrase rules, stopwords,
minimum-overlap logic, and special cases for concepts such as GDP, inflation, and
share.

Target principle:

LLM owns semantic understanding. Deterministic code owns execution, validation,
filtering, ranking mechanics, extraction, and trace.

## Target Split

### Intent Analyst

Question answered:

> What does the user mean?

The Intent Analyst is a live Qwen/Yandex structured-output node. It converts the
user query into a semantic artifact. It does not retrieve sources and does not
decide final candidates.

### Retrieval Planner

Question answered:

> How should this intent be searched in our source-card corpus?

The Retrieval Planner converts semantic intent into source-card search probes and
search strategy. It does not know the actual RAG result set, so it must not decide
the final number of source candidates required for correctness.

## Intent Analyst Contract

### Input

- original user query;
- optional conversation state for clarification follow-up;
- trusted source universe from system prompt:
  - Rosstat/FedStat/EMISS;
  - World Bank;
  - NSED/CKAN.

### Output

Canonical output should be `UserIntentArtifact`.

Conceptual schema:

```python
class UserIntentArtifact(BaseModel):
    original_query: str
    task: TaskIntent
    measures: list[MeasureIntent]
    dimensions: DimensionIntent
    operations: OperationIntent
    source_scope: SourceScope
    ambiguity: AmbiguityPolicy
    assumptions: list[str]
    rejected_interpretations: list[str]
    confidence: float
```

The artifact must be trace-visible. It is the semantic source of truth for
retrieval planning.

### Allowed Semantic Work

The Intent Analyst may use LLM knowledge for:

- professional interpretation of statistical/economic terms;
- Russian/English normalization;
- Rosstat/FedStat, World Bank, and NSED/CKAN terminology;
- compound concept decomposition;
- aliases and official terms useful for source-card retrieval;
- likely indicator names and codes;
- expected unit/form/frequency/dimension;
- operation flags: time series, comparison, ranking, growth, share, per-capita,
  real/nominal terms, visualization.

### Prohibited Work

The Intent Analyst must not:

- select final source cards;
- call retrievers;
- decide numeric values;
- fake coverage;
- silently invent required missing constraints;
- hard-filter sources unless the user explicitly requested a source restriction;
- decide final candidate/source count.

### TaskIntent

The target task categories are:

- `direct_lookup`
- `time_series`
- `comparison`
- `research`
- `derived_metric`
- `metadata_lookup`
- `clarification_needed`

The old categories in `IntentFrame` are compatibility-only and should not be the
long-term semantic contract.

### MeasureIntent

Every requested measure should become a structured measure. A query may contain
one measure or many.

For each measure capture:

- user phrase;
- canonical concept;
- Russian aliases;
- English aliases;
- Russian official terms;
- English official terms;
- possible indicator names;
- possible indicator codes;
- measurement form;
- unit expectation;
- concepts that must not be confused with it.

Compound concepts must be decomposed by the LLM. Example:

`основные экономические показатели России за 2000-2013`

should produce concrete measures such as GDP, inflation/CPI, unemployment,
industrial production, population, income/wages, depending on wording and source
domain.

The exact decomposed list belongs in `UserIntentArtifact` and must be visible in
trace. It should not be hidden inside retrieval code.

### DimensionIntent

Capture:

- geographies as user phrase plus normalized candidates;
- period as user phrase plus start/end/explicit periods when available;
- frequency;
- breakdowns.

Important: LLM normalization is a semantic hint, not deterministic source
coverage. Source adapters later validate real coverage.

Open detail to resolve by ADR: exact fields for `GeographyIntent`,
`PeriodIntent`, and `DimensionConstraints`.

### SourceScope

Source preferences are explicit user intent, not guessed defaults.

Rules:

- If user says "только Росстат" or equivalent, use `hard_only`.
- If user merely mentions a source, use `soft_preference`.
- If no source is mentioned, use `requested_sources=[]` and
  `source_constraint="none"`.
- With no hard constraint, the system searches all trusted source families.

The Intent Analyst should distinguish source hints from final source selection.
Mentioning a source does not mean other trusted sources are unavailable unless the
user explicitly forbids them.

### AmbiguityPolicy

Clarification is blocking only when the request cannot be executed into a
defensible source-bound search.

Do not ask for clarification merely because a concept is broad but standard. If
geography and period make the task searchable, broad concepts can be decomposed
into measures and routed into retrieval.

Examples:

- `Дай данные по инфляции.` may need clarification because geography/period are
  missing.
- `Основные экономические показатели России за 2010-2020` should normally become
  a research intent with decomposed measures, not an immediate clarification.

### Migration Decision

Open implementation decision:

- replace current `IntentFrame` runtime contract directly with
  `UserIntentArtifact`; or
- add a temporary compatibility adapter.

Current recommendation:

Make `UserIntentArtifact` canonical. Keep `IntentFrame` only as a temporary
downstream adapter for existing coverage/extraction/narrator code until those
layers migrate.

## Retrieval Planner Contract

### Input

Required:

- `UserIntentArtifact`

Optional:

- `ResearchDesignArtifact` for complex research/comparison cases;
- prior clarification state;
- source availability summary if already known;
- budget policy defaults.

### Output

Canonical output should be `RetrievalInput`.

Conceptual schema:

```python
class RetrievalInput(BaseModel):
    original_query: str
    probes: list[SearchProbe]
    source_scope: SourceScope
    dimension_constraints: DimensionConstraints
    negative_constraints: list[str]
    expected_result_shape: str | None
    trace_notes: list[str]
```

`RetrievalInput` is what Source Scouts consume. RAG receives probes, not just the
raw query and not `json.dumps(intent)`.

### SearchProbe

Conceptual schema:

```python
class SearchProbe(BaseModel):
    text: str
    purpose: Literal[
        "raw_query_fallback",
        "canonical_concept",
        "official_term",
        "alias",
        "source_specific",
        "indicator_code",
        "compound_component",
        "broad_fallback",
    ]
    language: Literal["ru", "en", "mixed", "code"]
    measure_index: int | None
    priority: int
    source_family_hint: Literal["fedstat", "world_bank", "ckan"] | None
```

Priority is a planning hint, not evidence authority. Final source usefulness is
proved by coverage inventory and deterministic extraction.

### Planner Responsibilities

The Retrieval Planner owns:

- generating multiple probes per measure;
- keeping the original query as one low-priority fallback probe;
- generating stronger normalized probes from canonical concepts;
- emitting official-term probes;
- emitting alias probes in Russian and English;
- emitting source-specific probes when source terminology differs;
- preserving explicit source constraints;
- adding negative constraints from `must_not_confuse_with`;
- deriving initial dimension constraints as hints;
- producing trace notes explaining the search strategy.

### Planner Non-Responsibilities

The Retrieval Planner must not:

- select final source cards;
- decide final source count;
- decide that data exists;
- decide final `not_found`;
- overload retriever with dumped intent JSON;
- encode hidden fixed top-k correctness rules.

### Source Count and Budget Policy

Final candidate/source count cannot be known before retrieval. Intent and planner
do not know what is actually in RAG.

The planner may define execution controls:

- per-probe page size;
- max pages per probe;
- priority ordering;
- source-family hint ordering;
- stop/continue criteria;
- context packaging limits.

But these are not correctness criteria.

Correctness source count is determined after retrieval and coverage by:

- coverage sufficiency;
- source authority;
- explicit hard/soft source constraints;
- deduplication;
- extraction readiness;
- source diversity where required;
- downstream context budget;
- need for not_found evidence.

Useful conceptual policy:

```python
class SourceBudgetPolicy(BaseModel):
    per_probe_page_size: int
    max_pages_per_probe: int | None
    max_context_sources: int
    continue_until: list[str]
    stop_reason: str | None
```

`max_context_sources` limits what is passed into downstream LLM context. It is not
the total number of checked candidates.

### Probe Generation Rules

For each measure:

1. Add canonical concept probes.
2. Add official-term probes.
3. Add Russian and English alias probes.
4. Add indicator-code probes when codes are present or likely.
5. Add source-specific probes when useful:
   - FedStat/Rosstat terminology;
   - World Bank English indicator names/codes;
   - CKAN/NSED package/resource/search terminology.
6. Add broad fallback probes only after stronger probes exist.

For compound requests, produce probes per decomposed measure. Do not rely on one
raw compound query.

Example for `ВВП России за 2000-2013`:

```json
[
  {
    "text": "ВВП России за 2000-2013",
    "purpose": "raw_query_fallback",
    "language": "ru",
    "priority": 10
  },
  {
    "text": "ВВП валовой внутренний продукт",
    "purpose": "canonical_concept",
    "language": "ru",
    "priority": 100,
    "source_family_hint": "fedstat"
  },
  {
    "text": "gross domestic product GDP",
    "purpose": "alias",
    "language": "en",
    "priority": 95,
    "source_family_hint": "world_bank"
  },
  {
    "text": "валовой внутренний продукт в текущих ценах",
    "purpose": "official_term",
    "language": "ru",
    "priority": 95,
    "source_family_hint": "fedstat"
  }
]
```

### Interaction With Research Designer

Current graph has:

`intent_analyst -> research_designer -> source_scouts`

Accepted target graph:

`intent_analyst -> retrieval_planner -> source_scouts`

This section is superseded by
`2026-05-19-adr-intent-retrieval-boundary.md` and
`2026-05-19-retrieval-planner-implementation-spec.md`.

Pre-retrieval `Research Designer` is removed. For direct, research, and
comparison tasks, Retrieval Planner runs after Intent Analyst unless the request
is blocked for clarification. Any future later-stage Analysis Designer must run
after real sources and coverage are known.

## Source Scouts Handoff

Source Scouts receive `RetrievalInput`.

For each probe:

- call retriever with `probe.text`;
- use source scope to apply hard filters or soft preferences;
- use page size as an execution control;
- preserve probe evidence on every candidate;
- merge duplicates by stable source identity;
- keep rejected/duplicate/weak evidence traceable.

Candidate identity should be stable:

- FedStat: source family plus indicator/table/resource id;
- World Bank: indicator id;
- CKAN: package id plus resource id when available.

## Accepted Decisions

- Option 2 is accepted: separate Intent Analyst, Retrieval Planner, Source
  Scouts, mechanical Retriever, and coverage/extraction proof.
- RAG must receive structured `RetrievalInput.probes`.
- Raw query remains a fallback probe but must not be the only probe for statistical
  indicator requests.
- Domain semantics belong in live Qwen structured output and probes, not in
  retriever string heuristics.
- Retrieval Planner is a live LLM structured-output node. Deterministic code may
  post-process and validate planner output, but must not replace the planner with
  a deterministic-only transform over `UserIntentArtifact`.
- Source preferences are explicit user source constraints/hints, not guessed
  defaults.
- Fixed candidate/source counts are incorrect.
- Final source count is decided after retrieval/coverage by sufficiency, not by
  Intent Analyst or Retrieval Planner.
- Downstream agents receive curated evidence packages, not arbitrary top-k
  source dumps.

## Open Questions

Resolve these through ADRs before code:

1. Exact migration path from `IntentFrame` to `UserIntentArtifact`.
2. Exact `GeographyIntent`, `PeriodIntent`, and `DimensionConstraints` fields.
3. Exact prompt, schema constraints, and fallback behavior for the LLM Retrieval
   Planner node.
4. Exact `SourceBudgetPolicy` fields and defaults.
5. Whether Research Designer runs before planner for all complex queries or only
   when the intent artifact lacks enough measure/probe material.
6. Exact `CandidateProbeEvidence` and merged candidate schemas.
7. How `RetrievalInput` and planner decisions appear in trace/UI.
8. Minimal acceptance tests proving raw query is not the only retrieval input.

## Minimal Acceptance Tests For First Implementation Slice

Do not claim this layer is implemented until tests prove:

- `analyze_user_intent` or equivalent returns a trace-visible
  `UserIntentArtifact`.
- explicit source hints become `SourceScope`, not hidden string checks.
- no source hint means no hard filter and all trusted source families remain
  eligible.
- a direct GDP query produces at least one normalized semantic probe in addition
  to the original query.
- a compound economic-indicators query produces multiple measure-level probes.
- Retrieval Planner does not emit final candidate count.
- Source Scouts can preserve per-probe evidence on candidates.

## Guardrails

- Do not start by cleaning `HybridRetriever`; probes must exist first.
- Do not pass a dumped intent JSON blob into retriever as a shortcut.
- Do not let planner page size become final source-count correctness.
- Do not reduce Phase 2 acceptance to a small subset of golden cases.
- Do not add offline/no-response LLM fallback behavior for runtime intent.
- Keep old runtime compatibility only as a temporary adapter, not as a second
  semantic source of truth.
