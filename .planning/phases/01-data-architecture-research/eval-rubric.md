# Phase 1 Evaluation Rubric

This rubric scores every case in `golden-cases.yaml`. It evaluates the assistant's structured artifacts, source evidence, deterministic data path, and trace. Final answer prose is not enough to pass.

## Hard Fail Rules

A case fails immediately if any of the following occur:

1. The response contains an unsupported numeric claim. Per D-12, every numeric value must originate from a deterministic tool, extraction artifact, coverage artifact, or trusted source adapter output with provenance.
2. The assistant fabricates a source, dataset id, resource URL, period, geography, unit, or coverage result.
3. A no-data or invalid request produces a confident answer instead of an attempted-source log and explanation.
4. The LLM reads tabular values from context or prose instead of using deterministic extraction evidence.
5. The trace omits the state where a blocking clarification, no-data result, or extraction failure was decided.
6. Dense retrieval embeds raw numeric data, extracted answer text, or LLM-generated numeric claims instead of source metadata/card chunks.
7. Embedding text or retrieval output contains an unsupported numeric claim.

## Scoring Model

Each case receives up to 16 points. A case passes at 13 points or higher, provided no hard fail rule is triggered.

| Dimension | Points | Deterministic scoring rule |
|---|---:|---|
| Intent classification | 2 | Award 2 when the structured intent category exactly matches `category` or a documented route equivalent from the golden case; 1 when it is compatible but underspecified; 0 when wrong or absent. |
| Research-definition fields | 2 | Award 2 when geography, period, metric/concept, source preference, and task goal are present or explicitly marked missing; 1 when one non-blocking field is absent; 0 when blocking fields are absent without explanation. |
| Clarification trigger correctness | 2 | Award 2 when `needs_clarification` matches behavior and blocking questions name the missing fields; 1 when a clarification is asked but not tied to the blocking field; 0 when the system asks unnecessary blockers or skips required clarification. |
| Candidate-source and embedding evidence | 2 | Award 2 when source cards include source, dataset/indicator id if available, title, unit, period/coverage hint, geography, provenance URL/resource, match mode, why matched, risk flags, and embedding provider/input-format evidence; 1 when at most two non-blocking fields are missing; 0 when candidate evidence is prose-only or embedding behavior is undefined. |
| Coverage-preview evidence | 2 | Award 2 when a CoverageReport or equivalent records actual period/geography/unit availability before extraction; 1 when coverage is checked but lacks one required axis; 0 when extraction proceeds without coverage-preview evidence. |
| Deterministic extraction evidence | 2 | Award 2 when extraction, filtering, aggregation, joins, and derived metrics are represented as code/tool operations with inputs and outputs; 1 when extraction is deterministic but formula/filter details are incomplete; 0 when values are produced without deterministic extraction evidence. |
| Rejection/no-data honesty | 2 | Award 2 when weak candidates, missing coverage, invalid requests, and no-data outcomes are recorded with specific rejection reasons; 1 when rejection is present but generic; 0 when absent or contradicted by final prose. |
| Trace completeness | 2 | Award 2 when the trace includes received query, intent/triage, research design if needed, source scouts, coverage preview, extraction planning, deterministic tool calls, critic/no-data decision, artifacts, and final narration; 1 when one non-critical state is missing; 0 when trace completeness is not auditable. |

## Dimension Details

### Intent Classification

The evaluator reads the structured intent artifact first. If only final answer text exists, the case can earn no more than 1 point for this dimension. Accepted category names are:

- `simple`
- `comparative`
- `research`
- `derived_metric`
- `ambiguous`
- `no_data`

Route names may be more specific, such as `fedstat_direct_lookup` or `world_bank_comparative`, but they must map back to one category from the golden case.

### Research-Definition Fields

The research definition must expose both `known_fields` and missing fields where relevant. Required fields are:

- user goal in plain language;
- geography and geography type when known;
- time frame or latest-available policy;
- metric, indicator, or economic concept;
- source preference if stated;
- granularity/frequency if stated or required;
- specific research questions for research or derived-metric cases.

