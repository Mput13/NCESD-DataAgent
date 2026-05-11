# Architecture

**Analysis Date:** 2026-05-11

## Pattern Overview

**Overall:** Source-bound economic data agent with prepared-data infrastructure, graph-aware hybrid retrieval, typed artifacts, LangGraph Phase 2 workflow execution, and deterministic extraction contracts.

**Key Characteristics:**
- Current Phase 2 code has a shared workflow service and LangGraph runtime in `app/workflow/service.py` and `app/workflow/graph.py`; it still needs audit/fix work before jury readiness because eval fixtures and runtime are not cleanly separated.
- All numbers must come from deterministic code in `app/data/deterministic_tools.py` or trusted source adapters; LLM code in `app/llm/yandex_ai_studio.py` is for structured interpretation/planning/narration only.
- Prepared data is first-class: source cards, catalog, embedding corpus, Qdrant manifest, retrieval eval, extraction probes, and readiness reports live under `.planning/phases/01-data-architecture-research/` and `.local/dataagent/phase1/`.
- Qdrant remains the vector-store abstraction, but retrieval is now graph-aware hybrid RAG: BM25 lexical search, dense Qdrant search, deterministic graph-first lookup, graph expansion from dense seeds, and RRF fusion over the prepared source-card corpus.
- `app/retrieval/graph_store.py` builds an in-memory SQLite graph from source-card metadata at runtime. Current Graph RAG does not require a separate graph database or a separate graph embedding collection.
- Streamlit in `app/ui/streamlit_app.py` calls shared workflow service entrypoints, but it is still a fast test/diagnostic surface rather than proof of polished product readiness.

## 2026-05-11 Graph RAG Update

Graph-aware retrieval changed the active retrieval contract:

```text
query
-> LexicalBM25Retriever over embedding_text
-> DenseQdrantRetriever over phase1_source_cards
-> KnowledgeGraphStore.graph_first_card_ids(query)
-> GraphExpander from dense seed card_ids
-> Qdrant payload fetch by graph neighbour card_ids
-> RRF fusion
-> selected/rejected RetrievalCandidate lists
-> HybridRetrievalResult with SubgraphContext
```

Important constraints after this update:

- The graph is deterministic metadata structure, not a source of numeric facts.
- Graph nodes and edges are built from source-card metadata: SourceCard, Indicator, Dataset, Provider, Unit, Geography, Period, Resource, Concept, and Alias.
- `SubgraphContext` is useful retrieval evidence for downstream agents, but final numeric answers still require coverage preview and deterministic extraction.
- Golden-case labels may be used by external eval scripts, but must not be fed into retrieval/workflow runtime as hidden hints.

## Current Workflow vs Target Workflow

**Current Phase 1 Workflow:**

1. Data-preparation scripts build source metadata artifacts:
   - `scripts/build_source_cards.py`
   - `scripts/build_source_catalog.py`
   - `scripts/build_embedding_corpus.py`
   - `scripts/build_embedding_index.py`
2. Retrieval evaluation runs over prepared source-card chunks:
   - `scripts/run_retrieval_spike.py`
   - `app/retrieval/hybrid_retrieval.py`
3. Extraction probes record deterministic contracts, not full extraction:
   - `scripts/run_extraction_probes.py`
   - `app/data/deterministic_tools.py`
4. Narrow graph smoke runs representative golden cases:
   - `app/workflow/run_graph.py`
   - `app/workflow/graph_contract.py`
5. Demo readiness aggregates artifacts and refuses false readiness:
   - `app/demo/run_demo.py`
   - `.planning/phases/01-data-architecture-research/demo-readiness.json`
6. Diagnostic UI displays readiness, trace, selected/rejected sources, and feedback payloads:
   - `app/ui/streamlit_app.py`
   - `app/ui/trace_models.py`

