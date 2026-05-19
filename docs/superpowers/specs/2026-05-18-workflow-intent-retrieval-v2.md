# Workflow Intent and Retrieval Spec V2 - 2026-05-18

Status: accepted design spec for the next workflow/retrieval refactor.

This document fixes the target behavior for the workflow layer starting from
`intent_analysis` and ending at source scouting. It describes the intended
architecture, not the current implementation.

## Problem

The current retrieval path is semantically weak:

- `run_source_scouts` passes the raw user query into `HybridRetriever.search(...)`.
- intent analysis extracts a small frame, but does not become the main retrieval input.
- retrieval contains hardcoded programmatic semantics such as token regexes, stopwords,
  synonym maps, phrase heuristics, and minimum overlap checks.
- compound concepts are only partially expanded and only after a separate research design path.

This is the wrong responsibility split. In this product, semantic understanding must be
done by the live LLM with knowledge of the statistical/RAG domain. Deterministic code
must validate, execute, filter, rank, extract, and trace. It must not pretend to
understand the user's statistical intent through handwritten string rules.

## Decision: Option 2

Use a layered contract:

1. `Intent Analyst` - LLM semantic compiler.
2. `Retrieval Planner` - converts the semantic intent into RAG/search probes.
3. `Source Scouts` - execute probes against retrievers and source-specific adapters.
4. `Retriever` - low-level index search and mechanical scoring only.
5. `Coverage/Extraction` - deterministic proof that selected sources answer the request.

The key decision: RAG must receive a structured `RetrievalInput`, not a single raw query
string and not a dumped intent JSON blob.

## Layer Responsibilities

### Intent Analyst

The Intent Analyst answers one question: what does the user mean?

It must produce a structured `UserIntentArtifact` and must be backed by live Qwen/Yandex
structured output in runtime mode.

It is allowed to use LLM semantic knowledge for:

- professional interpretation of statistical terms;
- Russian/English concept normalization;
- source-domain terminology such as Rosstat/FedStat, World Bank, NSED/CKAN;
- compound concept decomposition;
- expected units, forms, dimensions, frequencies, and operations;
- synonym and alias generation relevant to the statistical catalog.

It must not:

- select final source cards;
- call retrievers;
- decide numeric values;
- fake coverage;
- silently invent missing required user constraints;
- hard-filter sources unless the user explicitly requested a source restriction.

### Retrieval Planner

The Retrieval Planner answers one question: how should this intent be searched in our
RAG/source-card corpus?

It converts `UserIntentArtifact` into `RetrievalInput`.

This is a separate LLM structured-output node. The planner may use deterministic
post-processing only for schema validation, stable IDs, safety bounds, preserving explicit
constraints, and carrying the raw user query as a traceable fallback probe. It must not be
implemented as a deterministic-only transformation over the intent artifact, because probe
choice, aliases, official terms, and source-family search wording are part of search
strategy, not mechanical execution.

The planner owns:

- generating multiple search probes per measure;
- choosing probe purpose and priority;
- attaching source-family hints when useful;
- preserving explicit source constraints;
- adding negative constraints from the intent;
- keeping the raw user query as one probe, never as the only probe.

### Source Scouts

Source Scouts answer one question: which concrete source candidates should be evaluated?

They consume `RetrievalInput`, execute probes, merge results, deduplicate by stable source
identity, preserve per-probe evidence, and pass candidates into coverage/extraction.

They must not do semantic query expansion themselves. If a scout needs more search text,
that is a signal that `Intent Analyst` or `Retrieval Planner` did not produce enough
probes.

### Retriever

The retriever answers one question: which indexed cards match this search probe?

It may do mechanical retrieval work:

- BM25/lexical search;
- dense/vector search;
- RRF or other mechanical fusion;
- metadata filtering;
- score normalization;
- stable deduplication;
- traceable rejection reasons.

It must not contain product semantic interpretation:

- no handwritten economic synonym maps;
- no handwritten statistical phrase understanding;
- no "share/inflation/GDP" special cases;
- no stopword/token heuristics that decide semantic relevance;
- no deterministic parser that replaces the LLM's intent artifact.

