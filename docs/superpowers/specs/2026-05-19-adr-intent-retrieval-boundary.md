# ADR: Intent Analyst and Retrieval Planner Boundary - 2026-05-19

Status: accepted architecture decision and implementation planning artifact.

This ADR supersedes the pre-retrieval `Research Designer` route described in
earlier Phase 2 workflow plans. It refines, but does not replace, the broader
Option 2 direction in `2026-05-18-workflow-intent-retrieval-v2.md`.

Related guardrail: `2026-05-19-agent-artifact-drift-negative-example.md` records
the negative case where stale deterministic-planner language was accidentally
carried into artifacts and led toward an incorrect deterministic-only Retrieval
Planner implementation.

Implementation source of truth for Slice 2:
`2026-05-19-retrieval-planner-implementation-spec.md`.

## Decision

The pre-retrieval workflow is:

```text
Intent Analyst -> Retrieval Planner -> Source Scouts
```

`Research Designer` is removed from the pre-retrieval path.

A later-stage `Analysis Designer` remains a future design candidate after real
sources and coverage are known:

```text
Coverage Inventory -> Source Selection -> Analysis Designer? -> Extraction Mapping
```

## Why

The previous pre-retrieval `Research Designer` duplicated the responsibilities of
both Intent Analyst and Retrieval Planner:

- if it decomposes broad user concepts into concrete measures, that belongs to
  Intent Analyst;
- if it improves source-card search text, that belongs to Retrieval Planner;
- if it designs analysis methodology before sources are known, it is guessing.

The workflow needs one durable semantic artifact and one transient search artifact:

- `UserIntentArtifact` answers: what did the user ask for?
- `RetrievalInput` answers: how should source-card metadata be searched?

These artifacts must not become competing sources of semantic truth.

## Not Doing

- Do not keep pre-retrieval `Research Designer`.
- Do not pass raw user query alone into source-card RAG.
- Do not pass dumped intent JSON into retriever.
- Do not put `SearchProbe`, retrieval budget, or source-family search strings into
  `UserIntentArtifact`.
- Do not put guessed source-specific indicator codes into `UserIntentArtifact`
  unless the user explicitly supplied the identifier.
- Do not use years, country lists, or groups in RAG probe text by default when the
  RAG corpus is source-card metadata.
- Do not make `RetrievalInput` the semantic source of truth after sources are
  discovered.

## Contract

### UserIntentArtifact

`UserIntentArtifact` is durable and should remain available through retrieval,
coverage, source selection, extraction, critic, narrator, UI, and eval artifacts.

It captures user meaning:

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

Intent owns:

- task type and expected output;
- semantic measures, including compound concept decomposition;
- measure roles such as `primary`, `supporting`, `numerator`, `denominator`,
  `normalizer`, and `context`;
- measurement form such as `level`, `rate`, `growth`, `share`, `index`,
  `per_capita`, `absolute_change`, or `unknown`;
- related-but-distinct concepts, without treating them as hard exclusions;
- dimensions: geography, period, frequency, breakdowns;
- operation flags: time series, comparison, ranking, growth, share, per-capita,
  real/nominal terms, visualization;
- explicit user source constraints and explicit user-provided source identifiers;
- ambiguity and clarification policy.

Intent does not own:

- RAG/search probes;
- source-family-specific search text;
- guessed indicator codes;
- retrieval priority;
- retrieval budget;
- final source count;
- source selection;
- coverage verdicts;
- numeric values.

### RetrievalInput

`RetrievalInput` is transient. It is consumed by Source Scouts and retained in
trace/provenance, but downstream semantic reasoning should continue to use
`UserIntentArtifact`.

It captures the search program:

```python
class RetrievalInput(BaseModel):
    original_query: str
    probes: list[SearchProbe]
    dimension_constraints: DimensionConstraints
    source_scope: RetrievalSourceScope
    budget_policy: SourceBudgetPolicy
    trace_notes: list[str]
```

Search probes are metadata-aware:

