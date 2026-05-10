# Implementation Decision Brief

## Accepted implementation decisions

- Use one canonical Phase 1 track: `.planning/phases/01-data-architecture-research`.
- Use source-card metadata as the prepared corpus and keep raw numeric values out of embedding text.
- Use SQLite as the local source catalog and preserve DuckDB compatibility for extraction.
- Use Qdrant as the vector-store contract. Missing Yandex embedding credentials produce `gated_skip`, not a substitute custom vector index.
- Use hybrid retrieval: lexical/BM25 now, dense Qdrant when vectors are populated, and a bge-reranker-compatible seam.
- Use DuckDB SQL-first deterministic extraction probes for FedStat, World Bank, and CKAN.
- Use workflow-owned `TraceEvent` from `app/artifacts/workflow_artifacts.py` as the trace schema for graph and UI.
- Use Streamlit as a minimal diagnostic surface for state, trace, artifacts, source rejection, index readiness, feedback, and fix requests.

## Rejected options

- Rejected: using LLM memory or visual table reading for numeric values.
- Rejected: replacing Qdrant with an ad hoc local vector index when credentials are absent.
- Rejected: rebuilding or re-embedding the corpus as the default next step after Phase 1.
- Rejected: reviving the deprecated Core/Data/UI owner split for this milestone.
- Rejected: optimizing UI polish before relevance and extraction gates are green.

## Remaining risks

- Qdrant dense retrieval is not populated locally because Yandex embedding credentials are unavailable.
- Data relevance eval still has 12 failed cases and 8 gated cases, so the source-discovery claim is not final.
- Extraction probes prove contracts but do not yet produce source-bound numeric answers for representative golden cases.
- Qwen live structured-output validation is gated by missing Qwen credentials.
- FedStat normalization remains source-specific and should be proven on promoted demo cases before relying on it for final answers.

## Verification still required

- Populate or explicitly demo-gate the Qdrant collection before presenting dense retrieval.
- Rerun retrieval eval after vector population or source-card expansion.
- Promote 2-3 representative golden cases to full deterministic DatasetArtifact output with provenance.
- Run the Streamlit diagnostic shell against the generated `demo-readiness.json`.
- Re-run the full pytest suite after the final demo package changes.

## Rebuild/reprocess policy

Do not reprocess or re-embed all source metadata by default. Rebuild only when manifests are missing, stale, or intentionally invalidated. The canonical recovery path is the `rebuild_command` stored in `.planning/phases/01-data-architecture-research/embedding-index-manifest.json`.

## UI polish is deferred

UI polish is deferred until data relevance and deterministic extraction are correct. The Streamlit work in Phase 1 is a diagnostic interface: it must show state machine, trace, artifacts, index readiness, rejection reasons, and feedback/fix requests clearly enough to support debugging and demo evidence.

## Open questions before final demo

- Which cases become the deterministic extraction demo path?
- Will Yandex embedding credentials be available, or should final demo explicitly present dense retrieval as gated?
- Which source-card gaps are responsible for failed retrieval cases?
- What minimum final answer format is needed once DatasetArtifact rows exist?

