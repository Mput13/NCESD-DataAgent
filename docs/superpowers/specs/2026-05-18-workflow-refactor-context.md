# Workflow Refactor Context - 2026-05-18

Status: discussion capture and agent handoff artifact.

This document captures the architectural discussion around improving the current
DataAgent workflow. It is not an implementation plan and not a replacement for
`docs/superpowers/specs/2026-05-18-workflow-intent-retrieval-v2.md`.

Read this before changing the workflow from `intent_analysis` through finalization.
The goal is to improve the workflow carefully, layer by layer, while preserving
source-bound guarantees and avoiding broad agent-driven reinterpretation.

## Required Artifacts

Read these artifacts before planning or implementing workflow changes:

- `docs/superpowers/specs/2026-05-18-workflow-intent-retrieval-v2.md` -
  accepted Option 2 target architecture for intent/retrieval/source scouting.
- `docs/superpowers/specs/2026-05-18-intent-retrieval-planner-vision.md` -
  detailed layer vision for Intent Analyst and Retrieval Planner, including
  source-scope rules, probe generation, adaptive retrieval budget, and open ADR
  questions.
- `docs/superpowers/specs/2026-05-19-adr-intent-retrieval-boundary.md` -
  accepted ADR refining the Intent Analyst / Retrieval Planner boundary, removing
  pre-retrieval Research Designer, and defining metadata-aware RAG probes.
- `docs/superpowers/specs/2026-05-19-agent-artifact-drift-negative-example.md` -
  negative example of agent artifact drift where stale deterministic-planner
  language contradicted the accepted LLM Retrieval Planner boundary and caused a
  wrong implementation path.
- `docs/superpowers/specs/2026-05-19-retrieval-planner-implementation-spec.md` -
  implementation source of truth for the LLM Retrieval Planner workflow,
  including the BRICS example, prompt requirements, Source Scouts handoff, and
  acceptance tests.
- This document - broader workflow-refactor context, coverage/source-selection
  discussion, real deterministic coverage demo evidence, and guardrails.

## Goal

Improve the current data-agent workflow so it can reliably answer source-bound
statistical/economic questions over trusted data. The refactor must proceed by
small, explicit slices with durable decisions, real evidence, and narrow tests.

Do not start a broad rewrite. Do not implement every discussed idea at once.

Target direction:

`Intent Analyst -> Retrieval Planner -> Source Scouts -> Coverage Inventory -> Source Selection -> Extraction Mapping/Dry Run -> Deterministic Extraction -> Critic -> Narrator`

The user wants decisions preserved as we discuss layers. The main risk is that a
future agent reads a long discussion, implements a large refactor, and changes the
meaning of the decisions. Avoid that by writing ADRs and implementing one slice at
a time.

## Process Decision

Use an architecture-capture workflow before implementation:

1. Identify the current layer and neighboring contracts.
2. Extract decisions already made.
3. List unresolved architecture questions.
4. Write/update a small ADR before code.
5. Define one thin vertical proof using real source artifacts where possible.
6. Implement only after explicit user approval.
7. Verify with targeted tests and real artifact demos.
8. Update the decision log/spec after the slice.

Recommended ADR shape:

```md
## Decision
## Why
## Not Doing
## Contract
## Interactions
## Acceptance Tests
```

## Problems Identified

### Raw Query Retrieval

Current `run_source_scouts` still passes a raw user query into
`HybridRetriever.search(...)`. Intent analysis extracts a small `IntentFrame`, but
that frame is not the main retrieval input.

This weakens retrieval because the retriever must infer statistical meaning through
handwritten string rules instead of receiving LLM-normalized search probes.

### Retriever Owns Too Much Semantics

The retriever currently contains programmatic semantic logic: token rules,
stopwords, synonym maps, phrase heuristics, source/signal special cases, and
minimum-overlap style filtering.