```python
class SearchProbe(BaseModel):
    probe_id: str
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
    measure_id: str | None
    language: Literal["ru", "en", "mixed", "code"]
    priority: int
    source_family_hint: Literal["fedstat", "world_bank", "ckan"] | None
    basis: str | None
```

For source-card metadata RAG, `probe.text` should usually contain:

- measure name;
- official term;
- aliases;
- source-family terminology;
- source/dataset/indicator codes when used as planner hypotheses.

`probe.text` should not normally contain:

- years;
- full country lists;
- country groups such as BRICS;
- analysis verbs like "проанализируй", "сравни", "динамика";
- requested output shape.

Those belong in:

- `dimension_constraints`;
- coverage requirements;
- downstream source selection.

Exception: Retrieval Planner may create a low-priority dimension-aware probe only
when source-card metadata is known to include geography or period text that helps
recall.

### Source Scouts

Source Scouts consume `RetrievalInput`.

They:

- execute probes against retrievers and bounded source-family adapters;
- apply hard source constraints only when `source_constraint="hard_only"`;
- treat soft preferences and source-family hints as ordering/boosting hints;
- merge duplicate candidates by stable source identity;
- preserve per-probe evidence for every candidate;
- keep rejected/duplicate/weak evidence traceable;
- pass a candidate pool into Coverage Inventory.

They do not:

- perform semantic query expansion;
- decide final source sufficiency;
- decide final `not_found`;
- generate additional meaning beyond probes.

## Metadata RAG Query Principle

The ideal RAG query is not the user question. It is a short source-card metadata
query for one semantic measure.

Example user query:

```text
Проанализируй основные экономические показатели стран БРИКС за 2015-2024 годы и сравни динамику.
```

Intent decomposes the request into measures and dimensions:

- measures: GDP, inflation/CPI, unemployment rate, population, etc.;
- geographies: BRICS members;
- period: 2015-2024;
- frequency: annual;
- operations: comparison and time series.

Retrieval Planner should search source-card metadata with measure-centric probes,
for example:

```json
[
  {
    "probe_id": "p1",
    "measure_id": "m1",
    "source_family_hint": "fedstat",
    "text": "валовой внутренний продукт",
    "purpose": "official_term",
    "language": "ru",
    "priority": 100
  },
  {
    "probe_id": "p2",
    "measure_id": "m1",
    "source_family_hint": "world_bank",
    "text": "gross domestic product GDP",
    "purpose": "alias",
    "language": "en",
    "priority": 100
  },
  {
    "probe_id": "p3",
    "measure_id": "m1",
    "source_family_hint": "ckan",
    "text": "валовой внутренний продукт набор данных ресурс",
    "purpose": "source_specific",
    "language": "ru",
    "priority": 80
  },
  {
    "probe_id": "p4",
    "measure_id": "m2",
    "source_family_hint": "world_bank",
    "text": "inflation consumer price index CPI",
    "purpose": "alias",
    "language": "en",
    "priority": 95
  }
]
```

The same retrieval input separately carries the requested slice:

```json
{
  "dimension_constraints": {
    "geographies": ["BRA", "RUS", "IND", "CHN", "ZAF"],
    "periods": ["2015", "2016", "2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024"],
    "frequency": "annual"
  }
}
```

Coverage Inventory later proves whether a candidate source actually contains that
slice.

## Interactions

The next target architecture is:

```text
User query
-> Intent Analyst
   output: UserIntentArtifact
-> Retrieval Planner
   input: UserIntentArtifact
   output: RetrievalInput
-> Source Scouts
   input: RetrievalInput
   output: SourceCandidatePool with per-probe evidence
-> Coverage Inventory
   input: UserIntentArtifact + SourceCandidatePool
```

`RetrievalInput` remains in trace/provenance. It does not replace
`UserIntentArtifact` downstream.

## Implementation Plan

This is a serious workflow rewrite. Do it in slices.

### Slice 1 - Intent Contract

Add canonical intent schemas and live Qwen structured output:

- `UserIntentArtifact`;
- task, measure, geography, period, dimensions, operations, source scope,
  ambiguity schemas;
