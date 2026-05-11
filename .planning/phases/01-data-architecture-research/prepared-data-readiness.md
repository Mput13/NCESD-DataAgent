# Prepared Data Readiness

Plan 05 packages the current Phase 1 demo state without rebuilding the corpus or pretending gated components are ready. The demo path consumes prepared artifacts and reports `ready`, `gated`, or `blocked` with evidence.

## Source-card corpus

- Status: `ready`
- Evidence: `.planning/phases/01-data-architecture-research/source-cards-manifest.json`
- Artifact: `.local/dataagent/phase1/source-cards.json`
- Count: 11 source cards across CKAN, FedStat, and World Bank.
- Policy: source-card metadata is the embedding input; raw numeric observations and generated answers stay out of embedding text.

## Source catalog

- Status: `ready`
- Evidence: `.planning/phases/01-data-architecture-research/source-catalog-manifest.json`
- Artifact: `.local/dataagent/phase1/source-catalog.sqlite`
- Queryability: `passed`
- Tables: source cards, coverage hints, embedding chunks, and rejection metadata.

## Embedding corpus

- Status: `ready`
- Evidence: `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json`
- Artifact: `.local/dataagent/phase1/embedding-corpus.jsonl`
- Chunk count: 11
- Content hash: matches the corpus hash recorded by the prepared index manifest.

## Qdrant collection

- Status: `gated_skip`
- Evidence: `.planning/phases/01-data-architecture-research/embedding-index-manifest.json`
- Vector store: Qdrant
- Collection: `phase1_source_cards`
- Dense vectors: 0
- Gate: Yandex embedding credentials are unavailable.
- Rule: dense retrieval is not reported as ready unless the Qdrant manifest is `ready`, has a collection name, uses `vector_store=qdrant`, matches the embedding corpus hash, and records a positive vector count.

## Retrieval relevance eval

- Status: `gated`
- Evidence: `.planning/phases/01-data-architecture-research/retrieval-eval.csv`
- Current path: lexical/BM25 over prepared source-card text with Qdrant dense status preserved as `gated_skip`.
- Selected/rejected source evidence is present for representative cases, but dense retrieval cannot count as success until vectors are populated.

## Extraction probes

- Status: `gated`
- Evidence: `.planning/phases/01-data-architecture-research/extraction-probes.json`
- FedStat, World Bank, and CKAN probes record DuckDB SQL-first coverage evidence.
- Numeric extraction remains `skipped_with_reason` until a source-specific case chooses filters and runs deterministic extraction.

## Data-relevance eval

- Status: `gated`
- Evidence: `.planning/phases/01-data-architecture-research/data-relevance-eval.json` and `.planning/phases/01-data-architecture-research/data-relevance-eval.md`
- Current aggregate: 20 cases, 8 gated, 12 failed, 0 passed.
- Interpretation: the gate is doing its job. Missing retrieval rows, dense vector gates, and extraction skips are visible instead of converted into success.

## UI trace payloads

- Status: `ready`
- Evidence: `app/demo/run_demo.py`, `app/ui/streamlit_app.py`, and `.planning/phases/01-data-architecture-research/demo-readiness.json`
- Payload: `WorkflowTraceViewModel` with canonical `TraceEvent`, `FeedbackRequest`, `FixRequest`, index readiness, selected sources, rejected sources, and artifacts.

## Deterministic tool outputs

- Status: `ready for probes`, `gated for numeric demo output`
- Evidence: `app/data/deterministic_tools.py`, `scripts/run_extraction_probes.py`, and extraction SQL artifacts under `.planning/phases/01-data-architecture-research/extraction-probe-artifacts/`
- Constraint: no numeric claim can be narrated until deterministic tools produce the rows and provenance.

## Rebuild policy

Do not rebuild or re-embed by default. Rebuild only when a manifest is missing, stale, or explicitly invalidated by source-card contract changes. The recovery command is recorded in `embedding-index-manifest.json` under `rebuild_command`.

## Demo readiness verdict

Overall status: `gated`.

The product loop can demonstrate prepared source-card discovery, rejected-source evidence, Qdrant collection contract status, extraction probe evidence, data relevance gates, and diagnostic Streamlit trace/feedback. It cannot honestly demonstrate dense Qdrant retrieval or source-bound numeric answers until embedding credentials populate vectors and at least 2-3 golden cases run deterministic extraction end to end.