If lexical preprocessing is technically required by BM25, it must stay generic and
language-agnostic. Domain semantics belong upstream in LLM-produced probes.

## UserIntentArtifact

Target schema:

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

### TaskIntent

```python
class TaskIntent(BaseModel):
    category: Literal[
        "direct_lookup",
        "time_series",
        "comparison",
        "research",
        "derived_metric",
        "metadata_lookup",
        "clarification_needed",
    ]
    user_goal: str
    expected_output: Literal["answer", "table", "chart", "dataset", "methodology", "sources"]
```

### MeasureIntent

One user request may contain one or many measures.

```python
class MeasureIntent(BaseModel):
    user_phrase: str
    canonical_concept: str
    aliases_ru: list[str]
    aliases_en: list[str]
    official_terms_ru: list[str]
    official_terms_en: list[str]
    possible_indicator_names: list[str]
    possible_indicator_codes: list[str]
    measurement_form: Literal[
        "level",
        "index",
        "rate",
        "share",
        "growth",
        "per_capita",
        "absolute_change",
        "unknown",
    ]
    unit_expectation: str | None
    must_not_confuse_with: list[str]
```

For compound concepts, the LLM must decompose the concept into concrete measure intents.
Example: "основные экономические показатели" should become several concrete measures such
as GDP, inflation/CPI, unemployment, industrial production, population, income, depending
on the exact user wording and source domain.

### DimensionIntent

```python
class DimensionIntent(BaseModel):
    geographies: list[GeographyIntent]
    period: PeriodIntent | None
    frequency: Literal["annual", "quarterly", "monthly", "daily", "unknown"]
    breakdowns: list[str]
```

The LLM may normalize geography aliases, but deterministic source adapters must later
validate actual source coverage.

### OperationIntent

```python
class OperationIntent(BaseModel):
    wants_time_series: bool
    wants_comparison: bool
    wants_ranking: bool
    wants_growth_rate: bool
    wants_share: bool
    wants_per_capita: bool
    wants_real_terms: bool
    wants_nominal_terms: bool
    wants_visualization: bool
```

### SourceScope

```python
class SourceScope(BaseModel):
    requested_sources: list[Literal["fedstat", "world_bank", "ckan"]]
    source_constraint: Literal["none", "soft_preference", "hard_only"]
    source_hints: list[str]
```

Rules:

- If the user explicitly says "только Росстат", source constraint is `hard_only`.
- If the user merely mentions a source, it is `soft_preference`.
- If no source is mentioned, `requested_sources=[]` and `source_constraint="none"`.
- The system must search all available trusted source families when there is no explicit
  hard constraint.

### AmbiguityPolicy

```python
class AmbiguityPolicy(BaseModel):
    needs_clarification: bool
    blocking_missing_fields: list[str]
    clarification_questions: list[str]
    non_blocking_assumptions: list[str]
```

Clarification is blocking only when the request cannot be executed into a defensible
source-bound search. A broad but standard statistical concept is not by itself a blocking
ambiguity if geography and period make the task searchable.

## RetrievalInput

This is the object passed from workflow planning into source scouting.

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

### SearchProbe

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

Priority is a planning hint, not an authority signal. Final candidate quality is still
proven downstream by source coverage and deterministic extraction.

## What Goes Into RAG

RAG receives `RetrievalInput.probes`, not just the raw query.

For each probe, Source Scouts call the retriever with:

```python
retriever.search(
    probe.text,
    expected_sources=effective_source_filter,
    limit=probe_limit,
    metadata_filters=metadata_filters_supported_by_source_card_index,
)
```

Source Scouts must not stuff unsupported dimension constraints back into
`probe.text`. Constraints that cannot be applied as source-card metadata filters
remain attached for Coverage Inventory.

The raw user query is kept as a low-priority fallback probe:

```json
{
  "text": "ВВП России за 2000-2013",
  "purpose": "raw_query_fallback",
  "language": "ru",
  "priority": 10
}
```

But it is searched together with stronger LLM-normalized probes:

