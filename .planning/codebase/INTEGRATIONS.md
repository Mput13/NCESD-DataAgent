# External Integrations

**Analysis Date:** 2026-05-10

## APIs & External Services

**LLM / Yandex AI Studio Chat Completions:**
- Yandex AI Studio Qwen chat-completions client - used for structured output and smoke checks.
  - Implementation: `app/llm/yandex_ai_studio.py`.
  - SDK/Client: raw `requests`; `openai>=1.109.0` is installed but not used by current source code.
  - Endpoint: `https://llm.api.cloud.yandex.net/v1/chat/completions` by default.
  - Auth: `Authorization: Api-Key ...`.
  - Env vars: `YANDEX_AI_STUDIO_QWEN_API_KEY`, `YANDEX_AI_STUDIO_QWEN_MODEL`, fallback `YANDEX_AI_STUDIO_API_KEY`, `YANDEX_API_KEY`, `YANDEX_AI_STUDIO_MODEL`, `YANDEX_QWEN_MODEL`, and optional `YANDEX_AI_STUDIO_BASE_URL`.
  - Status: real client code and tests exist; live use is credential-gated. `tests/test_yandex_ai_studio.py` verifies URL/header behavior and structured-output payload shape.
  - Phase 2 rule: use this current verified host/auth pattern. The remote workstream branch is explicitly rejected as a direct merge because it regresses to a different Yandex host/auth pattern in `.planning/phases/02-jury-mvp/remote-workstream-review.md`.

**Embeddings / Yandex Foundation Models Text Embedding:**
- Yandex text embeddings - used to populate/query Qdrant with source-card embedding chunks.
  - Implementation: `app/retrieval/embedding_index.py` and `scripts/build_embedding_index.py`.
  - SDK/Client: raw `requests`.
  - Endpoint: `https://llm.api.cloud.yandex.net/foundationModels/v1/textEmbedding` by default.
  - Auth: `Authorization: Api-Key ...`.
  - Env vars: `YANDEX_EMBEDDING_API_KEY`, fallback `YANDEX_AI_STUDIO_API_KEY` / `YANDEX_API_KEY`, `YANDEX_FOLDER_ID`, `YANDEX_EMBEDDING_DOC_MODEL`, `YANDEX_EMBEDDING_QUERY_MODEL`, `YANDEX_EMBEDDING_DIMENSIONS`, `YANDEX_EMBEDDING_BASE_URL`, `YANDEX_EMBEDDING_TIMEOUT`, and `YANDEX_EMBEDDING_RETRIES`.
  - Current model contract: document/query split using `emb://<folder_id>/text-search-doc/latest` and `emb://<folder_id>/text-search-query/latest`, 256 dimensions by default.
  - Status: real build path exists, including cache and retry behavior, but current committed manifest `.planning/phases/01-data-architecture-research/embedding-index-manifest.json` is `gated_skip` with `vector_count=0` and stale against the full 36,321-chunk corpus.
  - Phase 2 rule: finish or refresh this index before claiming dense retrieval readiness; do not substitute a custom vector path.

**Trusted CKAN / NSED Repository:**
- NSED CKAN API - trusted catalog source, not general web search.
  - Source-card builder: `scripts/build_source_cards.py` calls `https://repository.nsedc.ru/api/3/action/package_search`.
  - Deterministic tools: `app/data/deterministic_tools.py` implements `ckan_package_search()` and `ckan_package_show()`.
  - Auth: none detected.
  - Query behavior: bounded package/resource search with `rows`, `start`, and resource inspection limits in `scripts/build_source_cards.py`.
  - Current default query: `57319` in `scripts/build_source_cards.py`.
  - Status: real API wrappers exist; committed full source-card/catalog/corpus manifests currently list only `FedStat` and `World Bank` families after the 36,321-card rebuild, while the stale 11-chunk embedding index manifest still lists `ckan`, `fedstat`, and `world_bank`. Treat CKAN coverage as partially prepared and not MVP-ready until Phase 2 rebuild/eval proves it.

**FedStat / Rosstat:**
- Local FedStat dump - trusted local source material for source-card metadata and deterministic extraction planning.
  - Default path: `/Users/a/Downloads/dumps/fedstatru/fedstatru.zip` in `scripts/build_source_cards.py`.
  - Builder: `app/data/source_card_builders.py` via `build_fedstat()`.
  - Extraction probe: `app/data/deterministic_tools.py` via `fedstat_normalize_preview()` and `scripts/run_extraction_probes.py`.
  - Probe SQL: `.planning/phases/01-data-architecture-research/extraction-probe-artifacts/fedstat-wide-preview.sql`.
  - Status: source-card/corpus preparation is real; extraction is still probe/coverage evidence, not full deterministic numeric answer production.