Decision: retriever should become mechanical: BM25/dense/graph/RRF, metadata
filters, score normalization, stable dedupe, and mechanical rejection evidence.
Domain semantics belong upstream in live Qwen structured output and retrieval
probes.

### Fixed Candidate/Source Counts Are Wrong

The workflow must not use a fixed source count per task. Different tasks require
different evidence:

- direct lookup may need one authoritative source;
- comparison may need one source covering all geographies/periods or several
  sources if coverage is split;
- research may need many sources;
- not_found requires enough checked/rejected evidence to justify the claim;
- ambiguous requests should avoid flooding downstream context.

Important correction: final `candidate_limit` cannot be decided before retrieval.
Intent analysis does not know what is actually in RAG. Retrieval Planner can set
probe priorities, initial page sizes, and stop conditions, but not the final number
of source candidates required for correctness.

Use limits only as execution controls, for example per-probe page size. Final
source count is determined after retrieval/coverage by sufficiency.

### Context Flooding Downstream Agents

Even when scouts retrieve many candidates, Research Designer/Critic/Narrator must
not receive arbitrary top-k source dumps. They should receive a curated evidence
package:

- selected sources with why they are needed;
- supporting sources if useful;
- summarized checked/rejected evidence;
- source coverage and extraction readiness;
- reasons not to include the rest.

The full candidate pool should remain in artifacts/trace, not necessarily in LLM
context.

### Coverage Can Produce False not_found

Current coverage logic sometimes hardcodes geography/period matching too early.
This can turn a reasonable source into zero rows or weak coverage because sources
are inconsistent:

- different geography labels/codes;
- unexpected dimension columns;
- wide vs long layouts;
- periods in columns, rows, labels, quarter/month formats;
- first-row headers;
- source-specific metadata quirks.

False coverage misses can cascade into extraction skips and then `not_found`.
The critic currently maps missing acceptable coverage/dataset to `not_found`,
which can hide retrieval/coverage bugs as user-facing absence of data.

### Coverage Status Is Too Coarse

`CoverageReport.status="ok"` currently can mean "the file opened and inspection
ran", not necessarily "the requested slice exists and can be extracted".

Needed distinction:

- inspection status: source file/API/resource could be inspected;
- schema status: schema was parsed confidently, partially, or remains unknown;
- slice status: requested slice matched, partially matched, no rows, or was not
  attempted;
- extraction readiness: ready, needs mapping, unsupported, unavailable.

### Deterministic Coverage Is Useful but Not an Oracle

Deterministic coverage is valuable because it observes real files and trusted APIs.
It can open parquet files, inspect columns, count rows, detect period columns, find
raw labels, report units/frequency, and test extraction readiness.

It is not reliable as the final semantic judge. It should not say "source is
irrelevant" just because a hardcoded alias or regex did not match.

Decision: deterministic coverage should maximize observability, not certainty.

## Evidence From Real Source Demo

A focused demo was run against real local catalog/parquet artifacts, without the
full workflow and without live LLM:

Runtime catalog:

- `.local/dataagent/phase1/source-catalog.sqlite`
- `.local/dataagent/runtime/source-catalog-manifest.json`
- 36,321 source cards: 6,905 FedStat and 29,416 World Bank.

### World Bank Good Case

Source card:

`world_bank:NY.GDP.MKTP.CD:wb/parquet/NY.GDP.MKTP.CD.parquet`

Real parquet:

`.local/dataagent/phase1/extracted/wb/parquet/NY.GDP.MKTP.CD.parquet`

For Russia 2024, deterministic coverage returned:

```json
{
  "source_id": "NY.GDP.MKTP.CD",
  "status": "ok",
  "available_periods": ["2024"],
  "available_geographies": ["RUS"],
  "unit": "current US$",
  "frequency": "annual",
  "matched_geographies": ["RUS"],
  "matched_periods": ["2024"],
  "requested_slice_rows": 1,
  "extraction_ready": true,
  "row_count": 1
}
```