**Current Prepared Data / Retrieval Status:**
- Source-card corpus is present at `.local/dataagent/phase1/source-cards.json` with 36,321 cards recorded in `.planning/phases/01-data-architecture-research/source-cards-manifest.json`.
- Source catalog is present at `.local/dataagent/phase1/source-catalog.sqlite` with manifest `.planning/phases/01-data-architecture-research/source-catalog-manifest.json`.
- Embedding corpus is present at `.local/dataagent/phase1/embedding-corpus.jsonl` with 36,321 chunks recorded in `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json`.
- The current index manifest `.planning/phases/01-data-architecture-research/embedding-index-manifest.json` records `status=ready`, `dense_status=ready`, `qdrant_mode=remote`, `qdrant_url=http://localhost:6333`, and `vector_count=36321`.
- The Phase 2 server manifest `.planning/phases/02-jury-mvp/qdrant-server-manifest.json` records ready server Qdrant evidence for collection `phase1_source_cards`.
- Graph-aware retrieval code and tests exist, but retrieval quality is not final MVP correctness; exact source/indicator selection, coverage, extraction, and final answer semantics still need strict verification.

**Required Phase 2 Workflow:**

1. `User query`
2. `Supervisor`
3. `Intent Analyst`
4. `Research Designer / Direct path`
5. `FedStat Scout / World Bank Scout / CKAN Scout`
6. `Coverage & Schema`
7. `Extraction Planner`
8. `Deterministic Tools`
9. `Methodology Critic`
10. `Visualization`
11. `Narrator`
12. `answer + dataset + script + sources + trace`

**Phase 2 Acceptance Rule:**
- All 20 cases in `.planning/phases/01-data-architecture-research/golden-cases.yaml` must reach `passed`, `needs_clarification`, or `not_found`.
- `gated`, `stale`, `skipped_with_reason`, `no_candidate`, and `final_answer.status=ok` while coverage/extraction is gated are not acceptable final states.
- Streamlit must submit user queries into the same evaluated workflow used by tests/evals, not a separate UI-only path.

## Layers

**Planning and Durable Project Memory:**
- Purpose: Defines roadmap, acceptance boundaries, architecture target, and Phase 2 seed decisions.
- Location: `.planning/`
- Contains: `.planning/STATE.md`, `.planning/ROADMAP.md`, `.planning/ARCHITECTURE_STACK.md`, `.planning/phases/02-jury-mvp/02-SEED-CONTEXT.md`, `.planning/phases/02-jury-mvp/remote-workstream-review.md`.
- Depends on: GSD workflow artifacts and current repo evidence.
- Used by: Phase planning, execution, mapping, and verification.

**Typed Artifact Contracts:**
- Purpose: Owns source-card, embedding, workflow, trace, dataset, feedback, and UI payload schemas.
- Location: `app/artifacts/`
- Contains: `app/artifacts/source_cards.py`, `app/artifacts/workflow_artifacts.py`.
- Depends on: Pydantic, standard Python types.
- Used by: `app/catalog/source_catalog.py`, `app/data/source_card_builders.py`, `app/workflow/run_graph.py`, `app/workflow/graph_contract.py`, `app/ui/trace_models.py`, tests in `tests/test_source_cards_contract.py` and `tests/test_workflow_graph.py`.
- Phase 2 guidance: add or extend artifact schemas here before adding new graph/UI payload shapes elsewhere.

**Prepared Source Builders:**
- Purpose: Build deterministic FedStat, World Bank, and CKAN source candidate cards from local dumps and bounded CKAN API calls.
- Location: `app/data/source_card_builders.py` and `scripts/build_source_cards.py`.
- Contains: `build_fedstat`, `build_world_bank`, `build_ckan`, archive readers, CKAN fetchers, manifest writing.
- Depends on: `app/artifacts/source_cards.py`, local dumps under `/Users/a/Downloads/dumps/`, CKAN package search.
- Used by: source-card corpus artifact `.local/dataagent/phase1/source-cards.json`, tests in `tests/test_source_card_builders.py`.
- Phase 2 guidance: put new source-card builder logic in `app/data/source_card_builders.py`; keep CLI/materialization orchestration in `scripts/build_source_cards.py`.

