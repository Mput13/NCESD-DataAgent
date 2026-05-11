# Retrieval Comparison

This artifact compares the retrieval stack over the prepared index. Dense retrieval is not optional: when credentials or vectors are unavailable, the row records the skipped evidence explicitly as a credential-aware fallback while preserving the Qdrant collection contract.

| Path | Implementation | Status | Evidence |
|---|---|---|---|
| lexical BM25/FTS | Local BM25/FTS approximation over source-card embedding_text with RU/EN keyword evidence | ready | `retrieval-eval.csv` records `retrieval_mode`, `evidence_keywords`, and `relevance_score` |
| Qdrant dense collection | Prepared index manifest `.planning/phases/01-data-architecture-research/embedding-index-manifest.json` with Qdrant collection `phase1_source_cards` | gated_skip | `dense_status`, `index_manifest_status`, and `qdrant_collection` stay present on every eval row |
| rerank | bge-reranker-v2-m3-compatible interface | fallback_keyword_overlap unless endpoint is configured | `rerank_status` records the bge-compatible path or deterministic fallback |
| local-vs-remote Qdrant config | `QDRANT_MODE=local`, path `.local/qdrant`, URL `` | configured | Retrieval code reads the same prepared index manifest for local or server Qdrant |
| skipped evidence | Missing credentials/index artifacts are represented as gated rows, not silent drops | credential-aware fallback | `missing_env_vars`, `dense_status`, and rejection reasons explain what did not run |

## Evaluation Snapshot

- Evaluated rows: `20`
- Prepared index status: `gated_skip`
- Qdrant collection: `phase1_source_cards`
- Dense status: `gated_skip`

## Rejection Handling

Weak candidates are not hidden. The CSV records `rejection_reasons`, `source_family_match`, and top-candidate provenance so later UI trace work can expose selected and rejected source cards.
