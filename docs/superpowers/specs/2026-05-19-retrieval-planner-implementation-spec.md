# Retrieval Planner Implementation Spec - 2026-05-19

Status: accepted implementation spec for the Retrieval Planner slice.

This spec is the implementation source of truth for the layer between
`UserIntentArtifact` and Source Scouts. It refines:

- `2026-05-18-workflow-intent-retrieval-v2.md`;
- `2026-05-18-intent-retrieval-planner-vision.md`;
- `2026-05-19-adr-intent-retrieval-boundary.md`.

If another artifact appears to permit deterministic-only Retrieval Planner
behavior, this spec and the ADR supersede that language.

## Layer Boundary

The pre-retrieval workflow is:

```text
Intent Analyst -> Retrieval Planner -> Source Scouts
```

Retrieval Planner consumes only the canonical `UserIntentArtifact` plus runtime
configuration needed to call the live LLM. It produces a transient
`RetrievalInput` for Source Scouts and trace/provenance.

Retrieval Planner is a live Qwen/Yandex structured-output node. It is not a
deterministic transformation over `UserIntentArtifact`.

Deterministic code in this layer is limited to:

- schema validation;
- stable ID assignment when missing;
- preserving explicit constraints from intent;
- validating source-family values against the trusted family list;
- applying safety bounds to budget fields;
- adding a traceable raw-query fallback probe if the LLM omitted it;
- recording trace metadata about LLM-produced vs mechanical fields.

Deterministic code must not generate the primary metadata probes.

## Input Contract

Input is the canonical intent artifact. Shape may evolve, but Retrieval Planner
must receive these semantic facts from intent rather than infer them from the raw
query:

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

Intent owns user meaning. It must not contain RAG probes, retrieval budget,
source-family search strings, guessed indicator codes, final source count,
coverage verdicts, or numeric values.

## Output Contract

Retrieval Planner emits `RetrievalInput`:

```python
class RetrievalInput(BaseModel):
    original_query: str
    intent_id: str | None
    probes: list[SearchProbe]
    dimension_constraints: DimensionConstraints
    source_scope: RetrievalSourceScope
    budget_policy: SourceBudgetPolicy
    negative_constraints: list[str]
    trace_notes: list[str]
```

`SearchProbe` is source-card metadata search text:

```python
class SearchProbe(BaseModel):
    probe_id: str
    text: str
    purpose: Literal[
        "canonical_concept",
        "official_term",
        "alias",
        "source_specific",
        "indicator_code",
        "raw_query_fallback",
        "broad_fallback",
    ]
    measure_id: str | None
    language: Literal["ru", "en", "mixed", "code"]
    priority: int
    source_family_hint: Literal["fedstat", "world_bank", "ckan"] | None
    basis: str | None
    origin: Literal["llm", "mechanical_fallback"]
```

Primary probes must have `origin="llm"`. A raw user query fallback may have
`origin="mechanical_fallback"` and must be low priority.

`DimensionConstraints` carries the requested slice separately from search text:

```python
class DimensionConstraints(BaseModel):
    geographies: list[str]
    geography_group: str | None
    period_start: int | None
    period_end: int | None
    frequency: str | None
```

`SourceBudgetPolicy` is an execution-control hint, not a correctness target:

```python
class SourceBudgetPolicy(BaseModel):
    per_probe_page_size: int
    max_pages_per_probe: int | None
    continue_until: list[str]
```

Retrieval Planner must not choose final source count. Source sufficiency is
decided after retrieval and coverage.

## Runtime Workflow

1. Receive `UserIntentArtifact`.
2. Build an LLM prompt/package containing:
   - the intent artifact;
   - the trusted source families: `fedstat`, `world_bank`, `ckan`;
   - the instruction that probes target source-card metadata, not table rows;
   - the instruction that years, geographies, country groups, analysis verbs, and
     requested output shape stay out of primary `probe.text` by default.
3. Call live/mock Qwen/Yandex structured output for `RetrievalInput`.
4. Validate the returned object against the schema.
5. Apply only deterministic post-processing:
   - clamp budget fields to configured safety bounds;
   - validate `measure_id` against intent measures;
   - validate source-family hints;
   - preserve explicit source constraints;
   - add missing stable `probe_id` values;
   - add low-priority raw-query fallback if absent;
   - mark origins and trace notes.
6. Emit `RetrievalInput` to Source Scouts.