**Catalog Layer:**
- Purpose: Materializes source cards, coverage hints, embedding chunks, and rejection metadata into SQLite while remaining DuckDB-compatible.
- Location: `app/catalog/source_catalog.py`.
- Contains: `SourceCatalog` and SQLite schema for `source_cards`, `coverage_hints`, `embedding_chunks`, `rejection_metadata`.
- Depends on: `app/artifacts/source_cards.py`, `sqlite3`.
- Used by: `scripts/build_source_catalog.py`, `.local/dataagent/phase1/source-catalog.sqlite`, `scripts/run_extraction_probes.py`.
- Phase 2 guidance: keep catalog schema changes backward-compatible with current manifests or regenerate affected manifests explicitly.

**Retrieval, Qdrant, and Graph RAG Layer:**
- Purpose: Queries source-card metadata through lexical BM25, dense Qdrant, deterministic graph-first lookup, graph expansion, and RRF fusion.
- Location: `app/retrieval/`
- Contains: `app/retrieval/embedding_index.py`, `app/retrieval/hybrid_retrieval.py`, `app/retrieval/graph_store.py`, `app/retrieval/query_understanding.py`.
- Depends on: `qdrant_client`, Yandex embeddings endpoint, prepared embedding corpus manifest.
- Used by: `scripts/build_embedding_index.py`, `scripts/run_retrieval_spike.py`, `scripts/evaluate_retrieval_modes.py`, `app/workflow/nodes/scouts.py`, tests in `tests/test_embedding_index.py`, `tests/test_hybrid_retrieval.py`, and `tests/test_retrieval_mode_comparison.py`.
- Phase 2 guidance: improve ranking/source selection here, but keep graph output as retrieval evidence only. Do not let graph labels, golden matrix expectations, or source ids bypass coverage and deterministic extraction.

**Deterministic Data Tools:**
- Purpose: Execute source-bound coverage, extraction, dataset export, and visualization helper logic.
- Location: `app/data/deterministic_tools.py`.
- Contains: `fedstat_normalize_preview`, `wb_coverage_preview`, `ckan_package_search`, `ckan_package_show`, `run_duckdb_query`, `build_dataset_artifact`, `export_csv_parquet_manifest`, `render_visualization_from_dataset_artifact`.
- Depends on: DuckDB, requests, optional PyArrow, optional Altair/Plotly.
- Used by: `scripts/run_extraction_probes.py`, Phase 2 extraction planner/deterministic tool work.
- Phase 2 guidance: implement real FedStat wide Parquet, World Bank long Parquet, and promoted CKAN resource extraction here or in source-specific modules under `app/data/`; keep LLM-generated free-form code out of the numeric path.

**LLM Integration Layer:**
- Purpose: Provides Yandex AI Studio/Qwen chat and structured output with explicit credential gates.
- Location: `app/llm/yandex_ai_studio.py`.
- Contains: `YandexAIStudioConfig`, `YandexAIStudioClient`, `structured_chat`, `qwen_credential_gate`.
- Depends on: `requests`, `python-dotenv`, Pydantic schemas.
- Used by: tests in `tests/test_yandex_ai_studio.py`; Phase 2 Supervisor/Intent/Designer/Critic/Narrator should call this layer for structured artifacts.
- Phase 2 guidance: keep the verified endpoint `https://llm.api.cloud.yandex.net/v1` and `Api-Key` auth behavior.

**Workflow Layer:**
- Purpose: Provides the shared Phase 2 workflow service, LangGraph routing, node implementations, and legacy smoke CLI.
- Location: `app/workflow/`
- Contains: `app/workflow/service.py`, `app/workflow/graph.py`, `app/workflow/state.py`, `app/workflow/nodes/*`, `app/workflow/run_graph.py`, and legacy `app/workflow/graph_contract.py`.
- Depends on: typed workflow artifacts, graph-aware hybrid retrieval, deterministic adapters, Yandex/Qwen client, LangGraph.
- Used by: Streamlit, web/CLI workflow entrypoints, Phase 2 acceptance runner, tests in `tests/test_phase2_workflow_service.py`, `tests/test_phase2_workflow_nodes.py`, and `tests/test_workflow_graph.py`.
- Phase 2 guidance: keep one shared workflow entrypoint for UI/eval/CLI, but remove eval fixture leakage (`case_id` / `golden-coverage-matrix` hints) from runtime before claiming product correctness.

