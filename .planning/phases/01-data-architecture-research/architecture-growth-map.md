# Architecture Growth Map

## Implemented now

- Source-card contracts for FedStat, World Bank, and CKAN.
- Prepared source-card corpus and SQLite catalog with coverage hints, embedding chunks, and rejection metadata.
- Embedding corpus manifest and Qdrant collection contract in `.planning/phases/01-data-architecture-research/embedding-index-manifest.json`.
- Hybrid retrieval interface with lexical/BM25, dense Qdrant gate, and bge-reranker-compatible seam.
- Qwen/Yandex AI Studio client with structured-output support and credential-gated live checks.
- Runnable narrow graph contract with canonical workflow artifacts and `TraceEvent`.
- DuckDB SQL-first deterministic extraction probes.
- Data relevance eval and demo readiness runner.
- Diagnostic Streamlit shell over `WorkflowTraceViewModel`, feedback, fix requests, artifacts, and index readiness.

## Extension seams

- Source adapters: add source-family builders without changing the source-card manifest shape.
- Retrieval providers: populate the existing Qdrant collection or add provider configuration without replacing the retrieval interface.
- Reranker: connect a bge-reranker-v2-m3 endpoint behind the current rerank seam.
- Workflow artifacts: expand typed Pydantic artifacts without moving `TraceEvent` ownership out of `workflow_artifacts.py`.
- Trace events: attach richer payloads while preserving canonical fields consumed by Streamlit.
- UI view models: extend `WorkflowTraceViewModel` instead of introducing a second trace schema.
- Qdrant collection contracts: update manifest metadata and vector counts without changing source-card ids or re-embedding all source metadata by default.
- Deterministic tools: add source-specific DuckDB/PyArrow operations behind the existing tool layer.

## Deferred full-stack capabilities

- Full hierarchical LangGraph supervisor with parallel scout execution and checkpoint rewind.
- Complete Qwen structured artifact generation for intent, research design, extraction planning, and narrator steps.
- Dense retrieval over populated Qdrant vectors for all source-card chunks.
- Full extraction and DatasetArtifact output for representative golden cases.
- Production-grade FedStat normalization across wide, first-row-header, and mixed-frequency tables.
- Rich charting/dashboard output beyond diagnostic tables and artifacts.
- User-facing answer polish and broader feedback repair loops.

## Next scaling steps

1. Populate the existing Qdrant collection after credentials are available, then rerun retrieval eval and data relevance eval.
2. Expand source-card coverage for failed golden cases before changing architecture.
3. Promote 2-3 cases to deterministic extraction with DatasetArtifact exports and provenance.
4. Wire the runnable graph to call the demo readiness and extraction outputs for an end-to-end trace.
5. Keep Streamlit diagnostic and evidence-first until retrieval and extraction gates are green.

## Full architecture alignment

The Phase 1 slice grows into `.planning/ARCHITECTURE_STACK.md` by preserving the same boundaries: agents research and critique, deterministic tools extract numbers, Qdrant supports source discovery, and Streamlit exposes trace/artifacts. The next work should scale the current seams rather than rewrite source adapters, retrieval providers, workflow artifacts, trace events, UI view models, Qdrant collection contracts, or re-embed all source metadata by default.

## Open questions before final demo

- Should the first complete extraction case use World Bank for stable long-format proof or FedStat/CKAN for stronger local relevance?
- How many failed retrieval cases can be fixed by source-card expansion before dense vectors are populated?
- Is dense retrieval required live in the demo, or can the demo honestly present Qdrant as gated with a clear rebuild command?
- Which trace payloads are most useful for judges: rejected sources, extraction SQL, coverage evidence, or feedback/fix requests?