- temporary adapter from `UserIntentArtifact` to current `IntentFrame`;
- trace visibility for the canonical intent artifact.

Acceptance:

- complex macro request decomposes into multiple measures;
- broad but executable requests do not become blocking clarification;
- explicit source hints become source scope;
- no source hint keeps all trusted families eligible;
- intent artifact contains no search probes, retrieval budget, or guessed source
  codes unless explicitly user-provided.

### Slice 2 - Retrieval Planner Contract

Add retrieval schemas and a live LLM structured-output planner node:

- `RetrievalInput`;
- `SearchProbe`;
- `DimensionConstraints`;
- `RetrievalSourceScope`;
- `SourceBudgetPolicy`.

Acceptance:

- planner consumes only `UserIntentArtifact`;
- planner calls live Qwen/Yandex structured output for primary probe generation;
- planner emits measure-centric metadata probes;
- planner emits probes for FedStat, World Bank, and CKAN when source scope is
  `none`;
- planner keeps years/geographies out of probe text by default;
- planner passes years/geographies/frequency as constraints;
- planner does not choose final source count.
- deterministic code is limited to schema validation, stable IDs, explicit
  constraint preservation, safety bounds, and traceable raw-query fallback; it
  must not replace the planner with deterministic-only probe generation.

Negative example to avoid: do not phrase this slice as "deterministic
transformation over LLM-produced fields." That wording contradicts this ADR
because it lets future agents implement the planner without an LLM structured
output call.

For the exact runtime workflow, prompt requirements, BRICS example, Source Scouts
handoff, and acceptance tests, use
`2026-05-19-retrieval-planner-implementation-spec.md`.

### Slice 3 - Graph Rewire

Change the graph from:

```text
intent_analyst -> research_designer -> source_scouts
```

to:

```text
intent_analyst -> retrieval_planner -> source_scouts
```

Keep legacy `ResearchDesignArtifact` compatibility only where older finalization
or tests still need it, but remove it from the pre-retrieval execution path.

Acceptance:

- research and comparison queries route through retrieval planner, not research
  designer;
- direct lookup also routes through retrieval planner;
- missing LLM credentials produce gated artifacts, not fake fallback intent.

### Slice 4 - Source Scouts Consume RetrievalInput

Refactor scouts to execute multiple probes:

- per-probe retrieval calls;
- source scope handling;
- stable dedupe;
- per-probe evidence on candidates;
- rejected/duplicate candidate evidence.

Acceptance:

- raw query is not the only retrieval input;
- no arbitrary top-k dump becomes downstream LLM context;
- candidates retain probe evidence;
- hard source filters apply only for explicit hard source constraints.

### Slice 5 - Retriever Semantic Cleanup

Only after probes are in place, remove product semantics from retriever:

- economic synonym maps;
- concept parsers;
- GDP/inflation/share special cases;
- semantic stopword/min-overlap decisions when they affect relevance.

Keep mechanical retrieval:

- BM25/dense/graph/RRF;
- generic tokenization;
- metadata filtering;
- score normalization;
- stable dedupe;
- mechanical rejection evidence.

Acceptance:

- domain semantics arrive through probes;
- retriever remains usable as a low-level search executor;
- existing golden cases do not regress to stale/gated/skipped final states.

## Acceptance Tests For The Rewrite

At the end of this rewrite:

- every non-clarification run traces `UserIntentArtifact`;
- every retrieval run traces `RetrievalInput`;
- complex concepts produce multiple measures in intent;
- retrieval probes are metadata-oriented and measure-centric;
- FedStat, World Bank, and CKAN receive appropriate probes unless source scope
  restricts them;
- years/geographies are used as constraints/coverage targets, not stuffed into
  every RAG query;
- Source Scouts preserve candidate probe evidence;
- Coverage Inventory receives `UserIntentArtifact + SourceCandidatePool`;
- `Research Designer` is absent from the pre-retrieval path;
- no fixed top-k is treated as correctness;
- all 20 golden cases still resolve only to `passed`, `needs_clarification`, or
  `not_found`.