If a field is unknown but non-blocking, the artifact must record an assumption. If the field is blocking, the clarification dimension decides whether behavior is correct.

### Clarification Trigger Correctness

Use `needs_clarification` from each golden case as the expected boolean. A clarification is correct only when it names the field that prevents reliable data work, for example source/methodology, geography, period, frequency, or concept. The assistant should not ask for a clarification when deterministic source discovery or coverage preview can safely proceed with explicit assumptions.

### Candidate-Source And Embedding Evidence

Candidate cards must be compressed evidence bundles, not raw API dumps. Retrieval evidence must also declare how source cards or chunks are embedded and queried. A complete candidate/evidence bundle contains:

- source: `FedStat`, `World Bank`, or `CKAN`;
- dataset, package, resource, or indicator id when available;
- title or indicator name;
- unit or unit risk flag;
- period/coverage hint or coverage-needed flag;
- geography or geography-risk flag;
- provenance URL or resource URL;
- match mode: `exact`, `lexical`, `semantic`, `proxy`, `ckan_discovery`, or `methodology_match`;
- `why_matched`;
- risk flags and rejection candidates where relevant.
- embedding provider/model family, or a credential-aware fallback when dense retrieval cannot run;
- document/query embedding split when provider-specific modes require it;
- source-card/chunk text format used for embedding;
- proof that dense retrieval indexes source metadata/card chunks, not raw numeric data or generated answers.

CKAN responses must be bounded and compressed. CKAN is scored as a trusted catalog API only; broad web-search behavior does not satisfy this dimension.

### Embedding Provider And Input Format

Dense retrieval readiness is part of retrieval evidence, not a later undefined detail. Every dense retrieval run or dense-retrieval readiness check must record:

- declared embedding provider and model family;
- credential-aware fallback if the intended provider cannot run locally;
- if Yandex AI Studio is used, `text-search-doc` for source-card/chunk documents and `text-search-query` for natural-language user queries;
- exact source-card/chunk text template used for embedding;
- fields included in embedding text: title, source family, dataset/package/resource/indicator ids, methodology or description summary, coverage hints, units, dimensions, geography hints, provenance URLs/resource URLs, availability flags, quality flags, and rejection-risk notes;
- fields excluded from embedding text: raw numeric table rows, extracted numeric answers, generated final-answer text, and any unsupported numeric claim;
- evidence artifact or trace event proving the indexed corpus is source metadata/card chunks.

If the provider is unavailable because credentials are missing, the case can still pass this dimension only when it records the intended provider/model family, the missing credential, the fallback retrieval mode used for local verification, and the command/check to rerun with credentials.

### Coverage-Preview Evidence

Coverage-preview evidence must appear before numeric extraction or final no-data claims. It must record:

- selected candidate source;
- available period or lack of period coverage;
- available geography or lack of geography coverage;
- unit/frequency compatibility;
- non-null availability when a source supports it;
- decision: continue, clarify, use proxy with warning, reject, or no data.

For cases that only ask for available years or source suitability, coverage-preview evidence may be the final artifact.

### Deterministic Extraction Evidence

Values, derived metrics, filters, joins, aggregations, and normalizations must be traceable to code/tool operations. Accepted evidence includes:

- extraction plan with source adapter and filters;
- SQL, pandas, DuckDB, PyArrow, or source-adapter operation record;
- formula inputs for derived metrics;
- output artifact id or manifest;
- source URL and retrieval timestamp;
- quality flags for missing values, aggregation, proxy indicators, or unit conversion.

The narrator may explain results only after these artifacts exist. If no deterministic extraction is needed for the case, this dimension is scored on whether the system explicitly avoids extraction and records why.

### Rejection And No-Data Honesty

Rejected sources must name the candidate and the reason. Valid reasons include:

- wrong geography;
- wrong unit or methodology;
- unavailable period;
- metadata-only result with no usable resource;
- local dump lacks required bilateral/detail dimension;
- source preference conflicts with candidate;
- candidate is a proxy and user has not approved proxy use.

No-data answers must include attempted sources and distinguish these outcomes: not found in catalog, found metadata but no usable data, found data but no requested coverage, invalid request for trusted sources, and credential-gated check not executed.

### Trace Completeness

Trace completeness is assessed from structured trace events or a deterministic log. A complete trace has:

- query received;
- intent/triage decision;
- research design when the route is research, derived, comparative, ambiguous, or no-data;
- source scout events for all attempted source families;
- candidate-source selection and rejection log;
- embedding provider/input-format evidence when dense retrieval is attempted or evaluated;
- coverage-preview evidence;
- extraction plan and deterministic tool calls when extraction occurs;
- methodology critic result or no-data decision;
- artifact ids for dataset, script, manifest, source cards, and final answer when produced;
- user clarification or feedback state when applicable.

The trace must be concise enough for Streamlit display while retaining expandable details for audit.

## Source-Specific Expectations

### FedStat

FedStat cases should record whether a candidate uses local metadata, local Parquet, clean JSONL, or CKAN-discovered resources. Wide Parquet tables require a normalizer strategy before extraction. A case must not pass if the assistant treats technical columns as final data without first handling internal headers, dimensions, periods, units, and coverage.

### World Bank

World Bank cases should distinguish countries from aggregates. The score is reduced when the assistant silently mixes country rows and aggregate groups. Indicator codes, country aliases, non-null period coverage, and source notes must be available in evidence artifacts when relevant.

### CKAN

CKAN-first discovery cases must use bounded `package_search`, `package_show`, or resource-level metadata. Raw CKAN JSON must be summarized into candidate cards before any LLM reasoning. Live CKAN volatility is acceptable only if the trace records query, row limit, timestamp, package/resource id, and reason for selection or rejection.

## Embedding-Specific Expectations

Embedding/indexing checks are required whenever a case uses dense retrieval or evaluates dense retrieval readiness. Passing evidence includes a stable provider declaration, source-card/chunk input format, and an audit trail that the embedded text contains only metadata and provenance. If Yandex AI Studio is the selected provider, document chunks must use `text-search-doc` and user queries must use `text-search-query`; using an ambiguous single mode for both sides is scored as 0 for candidate-source and embedding evidence.

Dense retrieval output may return candidates, scores, metadata, and provenance. It must not return unsupported numeric answers. Numeric fields that are part of source metadata, such as years in coverage hints or dataset ids, are allowed only when they are traceable to source metadata and not presented as extracted facts.

## Skipped Yandex Checks

When Yandex AI Studio credentials are absent, skipped Yandex-dependent checks are recorded as gated checks, not failures of the target architecture. The skip record must include:

- missing credential or environment variable;
- exact check that was skipped;
- expected verification command once credentials are present;
- affected golden cases or rubric dimensions;
- confirmation that Qwen via Yandex AI Studio remains the target model path.
- intended embedding modes, including `text-search-doc` for source-card/chunk documents and `text-search-query` for NL queries when Yandex embeddings are selected.

Skipped Yandex-dependent checks do not allow replacing Qwen with a different target model silently. They only defer credential-required verification while preserving the Qwen target from D-16 through D-18.

## Case Result Template

For each golden case, evaluators should record:

```yaml
case_id: GC-001
hard_fail: false
score:
  intent_classification: 0
  research_definition_fields: 0
  clarification_trigger_correctness: 0
  candidate_source_and_embedding_evidence: 0
  coverage_preview_evidence: 0
  deterministic_extraction_evidence: 0
  rejection_no_data_honesty: 0
  trace_completeness: 0
total: 0
passed: false
evidence_artifacts: []
fail_reasons: []
skipped_gated_checks: []
```

The rubric is deterministic: each point must cite an artifact id, file path, trace event id, or tool output. If evidence cannot be located, the point is not awarded.