**Evaluation Layer:**
- Purpose: Scores retrieval, extraction, Qdrant readiness, trace completeness, and unsupported numeric claim evidence against golden cases.
- Location: `app/evals/run_eval.py` and `scripts/run_retrieval_spike.py`.
- Contains: `run_evaluation`, per-case scoring, retrieval CSV generation.
- Depends on: `.planning/phases/01-data-architecture-research/golden-cases.yaml`, retrieval CSV, extraction probes, index manifest.
- Used by: `tests/test_eval_runner.py`, `.planning/phases/01-data-architecture-research/data-relevance-eval.json`.
- Phase 2 guidance: extend this layer to score actual terminal outcomes (`passed`, `needs_clarification`, `not_found`) across all 20 cases.

**Demo Readiness Layer:**
- Purpose: Aggregates prepared artifacts and reports whether the demo path is ready, gated, stale, or blocked.
- Location: `app/demo/run_demo.py`.
- Contains: `DemoInputs`, `assess_demo_readiness`, manifest consistency checks, trace view model creation.
- Depends on: source-card/catalog/corpus/index manifests, retrieval eval, extraction probes, data relevance eval, UI trace models.
- Used by: `app/ui/streamlit_app.py`, `tests/test_demo_readiness.py`, `.planning/phases/01-data-architecture-research/demo-readiness.json`.
- Phase 2 guidance: keep readiness strict; `ready` must mean real workflow readiness, not diagnostic artifact presence.

**UI Layer:**
- Purpose: Provides diagnostic Streamlit surface over readiness and trace data.
- Location: `app/ui/`
- Contains: `app/ui/streamlit_app.py`, `app/ui/trace_models.py`.
- Depends on: `app/demo/run_demo.py`, `app/artifacts/workflow_artifacts.py`, Streamlit.
- Used by: local command `python3 -m streamlit run app/ui/streamlit_app.py`.
- Phase 2 guidance: route `st.chat_input` submissions through the real workflow entrypoint; keep state transitions, selected/rejected sources, coverage, extraction plan, dataset/script, visualization, final answer, and feedback visible.

## Data Flow

**Prepared Data Build Flow:**

1. `scripts/build_source_cards.py` reads local FedStat and World Bank dumps and bounded CKAN API responses.
2. `app/data/source_card_builders.py` emits `SourceCandidateCard` records from `app/artifacts/source_cards.py`.
3. `.local/dataagent/phase1/source-cards.json` stores the full card payload.
4. `.planning/phases/01-data-architecture-research/source-cards-manifest.json` records card count, chunk count, hashes, source families, and local artifact paths.
5. `scripts/build_source_catalog.py` writes `.local/dataagent/phase1/source-catalog.sqlite`.
6. `scripts/build_embedding_corpus.py` writes `.local/dataagent/phase1/embedding-corpus.jsonl`.
7. `scripts/build_embedding_index.py` writes `.planning/phases/01-data-architecture-research/embedding-index-manifest.json` and `.planning/phases/01-data-architecture-research/embedding-index-build.md`.

**Graph-Aware Retrieval Flow:**

1. `scripts/run_retrieval_spike.py` reads `.planning/phases/01-data-architecture-research/golden-cases.yaml`.
2. `app/retrieval/hybrid_retrieval.py` loads documents from `corpus_artifact_path` in `.planning/phases/01-data-architecture-research/embedding-index-manifest.json`.
3. `LexicalBM25Retriever` ranks source-card embedding text.
4. `DenseQdrantRetriever` embeds the query and queries Qdrant when index and credentials are ready.
5. `KnowledgeGraphStore` builds an in-memory graph from the same source-card documents.
6. `graph_first_card_ids(query)` returns cards linked to parsed concepts, geographies, years, and source families.
7. `GraphExpander` expands from dense seed cards through graph neighbours and fetches neighbour payloads from Qdrant by `card_id`.
8. `_rrf_fuse` combines lexical, dense, graph-first, and graph-neighbour candidates.
9. `_split_rejections` records source preference mismatch, no-evidence, and contextual/direct-indicator rejection reasons.
10. `scripts/evaluate_retrieval_modes.py` can compare `dense_only`, `lexical_only`, `graph_first`, `dense_plus_lexical`, and `hybrid_graph`.

