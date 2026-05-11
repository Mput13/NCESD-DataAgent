# Final Recommendation

## Recommendation summary

Proceed with the Phase 1 architecture as the demo foundation, but present the current build as `gated` rather than complete. The strongest accepted path is prepared source-card corpus + SQLite catalog + Qdrant collection contract + lexical retrieval with explicit dense gate + DuckDB SQL-first extraction probes + diagnostic Streamlit trace.

## Ranked options

| Rank | Option | data relevance | Qdrant readiness | deterministic reliability | implementation risk | demo readiness | Evidence |
|---:|---|---|---|---|---|---|---|
| 1 | Prepared source cards, SQLite catalog, Qdrant collection contract, lexical retrieval with dense `gated_skip` | Medium: representative source cards and rejection reasons exist, but many golden rows are missing | Medium: Qdrant contract exists; vectors are credential-gated | High: no numeric claims without DuckDB/tool evidence | Low | Medium: diagnostic demo works as gated evidence | `source-cards-manifest.json`, `source-catalog-manifest.json`, `embedding-index-manifest.json`, `retrieval-eval.csv`, `demo-readiness.json` |
| 2 | Populate the existing Qdrant collection with Yandex embeddings and rerun retrieval eval | High if credentials succeed and retrieval rows cover all 20 cases | High after positive vector count and ready status | High: still source-card metadata only | Medium: external credential/model dependency | High for source discovery demo | `embedding-index-build.md`, `embedding-index-manifest.json`, `retrieval-comparison.md` |
| 3 | Add 2-3 deterministic extraction golden paths over selected FedStat/World Bank/CKAN cases | High for cases with real coverage | Medium: independent of dense gate, but benefits from better retrieval | High: numbers from DuckDB/source adapters only | Medium: source-specific filters and normalization details | High for final demo credibility | `extraction-probes.json`, `extraction-probes.md`, `deterministic_tools.py` |
| 4 | Polish Streamlit visuals before closing data gates | Low: does not improve source choice | Low | Low | Low | Low: better surface, same factual gaps | `trace-ui-demo.md`, `streamlit_app.py` |

## Prepared-data and index path

Accept the prepared-data path. It has the right traceable shape: source cards, catalog, embedding corpus, manifest hashes, and a Qdrant collection contract. The current `gated_skip` is acceptable evidence, not a failure to hide. The next improvement is to populate the existing Qdrant collection, not replace it with a custom local vector index.

## Retrieval path

Keep hybrid retrieval. Lexical/BM25 evidence is enough for a gated diagnostic demo, but not enough for the final source-discovery claim. Dense Qdrant retrieval becomes accepted only when `embedding-index-manifest.json` records `status=ready`, `vector_store=qdrant`, a collection name, matching corpus hash, and positive vector count.

## Extraction path

Keep DuckDB SQL-first deterministic extraction. Extraction probes are sufficient to prove tool contracts, but not sufficient to answer numeric questions. Before final demo, choose 2-3 golden cases and produce DatasetArtifact rows with provenance.

## Orchestration path

Keep the narrow LangGraph-compatible flow and canonical `TraceEvent` ownership. The trace already carries selected sources, rejected sources, coverage/extraction planning, Qdrant status, and final artifacts without duplicating UI schemas.

## Yandex/Qwen path

Keep Qwen/Yandex AI Studio as the target structured-output path. Missing credentials should remain `gated_skip`; DeepSeek remains historical smoke evidence only.

## Diagnostic trace/UI path

Use Streamlit as a diagnostic shell, not a polished product surface. The UI should expose chat input, example prompts, state machine, live trace, artifacts, source rejection details, index readiness, and feedback/fix requests. UI polish is lower priority than data relevance, Qdrant readiness, and deterministic reliability.

## Open questions before final demo

- Which 2-3 golden cases should be promoted to full deterministic extraction first?
- Are Yandex embedding credentials available soon enough to populate `phase1_source_cards` before demo?
- Which failed retrieval rows are best fixed by adding source cards versus improving lexical/dense query expansion?
- Should the first numeric demo favor World Bank long-format data for reliability or FedStat/CKAN for case relevance?