```json
[
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

For a compound request like "основные экономические показатели России за 2000-2013",
the Retrieval Planner produces probes per decomposed measure:

- GDP / gross domestic product / валовой внутренний продукт;
- CPI / inflation / индекс потребительских цен;
- unemployment rate / уровень безработицы;
- industrial production / промышленное производство;
- population / численность населения;
- income or wages if relevant to the query wording.

The exact list belongs to the LLM artifact and must be visible in trace.

## Source Constraints

Source constraints are explicit user intent, not a guess.

If `source_scope.source_constraint == "hard_only"`, scouts search only the requested source
families.

If `source_scope.source_constraint == "soft_preference"`, scouts boost or search preferred
sources first, but still keep fallback probes for other trusted sources unless the user
explicitly forbids them.

If `source_scope.source_constraint == "none"`, scouts search all trusted sources.

CKAN/NSED is a trusted catalog API in this system. It is not general web search.

## Candidate Merge and Evidence

Scouts must preserve why a candidate exists:

```python
class CandidateProbeEvidence(BaseModel):
    probe_text: str
    probe_purpose: str
    probe_priority: int
    retrieval_mode: str
    score: float
```

When multiple probes find the same card/resource, merge evidence instead of duplicating
the candidate.

Candidate identity should be stable:

- FedStat: source family + indicator/table/resource id;
- World Bank: indicator id;
- CKAN: package id + resource id when available.

## Rejection Rules

Rejections must be traceable and downstream-facing:

- `source_constraint_mismatch`;
- `dimension_coverage_mismatch`;
- `measure_semantics_mismatch`;
- `weak_retrieval_evidence`;
- `duplicate_lower_rank`;
- `adapter_unavailable`;
- `metadata_incomplete`;
- `extraction_not_supported`.

The retriever may report mechanical no-match evidence, but semantic rejection must be
based on the LLM intent artifact plus source-card metadata, not hardcoded token overlap.

## Prompt Requirements

The Intent Analyst prompt must explicitly mention the trusted source universe:

- Rosstat/FedStat/EMISS;
- World Bank;
- NSED/CKAN.

The prompt must instruct Qwen to:

- normalize the user request into statistical concepts;
- output aliases and official terms useful for source-card retrieval;
- decompose compound concepts;
- keep source preferences empty unless the user gave explicit source hints;
- distinguish soft source mentions from hard "only this source" constraints;
- return JSON only under the schema.

The Retrieval Planner prompt must explicitly know that it is writing search probes for
source-card metadata, not for numeric table rows and not for final answer generation.

## Runtime Constraints

- Runtime paths must not depend on `.planning/`.
- Missing live LLM credentials must produce gated/error artifacts, not fake fallback intent.
- LLM may generate search terms, aliases, and likely indicator names, but final source
  selection still requires retriever evidence and deterministic coverage/extraction.
- LLM must not generate final numeric data from memory.
- All selected candidates must retain provenance and per-probe trace.

## Migration Plan

1. Add artifact schemas for `UserIntentArtifact`, `RetrievalInput`, `SearchProbe`, and
   candidate probe evidence.
2. Replace the current `IntentFrame` runtime contract with `UserIntentArtifact` or add an
   adapter only as a temporary compatibility layer.
3. Add a `retrieval_planner` workflow node between intent/research design and source scouts.
4. Change `run_source_scouts` to accept `RetrievalInput`.
5. Remove domain-semantic string heuristics from `HybridRetriever`.
6. Keep BM25/dense/RRF mechanics in retriever, but make all semantic expansion arrive from
   probes.
7. Update golden-case traces to show intent artifact, retrieval input, probes, selected
   candidates, rejected candidates, coverage, extraction, and final outcome.
8. Add regression tests proving the raw query is not the only retrieval input.

## Acceptance Criteria

The refactor is successful when:

- for every non-clarification request, trace contains `UserIntentArtifact` and
  `RetrievalInput`;
- `RetrievalInput.probes` contains at least one normalized semantic probe in addition to
  the original query for statistical indicator requests;
- compound concepts produce multiple measure-level probes;
- explicit source hints become source scope, not hidden string checks;
- retriever code no longer owns economic synonym/phrase semantics;
- source candidates carry per-probe evidence;
- all 20 golden cases still end in valid final outcomes: `passed`, `needs_clarification`,
  or `not_found`.