**World Bank:**
- Local World Bank dump - trusted local source material for indicator/country metadata and canonical long-format extraction planning.
  - Default path: `/Users/a/Downloads/dumps/wb/data.zip` in `scripts/build_source_cards.py`.
  - Builder: `app/data/source_card_builders.py` via `build_world_bank()`.
  - Extraction probe: `app/data/deterministic_tools.py` via `wb_coverage_preview()` and `scripts/run_extraction_probes.py`.
  - Probe SQL: `.planning/phases/01-data-architecture-research/extraction-probe-artifacts/world-bank-coverage-preview.sql`.
  - Status: source-card/corpus preparation is real; extraction is still probe/coverage evidence, not full deterministic numeric answer production.

**Reranking Endpoint:**
- bge-reranker-compatible seam - optional future rerank service.
  - Implementation: `app/retrieval/hybrid_retrieval.py` in `BGERerankerCompatible`.
  - Env var: `BGE_RERANKER_URL`.
  - Status: diagnostic seam only; if the env var exists, current code records `bge-reranker-v2-m3_endpoint_configured_not_called_in_phase1` and does not call the endpoint.

## Data Storage

**Databases:**
- SQLite source catalog
  - Path: `.local/dataagent/phase1/source-catalog.sqlite`.
  - Manifest: `.planning/phases/01-data-architecture-research/source-catalog-manifest.json`.
  - Implementation: `app/catalog/source_catalog.py` and `scripts/build_source_catalog.py`.
  - Tables: `source_cards`, `coverage_hints`, `embedding_chunks`, and `rejection_metadata`.
  - Status: current manifest records 36,321 source cards, 36,321 embedding chunks, `queryability_check=passed`, and `duckdb_compatible=true`.
- DuckDB in-memory query engine
  - Implementation: `app/data/deterministic_tools.py` in `run_duckdb_query()`.
  - Scope: read-only `SELECT` / `WITH` queries only.
  - Status: real utility and tests exist; current Phase 1 extraction probes are not full MVP extraction adapters.

**Vector Stores:**
- Qdrant local persistent mode
  - Default path: `.local/qdrant`.
  - Default collection: `phase1_source_cards`.
  - Implementation: `app/retrieval/embedding_index.py`, `scripts/build_embedding_index.py`, and `scripts/build_partial_embedding_snapshot.py`.
  - Manifest: `.planning/phases/01-data-architecture-research/embedding-index-manifest.json`.
  - Status: current committed full-demo readiness is not ready: `.planning/phases/01-data-architecture-research/demo-readiness.current.json` records `qdrant_status=stale`, `dense_retrieval_ready=false`, and `qdrant_vector_count=0`.
- Qdrant remote/server mode
  - Env vars: `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`.
  - Status: supported by configuration code in `app/retrieval/embedding_index.py`; no production/remote deployment evidence detected.

**File Storage:**
- Local filesystem only.
- Generated local artifacts:
  - `.local/dataagent/phase1/source-cards.json`
  - `.local/dataagent/phase1/source-catalog.sqlite`
  - `.local/dataagent/phase1/embedding-corpus.jsonl`
  - `.local/dataagent/phase1/embedding-cache.jsonl`
  - `.local/dataagent/phase1/embedding-build.pid`
  - `.local/dataagent/phase1/embedding-monitor.log`
  - `.local/dataagent/phase1/embedding-build.stdout.log`
  - `.local/qdrant`
  - `.local/qdrant-partial-dev`
  - `.local/qdrant-method-check`
- Committed manifests/evidence:
  - `.planning/phases/01-data-architecture-research/source-cards-manifest.json`
  - `.planning/phases/01-data-architecture-research/source-catalog-manifest.json`
  - `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json`
  - `.planning/phases/01-data-architecture-research/embedding-index-manifest.json`
  - `.planning/phases/01-data-architecture-research/demo-readiness.current.json`
  - `.planning/phases/01-data-architecture-research/retrieval-eval.current.csv`
  - `.planning/phases/01-data-architecture-research/extraction-probes.current.json`
  - `.planning/phases/01-data-architecture-research/data-relevance-eval.current.json`

**Caching:**
- Yandex embedding cache: `.local/dataagent/phase1/embedding-cache.jsonl`, implemented by `EmbeddingCache` in `scripts/build_embedding_index.py`.
- No Redis, Memcached, or external cache service detected.

## Authentication & Identity

**Auth Provider:**
- No user authentication provider detected.
- Streamlit UI in `app/ui/streamlit_app.py` has no login/session auth; it is a local diagnostic UI.

**Service Credentials:**
- Yandex chat and embedding credentials are expected through environment variables loaded from local `.env`.
- Qdrant remote credentials are optional through `QDRANT_API_KEY`.
- CKAN wrappers use public unauthenticated endpoints.
- `.env` and `.env.example` exist; do not read or commit secret contents.

## Monitoring & Observability

**Error Tracking:**
- None detected.

**Logs:**
- Local process/log artifacts:
  - `.local/dataagent/phase1/embedding-monitor.log`
  - `.local/dataagent/phase1/embedding-build.stdout.log`
  - `.planning/phases/01-data-architecture-research/embedding-index-build.md`