For BRICS 2015-2024, the same source returned 50 requested slice rows covering
BRA, CHN, IND, RUS, and ZAF across 2015-2024.

This proves deterministic coverage can be useful when source structure is regular.

### FedStat Dirty Wide Table Case

Source card:

`fedstat:60201:fedstatru/data/parquet/60201.parquet`

Title:

`Величина валового внутреннего продукта в рыночных ценах`

Real parquet shape:

```json
{
  "rows": 2,
  "cols": ["column0", "column1", "column2", "column3", "column4"],
  "first_row": ["ОКСМ", "Единица измерения", "Период", 2019.0, 2020.0],
  "second_row": ["\\n643 Российская Федерация", "386 миллиард рублей", "...", 110046.1, 106606.6]
}
```

Coverage recovered logical columns:

```json
{
  "source_id": "60201",
  "status": "ok",
  "available_periods": ["2019", "2020"],
  "available_geographies": ["Российская Федерация"],
  "unit": "* миллиард рублей",
  "physical_columns": ["column0", "column1", "column2", "column3", "column4"],
  "logical_columns": ["ОКСМ", "Единица измерения", "Период", "2019", "2020"],
  "matched_geographies": ["Российская Федерация"],
  "matched_periods": ["2019", "2020"],
  "requested_slice_rows": 1,
  "extraction_ready": true
}
```

This proves deterministic inspection can recover useful structure from imperfect
FedStat parquet.

### World Bank Bad/Weak Candidate Case

Source:

`world_bank:6.0.GDP_current:wb/parquet/6.0.GDP_current.parquet`

It looked semantically relevant from title/metadata but produced zero rows for
Russia, even with no period filter. Coverage returned `status="ok"` with
`row_count=0` and `extraction_ready=false`.

This illustrates why `ok` is too coarse and why coverage must not be treated as a
semantic oracle. It also shows why Source Selection must consider extraction
readiness and not merely source-card relevance.

## Layer Decisions Captured So Far

### Intent Analyst

Detailed artifact:

`docs/superpowers/specs/2026-05-18-intent-retrieval-planner-vision.md`

Role: understand what the user means.

The Intent Analyst should produce `UserIntentArtifact` using live Qwen/Yandex
structured output in runtime mode.

It may use LLM semantic knowledge for:

- statistical term interpretation;
- Russian/English normalization;
- source-domain terminology;
- compound concept decomposition;
- aliases, official terms, likely indicator names/codes;
- expected units/forms/dimensions/frequencies/operations.

It must not:

- select final source cards;
- decide numeric values;
- fake coverage;
- hard-filter sources without explicit user source restriction;
- decide final source/candidate count.

Open implementation decision: replace `IntentFrame` directly with
`UserIntentArtifact`, or introduce a temporary compatibility adapter. Current
recommendation: make `UserIntentArtifact` canonical and keep `IntentFrame` only as
a temporary downstream adapter.

### Retrieval Planner

Detailed artifact:

`docs/superpowers/specs/2026-05-18-intent-retrieval-planner-vision.md`

Refined/accepted boundary:

`docs/superpowers/specs/2026-05-19-adr-intent-retrieval-boundary.md`

Implementation source of truth:

`docs/superpowers/specs/2026-05-19-retrieval-planner-implementation-spec.md`

Role: convert semantic intent into search probes and search strategy.

Retrieval Planner should produce `RetrievalInput` with multiple `SearchProbe`
items. The raw user query remains available for provenance/fallback, but source-card
RAG probes should be metadata-oriented and measure-centric. Years, country lists,
and requested output shape belong in dimension constraints and coverage targets,
not in every probe text.

It may define:

- probe text;
- purpose;
- language;
- measure index;
- priority;
- source-family hints;
- initial page size;
- stop/continue criteria.

It must not define final candidate count before retrieval. It does not know what
RAG contains.