**Current Graph Smoke Flow:**

1. `app/workflow/run_graph.py` loads one golden case from `.planning/phases/01-data-architecture-research/golden-cases.yaml`.
2. `_intent_from_case` creates `IntentFrame`.
3. `route_from_category` maps category to `Direct lookup`, `Ambiguous lookup`, `Comparative query`, `Research query`, or `No-data check`.
4. `_run_retrieval` calls `HybridRetriever` and writes selected/rejected source evidence into `EvidenceBundleArtifact`.
5. `_plan_coverage_and_extraction` creates gated `CoverageReport`, `ExtractionPlan`, `DatasetArtifact`, and `FinalAnswer`.
6. `build_graph().invoke(state)` currently appends a checkpoint trace via `Phase1Graph`.
7. Output JSON contains `trace_events`, selected/rejected sources, coverage status, extraction status, dataset artifact, and final answer.

**Phase 2 Product Flow:**

1. `app/ui/streamlit_app.py` accepts a user query and calls the same workflow entrypoint used by evals.
2. Supervisor and Intent Analyst produce `IntentFrame` from Qwen or deterministic fallback with explicit gate.
3. Research Designer creates `ResearchDesignArtifact` for non-trivial cases.
4. Source scouts call retrieval/catalog/CKAN tools and emit selected/rejected source artifacts.
5. Coverage & Schema validates periods, geography, units, frequency, missing values, and source-specific risks.
6. Extraction Planner selects safe operations and DuckDB SQL/Python templates.
7. Deterministic Tools create `DatasetArtifact` and export dataset/script artifacts.
8. Methodology Critic blocks, repairs, asks clarification, or confirms source-bound output.
9. Visualization is generated from `DatasetArtifact`, not LLM text.
10. Narrator emits source-bound final answer.
11. Evals score all 20 golden cases with no unacceptable final states.

**State Management:**
- Current Phase 2 workflow state is `Phase2State` in `app/workflow/state.py`.
- Legacy smoke/test workflow state is `GraphState` in `app/workflow/graph_contract.py`.
- Canonical trace state is `TraceEvent` in `app/artifacts/workflow_artifacts.py`.
- UI state view is `WorkflowTraceViewModel` in `app/ui/trace_models.py`.
- Phase 2 should continue moving toward a single typed workflow state and explicit inter-agent artifacts instead of generic per-node dict payloads.

## Key Abstractions

**SourceCandidateCard:**
- Purpose: Source-bound metadata card passed from scouts to coverage/retrieval.
- Examples: `app/artifacts/source_cards.py`, `.local/dataagent/phase1/source-cards.json`.
- Pattern: Pydantic model with metadata-only embedding text and `card_id` identity.

**EmbeddingDocument / EmbeddingCorpusManifest:**
- Purpose: Stable source-card chunk contract for document embeddings and Qdrant population.
- Examples: `app/artifacts/source_cards.py`, `scripts/build_embedding_corpus.py`, `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json`.
- Pattern: metadata-only JSONL chunks joined back by `card_id` and `chunk_id`.

**SourceCatalog:**
- Purpose: SQLite catalog interface for source cards and embedding chunks.
- Examples: `app/catalog/source_catalog.py`, `.local/dataagent/phase1/source-catalog.sqlite`.
- Pattern: plain SQLite schema that DuckDB can attach or scan later.