- Machine-readable evidence:
  - `TraceEvent` model in `app/artifacts/workflow_artifacts.py`.
  - Diagnostic trace view model in `app/ui/trace_models.py`.
  - Workflow smoke output in `.planning/phases/01-data-architecture-research/run-graph-smoke.current.json`.
  - Demo readiness in `.planning/phases/01-data-architecture-research/demo-readiness.current.json`.
- Status: observability is artifact-based, not centralized logging/APM.

## CI/CD & Deployment

**Hosting:**
- Not detected.
- Streamlit local UI target runs from `app/ui/streamlit_app.py`.

**CI Pipeline:**
- None detected in the repository file scan.
- No `.github/workflows/`, Dockerfile, or deployment config detected.

## Environment Configuration

**Required env vars for live Yandex chat:**
- `YANDEX_AI_STUDIO_QWEN_API_KEY` or `YANDEX_AI_STUDIO_API_KEY` / `YANDEX_API_KEY`
- `YANDEX_AI_STUDIO_QWEN_MODEL` or `YANDEX_AI_STUDIO_MODEL` / `YANDEX_QWEN_MODEL`
- Optional `YANDEX_AI_STUDIO_BASE_URL`

**Required env vars for live Yandex embeddings and dense Qdrant readiness:**
- `YANDEX_EMBEDDING_API_KEY` or `YANDEX_AI_STUDIO_API_KEY` / `YANDEX_API_KEY`
- `YANDEX_EMBEDDING_DOC_MODEL`
- `YANDEX_EMBEDDING_QUERY_MODEL`
- `YANDEX_EMBEDDING_DIMENSIONS`
- Optional `YANDEX_FOLDER_ID`, `YANDEX_EMBEDDING_BASE_URL`, `YANDEX_EMBEDDING_TIMEOUT`, `YANDEX_EMBEDDING_RETRIES`

**Required env vars for Qdrant remote mode:**
- `QDRANT_URL`
- Optional `QDRANT_API_KEY`
- Optional `QDRANT_COLLECTION`

**Local-mode Qdrant defaults:**
- `QDRANT_MODE=local`
- `QDRANT_PATH=.local/qdrant`
- `QDRANT_COLLECTION=phase1_source_cards`

**Secrets location:**
- Local `.env` file only. It exists in the repo root but is ignored by `.gitignore`; contents must not be committed or quoted.

## Webhooks & Callbacks

**Incoming:**
- None detected.

**Outgoing:**
- Yandex chat-completions POST requests from `app/llm/yandex_ai_studio.py`.
- Yandex text embedding POST requests from `app/retrieval/embedding_index.py`.
- CKAN package search/show GET requests from `scripts/build_source_cards.py` and `app/data/deterministic_tools.py`.
- Optional Qdrant remote client calls from `app/retrieval/embedding_index.py` when `QDRANT_URL` is set.

## Real vs Diagnostic vs Not MVP-Ready

**Real and reusable:**
- Typed artifact contracts in `app/artifacts/source_cards.py` and `app/artifacts/workflow_artifacts.py`.
- Source-card builders for FedStat, World Bank, and CKAN in `app/data/source_card_builders.py`.
- Local SQLite catalog builder in `app/catalog/source_catalog.py` and `scripts/build_source_catalog.py`.
- Embedding corpus generator in `scripts/build_embedding_corpus.py`.
- Qdrant/Yandex embedding build path in `app/retrieval/embedding_index.py` and `scripts/build_embedding_index.py`.
- Hybrid lexical/dense retrieval interface in `app/retrieval/hybrid_retrieval.py`.
- Yandex AI Studio Qwen client in `app/llm/yandex_ai_studio.py`.

**Diagnostic/probe-only:**
- Streamlit UI in `app/ui/streamlit_app.py` reads readiness artifacts and does not execute the full user-query workflow.
- Workflow in `app/workflow/run_graph.py` emits source-bound trace artifacts for a narrow Phase 1 path, but coverage/extraction remain gated.
- Extraction probes in `scripts/run_extraction_probes.py` and `.planning/phases/01-data-architecture-research/extraction-probes.current.json` are coverage evidence, not full deterministic answer extraction for all golden cases.
- Reranker seam in `app/retrieval/hybrid_retrieval.py` is configured-not-called for external BGE reranker service.

**Not MVP-ready:**
- Dense retrieval: current `.planning/phases/01-data-architecture-research/demo-readiness.current.json` records `qdrant_status=stale` and `dense_retrieval_ready=false`.
- Full jury eval: `.planning/phases/01-data-architecture-research/data-relevance-eval.current.json` records 20 gated cases.
- Final answer semantics: `.planning/phases/02-jury-mvp/02-SEED-CONTEXT.md` calls out that `final_answer.status=ok` while coverage/extraction are gated is invalid for Phase 2.
- LangGraph runtime: target architecture exists in `.planning/ARCHITECTURE_STACK.md`, but current source code uses an internal graph contract in `app/workflow/graph_contract.py`; no `langgraph` package is present in `requirements.txt`.

---

*Integration audit: 2026-05-10*