If the LLM call fails or credentials are missing, Retrieval Planner must return a
gated/error artifact such as `llm_unavailable`, `llm_timeout`, or `llm_error`. It
must not synthesize primary probes with deterministic code as a product fallback.

## Prompt Requirements

The Retrieval Planner prompt must instruct the LLM to:

- write probes for source-card metadata, not numeric table rows;
- generate measure-centric probes;
- generate source-family-aware probes for `fedstat`, `world_bank`, and `ckan`
  when `source_scope.mode == "none"`;
- preserve hard source restrictions only when the user explicitly requested
  hard-only source use;
- treat soft source mentions as ordering/boosting hints, not exclusions;
- keep years, geographies, country groups, analysis verbs, and output-shape words
  out of primary probe text by default;
- put years, geographies, groups, and frequency into `dimension_constraints`;
- include official terms and aliases in Russian and English when useful;
- mark source-specific indicator codes as retrieval hypotheses, not facts, unless
  the user explicitly supplied the code;
- return JSON only under the schema.

## Correct Example

User request:

```text
Сравни динамику ВВП, инфляции и безработицы стран БРИКС за 2015-2024.
```

Intent Analyst output, simplified:

```json
{
  "original_query": "Сравни динамику ВВП, инфляции и безработицы стран БРИКС за 2015-2024.",
  "task": {"kind": "compare_dynamics"},
  "measures": [
    {"measure_id": "m_gdp", "concept": "gross domestic product"},
    {"measure_id": "m_inflation", "concept": "inflation / consumer price index"},
    {"measure_id": "m_unemployment", "concept": "unemployment rate"}
  ],
  "dimensions": {
    "geography_group": "BRICS",
    "geographies": ["Brazil", "Russia", "India", "China", "South Africa"],
    "period_start": 2015,
    "period_end": 2024,
    "frequency": "annual"
  },
  "operations": {"items": ["compare", "time_series_dynamics"]},
  "source_scope": {
    "mode": "none",
    "eligible_families": ["world_bank", "fedstat", "ckan"]
  }
}
```

Retrieval Planner calls LLM structured output and receives primary probes like:

```json
{
  "original_query": "Сравни динамику ВВП, инфляции и безработицы стран БРИКС за 2015-2024.",
  "intent_id": "intent_001",
  "dimension_constraints": {
    "geography_group": "BRICS",
    "geographies": ["Brazil", "Russia", "India", "China", "South Africa"],
    "period_start": 2015,
    "period_end": 2024,
    "frequency": "annual"
  },
  "source_scope": {
    "mode": "none",
    "eligible_families": ["world_bank", "fedstat", "ckan"]
  },
  "budget_policy": {
    "per_probe_page_size": 10,
    "max_pages_per_probe": 2,
    "continue_until": ["each_measure_has_candidates", "eligible_families_attempted"]
  },
  "negative_constraints": [],
  "trace_notes": ["Primary probes generated by LLM for source-card metadata."],
  "probes": [
    {
      "probe_id": "p_gdp_wb",
      "measure_id": "m_gdp",
      "text": "gross domestic product GDP",
      "source_family_hint": "world_bank",
      "purpose": "alias",
      "language": "en",
      "priority": 100,
      "basis": "English source-card terminology",
      "origin": "llm"
    },
    {
      "probe_id": "p_gdp_fedstat",
      "measure_id": "m_gdp",
      "text": "валовой внутренний продукт ВВП",
      "source_family_hint": "fedstat",
      "purpose": "official_term",
      "language": "ru",
      "priority": 100,
      "basis": "Russian official statistical terminology",
      "origin": "llm"
    },
    {
      "probe_id": "p_gdp_ckan",
      "measure_id": "m_gdp",
      "text": "валовой внутренний продукт национальные счета",
      "source_family_hint": "ckan",
      "purpose": "source_specific",
      "language": "ru",
      "priority": 95,
      "basis": "NSED CKAN package/resource metadata terminology",
      "origin": "llm"
    },
    {
      "probe_id": "p_inflation_wb",
      "measure_id": "m_inflation",
      "text": "inflation consumer price index CPI",
      "source_family_hint": "world_bank",
      "purpose": "alias",
      "language": "en",
      "priority": 100,
      "basis": "English source-card terminology",
      "origin": "llm"
    },
    {
      "probe_id": "p_inflation_fedstat",
      "measure_id": "m_inflation",
      "text": "индекс потребительских цен инфляция",
      "source_family_hint": "fedstat",
      "purpose": "official_term",
      "language": "ru",
      "priority": 100,
      "basis": "Russian official statistical terminology",
      "origin": "llm"
    },
    {
      "probe_id": "p_inflation_ckan",
      "measure_id": "m_inflation",
      "text": "индекс потребительских цен инфляция",
      "source_family_hint": "ckan",
      "purpose": "source_specific",
      "language": "ru",
      "priority": 95,
      "basis": "NSED CKAN package/resource metadata terminology",
      "origin": "llm"
    },
    {
      "probe_id": "p_unemployment_wb",
      "measure_id": "m_unemployment",
      "text": "unemployment rate labor force",
      "source_family_hint": "world_bank",
      "purpose": "alias",
      "language": "en",
      "priority": 100,
      "basis": "English source-card terminology",
      "origin": "llm"
    },
    {
      "probe_id": "p_unemployment_fedstat",
      "measure_id": "m_unemployment",
      "text": "уровень безработицы рабочая сила",
      "source_family_hint": "fedstat",
      "purpose": "official_term",
      "language": "ru",
      "priority": 100,
      "basis": "Russian official statistical terminology",
      "origin": "llm"
    },
    {
      "probe_id": "p_unemployment_ckan",
      "measure_id": "m_unemployment",
      "text": "безработица рынок труда рабочая сила",
      "source_family_hint": "ckan",
      "purpose": "source_specific",
      "language": "ru",
      "priority": 95,
      "basis": "NSED CKAN package/resource metadata terminology",
      "origin": "llm"
    },
    {
      "probe_id": "p_raw_fallback",
      "measure_id": null,
      "text": "Сравни динамику ВВП, инфляции и безработицы стран БРИКС за 2015-2024.",
      "source_family_hint": null,
      "purpose": "raw_query_fallback",
      "language": "ru",
      "priority": 10,
      "basis": "Mechanical fallback for provenance and recall only",
      "origin": "mechanical_fallback"
    }
  ]
}
```