**HybridRetriever:**
- Purpose: Unified lexical, dense Qdrant, graph-first, graph-expansion, and RRF retrieval interface.
- Examples: `app/retrieval/hybrid_retrieval.py`, `scripts/run_retrieval_spike.py`, `scripts/evaluate_retrieval_modes.py`.
- Pattern: returns `HybridRetrievalResult` with accepted/rejected `RetrievalCandidate` records, `SubgraphContext`, dense status, graph status, rerank/fusion status, index status, and Qdrant collection.

**KnowledgeGraphStore / SubgraphContext:**
- Purpose: Deterministic metadata graph over source cards for graph-first lookup and neighbour expansion.
- Examples: `app/retrieval/graph_store.py`, `tests/test_hybrid_retrieval.py`.
- Pattern: in-memory SQLite graph built at retrieval startup from source-card documents; no separate graph service is required. `SubgraphContext.as_text()` is compact downstream context, not final evidence for numeric claims.

**GraphState and NodeContract:**
- Purpose: Workflow state, node roles, budgets, and tool scopes.
- Examples: `app/workflow/graph_contract.py`, `tests/test_workflow_graph.py`.
- Pattern: typed state with trace append helper and route budgets; current graph is a narrow invoke-compatible slice.

**Workflow Artifacts:**
- Purpose: Typed artifacts for intent, research design, evidence, coverage, extraction, dataset, critique, visualization, final answer, feedback, and trace.
- Examples: `app/artifacts/workflow_artifacts.py`.
- Pattern: Pydantic artifacts with `extra="forbid"` for stable machine-readable eval/UI contracts.

**DatasetArtifact:**
- Purpose: Dataset, provenance, quality, and export metadata created only from deterministic rows.
- Examples: `app/artifacts/workflow_artifacts.py`, `app/data/deterministic_tools.py`.
- Pattern: `records` + provenance + CSV/Parquet/manifest paths.

**WorkflowTraceViewModel:**
- Purpose: UI-facing trace/readiness payload.
- Examples: `app/ui/trace_models.py`, `app/demo/run_demo.py`.
- Pattern: Pydantic view model consuming canonical `TraceEvent` rather than defining separate trace schemas.

## Entry Points

**Source-Card Build CLI:**
- Location: `scripts/build_source_cards.py`
- Triggers: Manual or planned data-preparation run.
- Responsibilities: Read local FedStat/World Bank dumps, call bounded CKAN search, write `.local/dataagent/phase1/source-cards.json` and `.planning/phases/01-data-architecture-research/source-cards-manifest.json`.

**Source Catalog Build CLI:**
- Location: `scripts/build_source_catalog.py`
- Triggers: After source-card manifest is built.
- Responsibilities: Materialize `.local/dataagent/phase1/source-catalog.sqlite` and `.planning/phases/01-data-architecture-research/source-catalog-manifest.json`.

**Embedding Corpus Build CLI:**
- Location: `scripts/build_embedding_corpus.py`
- Triggers: After source-card manifest is built.
- Responsibilities: Write `.local/dataagent/phase1/embedding-corpus.jsonl` and `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json`.

**Embedding Index Build CLI:**
- Location: `scripts/build_embedding_index.py`
- Triggers: After embedding corpus exists and optionally after credentials are configured.
- Responsibilities: Build or gate Qdrant collection, write `.planning/phases/01-data-architecture-research/embedding-index-manifest.json`, `.planning/phases/01-data-architecture-research/embedding-index-build.md`, and `.local/dataagent/phase1/embedding-cache.jsonl`.

**Retrieval Eval CLI:**
- Location: `scripts/run_retrieval_spike.py`
- Triggers: After index manifest exists.
- Responsibilities: Evaluate hybrid retrieval over golden cases and write `.planning/phases/01-data-architecture-research/retrieval-eval.csv` and `.planning/phases/01-data-architecture-research/retrieval-comparison.md`.

**Retrieval Mode Comparison CLI:**
- Location: `scripts/evaluate_retrieval_modes.py`
- Triggers: After index manifest and corpus exist.
- Responsibilities: Compare `dense_only`, `lexical_only`, `graph_first`, `dense_plus_lexical`, and `hybrid_graph`; write `.planning/phases/02-jury-mvp/retrieval-mode-comparison.csv`, `.json`, and `.md`.