Decision: Retrieval Planner is a separate LLM structured-output node. Deterministic
code may validate the schema, assign stable IDs, preserve explicit constraints,
apply safety bounds, and carry the raw user query as a fallback probe. It must not
generate the primary `RetrievalInput` as a deterministic-only transform over
`UserIntentArtifact`.

### Source Scouts

Role: execute probes against retrievers and source-specific adapters.

Scouts should:

- consume `RetrievalInput`;
- run multiple probes;
- merge/dedupe candidates by stable identity;
- preserve per-probe evidence;
- keep full candidate pool in artifacts;
- pass a candidate pool into coverage inventory.

Scouts should not perform semantic query expansion themselves. If scouts need more
search text, that is a failure upstream in Intent Analyst or Retrieval Planner.

### Research Designer / Analysis Designer Boundary

Accepted update:

Pre-retrieval `Research Designer` is removed. Its previous useful responsibilities
are split as follows:

- compound concept decomposition belongs to Intent Analyst;
- search text/probe generation belongs to Retrieval Planner;
- analysis/methodology planning should be reconsidered later as a post-coverage
  `Analysis Designer`, after real source candidates and coverage inventories are
  known.

### Adaptive Retrieval Budget

There should be no fixed "5 sources per task" rule.

Use an adaptive policy:

- `per_probe_page_size`: execution page size, not correctness limit;
- `max_pages_per_probe`: safety bound;
- `max_context_sources`: context packaging bound, not total candidate bound;
- `continue_until`: coverage complete, enough authoritative evidence, no more
  candidates, budget exhausted, or ambiguity detected;
- `stop_reason`: recorded in trace/artifacts.

### Coverage Inventory

Role: factual inspection of candidate sources.

Coverage should inspect real source artifacts and return observations:

- physical/logical columns;
- dtypes;
- row counts;
- non-null counts;
- candidate period fields;
- candidate geography fields;
- candidate indicator fields;
- sample raw dimension values;
- min/max periods;
- units/frequency;
- source-specific risks;
- technical extraction capability.

Coverage should not make final semantic rejection from hardcoded alias/period
misses. If a mapping is uncertain, return inventory and candidate mappings for
LLM Source Selection.

Recommended new contract direction:

```text
source card -> factual inventory + candidate mappings + extraction capabilities
```

not:

```text
source card + intent filters -> final source suitability verdict
```

### Source Selection

Role: decide which covered/inventoried sources are worth using, whether evidence
is sufficient, and whether retrieval should continue.

Source Selection should run after Coverage Inventory, not before it.

It may use LLM over compact evidence:

- `UserIntentArtifact`;
- `RetrievalInput` probe summary;
- source-card summary;
- deterministic coverage inventory;
- candidate mappings;
- extraction readiness;
- technical risks;
- checked/rejected summary.

LLM can propose:

- source/slice/mapping to try;
- whether a source is primary, supporting, duplicate, or rejected;
- whether to continue retrieval;
- whether to ask the user for clarification;
- why evidence is sufficient/insufficient.

But deterministic extraction must prove selected mappings with real rows before
the final answer can be `passed`.

### Extraction Mapping and Dry Run

Recommended addition: bounded extraction dry-run before full extraction.

For a proposed mapping/slice:

- run a deterministic extraction attempt;
- return up to a few sample rows;
- count rows/non-null values;
- preserve provenance;
- do not treat dry-run as final dataset artifact.

This is the proof step between LLM source selection and full deterministic
extraction.

### Critic

Critic should not turn coverage parser misses into `not_found`.

`not_found` should require logged attempts across relevant trusted sources/probes,
with evidence that sources were checked and failed for defensible reasons.

If coverage/extraction failed because mapping is uncertain or the parser is weak,
the outcome should be repair/continue-search/needs-clarification, not user-facing
`not_found`.

### Narrator

Narrator receives a curated package, not the full candidate pool.