Primary probe text intentionally does not contain:

- `2015`;
- `2024`;
- `BRICS`;
- the full country list;
- "сравни";
- "динамика".

Those values remain in `dimension_constraints` and are proven later by Coverage
Inventory.

## Source Scouts Handoff

Source Scouts consume `RetrievalInput` exactly as a search execution plan.

They may:

- execute each probe against retrievers and bounded source-family adapters;
- pass `source_family_hint` as a filter or boost;
- pass dimension constraints as metadata filters only when the source-card index
  actually has compatible metadata fields;
- merge/dedupe candidates by stable source identity;
- preserve per-probe candidate evidence;
- pass `UserIntentArtifact + SourceCandidatePool` to Coverage Inventory.

They must not:

- add semantic aliases or handwritten economic synonym maps;
- rewrite probes with years/countries/groups to improve recall;
- decide final source sufficiency;
- decide `not_found`;
- treat raw-query fallback as enough if LLM primary probes are missing.

## Acceptance Tests For This Slice

The implementation is not accepted unless tests prove:

- `retrieval_planner` calls the live/mock Qwen/Yandex structured-output client for
  primary `RetrievalInput` generation;
- missing credentials or LLM failure produce a gated/error artifact, not
  deterministic primary probes;
- for a complex request with three measures and `source_scope.mode == "none"`,
  each measure has LLM-origin probes for `world_bank`, `fedstat`, and `ckan`;
- CKAN is present as a trusted source-family target, not omitted as "web";
- primary probe text excludes years, geography groups, full country lists,
  analysis verbs, and requested output shape by default;
- `dimension_constraints` carries years, geographies, group, and frequency;
- raw user query fallback exists only as low-priority
  `origin="mechanical_fallback"`;
- raw query fallback is never the only probe for statistical requests;
- `RetrievalInput` remains transient and downstream semantic checks continue to
  use `UserIntentArtifact`;
- Retrieval Planner does not choose final candidate count or final source count.

## Implementation Notes

The first implementation slice should add tests before code. At minimum:

- one unit test with a mocked structured-output client proving the call happens;
- one failure-path test proving no deterministic primary probe fallback;
- one BRICS-style complex request test proving family/measure probe coverage and
  dimension separation;
- one trace test proving probe `origin` is visible.

Do not start `HybridRetriever` semantic cleanup until these tests pass and Source
Scouts consume `RetrievalInput`.