**Extraction Probe CLI:**
- Location: `scripts/run_extraction_probes.py`
- Triggers: After source catalog exists.
- Responsibilities: Record FedStat, World Bank, and CKAN coverage/extraction probe evidence and SQL artifacts under `.planning/phases/01-data-architecture-research/extraction-probe-artifacts/`.

**Workflow Graph CLI:**
- Location: `app/workflow/run_graph.py`
- Triggers: `python3 -m app.workflow.run_graph --goldens ... --case-index ... --index-manifest ... --json-output ...`
- Responsibilities: Run current narrow graph over one golden case and emit machine-readable trace.

**Evaluation CLI:**
- Location: `app/evals/run_eval.py`
- Triggers: `python3 -m app.evals.run_eval ...`
- Responsibilities: Score source relevance, Qdrant/dense status, coverage, extraction, no-data honesty, and trace evidence.

**Demo Readiness CLI:**
- Location: `app/demo/run_demo.py`
- Triggers: `python3 -m app.demo.run_demo ...`
- Responsibilities: Assess source-card/catalog/corpus/index/eval/probe readiness and write readiness JSON.

**Streamlit UI:**
- Location: `app/ui/streamlit_app.py`
- Triggers: `python3 -m streamlit run app/ui/streamlit_app.py`
- Responsibilities: Current diagnostic display of readiness, trace, artifacts, selected/rejected sources, index readiness, feedback, and fix requests.

## Error Handling

**Strategy:** Explicit gated/blocked/stale statuses and machine-readable reasons are preferred over silent fallback or false success.

**Patterns:**
- Missing Qwen credentials raise in `YandexAIStudioConfig.from_env` or return `gated_skip` evidence through `qwen_credential_gate` in `app/llm/yandex_ai_studio.py`.
- Missing embedding credentials return `GatedSkipStatus` in `app/retrieval/embedding_index.py` and preserve Qdrant manifest fields.
- Missing index/corpus artifacts in `app/workflow/run_graph.py` set graph state to `gated` and append trace warnings.
- Demo readiness in `app/demo/run_demo.py` distinguishes `missing`, `stale`, `blocked`, `gated`, `gated_skip`, and `ready`.
- `run_duckdb_query` in `app/data/deterministic_tools.py` only permits `SELECT`/`WITH` SQL and raises on non-read-only statements.
- Phase 2 should map product terminal statuses to `passed`, `needs_clarification`, or `not_found`; infrastructure statuses must not be final MVP outcomes.

## Cross-Cutting Concerns

**Logging:** Current scripts print JSON or concise CLI summaries; long-running embedding writes `.local/dataagent/phase1/embedding-build.stdout.log` and `.local/dataagent/phase1/embedding-monitor.log`.

**Validation:** Pydantic models in `app/artifacts/source_cards.py`, `app/artifacts/workflow_artifacts.py`, and `app/ui/trace_models.py` use strict schemas. Artifact consistency is checked by tests and readiness/eval runners.

**Authentication:** Yandex and Qdrant credentials are loaded from environment via `python-dotenv` in `app/llm/yandex_ai_studio.py` and `app/retrieval/embedding_index.py`. Do not read or commit `.env` contents.

**Source Boundaries:** CKAN access is bounded trusted catalog access through `ckan_package_search` and `ckan_package_show` in `app/data/deterministic_tools.py`; it is not general web search.

**Artifacts:** Durable planning/evidence artifacts live under `.planning/phases/01-data-architecture-research/`; generated local data lives under `.local/dataagent/phase1/` and Qdrant local state under `.local/qdrant*`.

**Remote Workstream Rule:** `origin/workstream-1/core-integration` is reference-only per `.planning/phases/02-jury-mvp/remote-workstream-review.md`; do not merge it wholesale because it deletes Phase 1 artifacts/tests/scripts, rewinds planning state, keeps stubs, and regresses Yandex endpoint/auth.

---

*Architecture analysis: 2026-05-11*