It must not invent numeric values. All numbers must come from dataset artifacts or
trusted deterministic source adapters. It should explain selected sources,
limitations, citations, and not-found evidence without unsupported numeric claims.

## Deterministic Coverage Improvement Ideas

These ideas should become a focused ADR/slice before implementation.

1. Split inspection/schema/slice/extraction statuses.
2. Always return raw inventory, even when slice filtering fails.
3. Avoid filtering too early; inspect full source first, then attempt requested
   slice separately.
4. Produce multiple schema hypotheses for irregular tables.
5. Return candidate mappings instead of hard semantic matches.
6. Add source-family inspectors:
   - World Bank regular long-format inspector;
   - FedStat tolerant wide-table inspector;
   - CKAN package/resource/format inspector.
7. Add fallback inspection when normal parsing fails:
   - first N rows;
   - dtypes/null ratios;
   - year-like values in columns and rows;
   - numeric value columns;
   - dimension-like columns.
8. Add technical scores without final semantic rejection:
   - schema confidence;
   - slice match confidence;
   - data density;
   - metadata completeness;
   - extraction complexity.
9. Produce an LLM-ready compact summary.
10. Add bounded extraction dry-run for proposed mappings.

## Open Architecture Questions

Resolve these through ADRs, not broad implementation:

1. Exact `UserIntentArtifact` migration path:
   direct replacement vs temporary adapter.
2. Exact `GeographyIntent`, `PeriodIntent`, and `DimensionConstraints` schemas.
3. Exact prompt and schema details for the LLM Retrieval Planner node.
4. Exact adaptive retrieval budget contract and stop conditions.
5. Candidate identity and per-probe evidence schema.
6. Coverage Inventory schema and how it coexists with current `CoverageReport`.
7. Source Selection output schema:
   selected primary/supporting/rejected, sufficiency, continue-search decision,
   proposed mappings.
8. Extraction dry-run artifact schema.
9. Revised critic guardrails for `not_found`.
10. Trace/UI artifact shape for intent, probes, inventory, selection, dry-run,
    extraction, and final outcome.

## Recommended Next Slice

Do not start with full intent/retrieval refactor.

Recommended first practical slice: **Coverage Inventory Contract**.

Reason:

- the discussion already has real source evidence;
- current coverage can produce misleading `ok` or false misses;
- improving coverage inventory gives a concrete, testable artifact;
- downstream Source Selection, Extraction, Critic, and Narrator can be designed
  around real observations instead of assumptions.

Thin proof:

1. Keep current workflow intact.
2. Add a new inventory artifact or extended coverage payload beside the current
   `CoverageReport`.
3. Demonstrate on:
   - `world_bank:NY.GDP.MKTP.CD` good case;
   - `fedstat:60201` dirty wide-table case;
   - `world_bank:6.0.GDP_current` weak/zero-row candidate.
4. Show that the artifact separates inspection success from slice match and
   extraction readiness.
5. Add targeted tests using real or fixture parquet shapes.

Only after that should Source Selection be designed against the new inventory
contract.

## Guardrails For Future Agents

- Do not implement directly from this whole document.
- Pick one slice and write a small ADR first.
- Before writing a final spec after discussion, perform an artifact drift check:
  search older specs for stale alternatives and explicitly supersede them.
- Do not keep "compatibility" language that can be implemented as permission to
  violate the accepted architecture.
- Do not remove legacy contracts until adapters/tests prove the replacement.
- Do not lower Phase 2 acceptance below all 20 golden cases.
- Do not add offline/no-response LLM fallback behavior.
- Do not allow LLM to generate final numeric data from memory.
- Do not treat fixed top-k as correctness.
- Do not treat deterministic parser failure as not_found.
- Do not implement Retrieval Planner as deterministic-only probe generation; it
  is a live LLM structured-output layer with deterministic validation and
  post-processing only.
- Preserve traceability: candidates, rejected reasons, coverage inventory,
  mappings, dry-run results, extraction artifacts, and final outcome.
