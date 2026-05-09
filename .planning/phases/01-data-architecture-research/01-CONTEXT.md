# Phase 1: Data Architecture Implementation - Context

**Gathered:** 2026-05-09
**Status:** Planned, ready for execution

<domain>
## Phase Boundary

Phase 1 is the only active phase in the current milestone. It delivers an implementation-oriented architecture package for DataAgent: requirements map, test cases, deterministic source inventory, a durable prepared-data and embedding-index product, source/retrieval/extraction code slices, model/orchestration validation, Streamlit trace/UI contract, and a final implementation decision package.

The historical slug `01-data-architecture-research` remains canonical for continuity, but `research` does not mean prose-only work. Phase 1 may produce code, scripts, tests, and UI contracts. What it must not do is silently treat unverified spikes as complete: every implementation slice needs plan-bound verification and a `01-xx-SUMMARY.md`.

The phase is anchored in `.planning/ARCHITECTURE_STACK.md`. That document is treated as the target stack, not merely a loose research note.

Phase 1 may implement a narrow vertical slice first, but it must be architecturally scalable toward the full `.planning/ARCHITECTURE_STACK.md` vision. The implementation should avoid one-off demo shortcuts that would block later expansion into real source adapters, multiple retrieval providers, richer LangGraph orchestration, deterministic tool libraries, trace replay, and a fuller Streamlit UI.

The prepared source-card corpus and embedding/search index are Phase 1 deliverables, not disposable research output. By the end of Phase 1 these data artifacts should be ready for demo use; reprocessing or re-embedding all sources in a later phase should happen only for an explicit blocker, schema migration, or corrupted/outdated artifact. Because embedding may be long-running, Phase 1 planning should start the embedding/index build as soon as the source-card corpus and provider contract are ready, then prepare orchestration, extraction, UI, and demo integration while that job runs.

</domain>

<decisions>
## Implementation Decisions

### Architecture Stack Status
- **D-01:** Treat `.planning/ARCHITECTURE_STACK.md` as the target architecture for Phase 1 research and planning.
- **D-02:** Phase 1 should implement and validate risks inside that stack, not compare against a radically simpler architecture unless a blocker is discovered.
- **D-02A:** The current milestone has no active numbered follow-up phases. Future phases require an explicit roadmap change after Phase 1 verification.
- **D-02B:** Execute Phase 1 single-track. Do not recreate a Core/Data/UI owner split.
- **D-02C:** Phase 1 may ship a narrow working slice, but it must preserve extension seams for the full architecture: source adapters, retrieval providers, typed workflow artifacts, graph nodes, deterministic tools, trace events, and UI view models.
- **D-02D:** Every shortcut must be documented as either accepted MVP simplification, deferred full-stack capability, or rejected option in the final decision package.

### Source Scope
- **D-03:** FedStat, World Bank, and CKAN are all in scope from the start.
- **D-04:** CKAN is a first-class source path for discovery and data access, not just a bonus freshness check.
- **D-05:** Local dumps remain important for speed and reproducibility, but Phase 1 must research how live CKAN package/resource discovery integrates into the same source-bound workflow.

### Retrieval and Catalog
- **D-06:** Implement/research retrieval fully according to `.planning/ARCHITECTURE_STACK.md`: lexical BM25/FTS plus dense embeddings and reranking where feasible.
- **D-07:** Metadata indexing should use compact source cards and evidence bundles rather than loading raw CKAN/API/table responses into LLM context.
- **D-08:** Retrieval must support exact code/title matches, Russian and English lexical search, semantic matches, proxy candidates, methodology matches, and rejection reasons.
- **D-08A:** Phase 1 must define a stable embedding document/chunk format before dense retrieval implementation: source id/card id, chunk id, source family, language, content hash, metadata version, provenance, coverage, units, dimensions, source URL/resource URL, and the exact text fields sent to the embedding model.
- **D-08B:** The primary embedding target is Yandex AI Studio embeddings with document/query split: `YANDEX_EMBEDDING_DOC_MODEL=emb://<folder_id>/text-search-doc/latest` for source-card/chunk documents and `YANDEX_EMBEDDING_QUERY_MODEL=emb://<folder_id>/text-search-query/latest` for user queries. The expected vector size is `YANDEX_EMBEDDING_DIMENSIONS=256`. If credentials are absent, execution must record a credential-aware gated skip while preserving the same corpus/index contract.
- **D-08C:** Phase 1 should materialize a local source-card corpus and a Qdrant embedding/search collection as a durable data product. Later phases should consume the manifest and Qdrant collection, not reprocess all sources by default.
- **D-08D:** Embedding inputs are metadata/source-card chunks only. They must not include raw numeric series, generated factual answers, or unsupported numeric claims from an LLM.
- **D-08E:** Long-running embedding/indexing work should run as early as possible after corpus readiness; independent orchestration, UI, extraction, and demo work should continue in parallel while it runs.
- **D-08F:** Phase 1 source metadata must be materialized into a local SQLite or DuckDB catalog that stores source cards, schemas, coverage hints, embedding chunk ids, and rejection-ready metadata. Flat files may be exported for review, but the agent should query a catalog interface.
- **D-08G:** Phase 1 uses Qdrant as the vector store, not a temporary custom local vector index. For speed and low ops overhead, execution may use Qdrant local persistent mode via `qdrant-client` (`QDRANT_MODE=local`, `QDRANT_PATH=.local/qdrant`) or a server URL if provided, but both paths must use the Qdrant client/collection abstraction. Later production deployment should be a configuration change, not a retrieval rewrite.

### Deterministic Extraction
- **D-09:** Implement/research data extraction fully according to `.planning/ARCHITECTURE_STACK.md`: DuckDB SQL-first with PyArrow/source adapters for normalization and Polars where useful.
- **D-10:** FedStat requires a real normalizer strategy for wide Parquet tables, including first-row headers, dimensions, period columns, units, source URLs, and coverage preview.
- **D-11:** World Bank requires a real adapter strategy for indicator cards, countries/aggregates, coverage by country/period, and canonical long-format output.
- **D-12:** LLMs may choose plans and explain results, but numbers must come only from deterministic tools.

### Orchestration and Agents
- **D-13:** Implement/research the orchestration fully according to `.planning/ARCHITECTURE_STACK.md`: LangGraph hierarchical supervisor with typed artifacts.
- **D-14:** The minimum target graph for research/planning is Lead DataAgent/Supervisor, Intent/Triage, Research Designer, FedStat Scout, World Bank Scout, CKAN Scout, Coverage & Schema, Extraction Planner, deterministic tools, Methodology Critic, Narrator, and Visualization where relevant.
- **D-15:** Simple direct lookups should be able to skip unnecessary agents, but complex research queries should use parallel source scouts and critic loops.
- **D-15A:** Graph contracts must include per-node budgets and tool scopes so the hierarchical multi-agent system stays bounded: direct lookup uses few tool calls, complex/research/no-data routes fan out to scouts and critic only when justified.

### LLM Choice
- **D-16:** Use Qwen 3.6 via Yandex AI Studio as the target model per architecture stack.
- **D-17:** Do not spend Phase 1 primarily on broad model benchmarking. DeepSeek/YandexGPT comparisons can be tested later if needed.
- **D-18:** Yandex AI Studio integration should remain part of the target: OpenAI-compatible API, structured outputs/tool calling, and optional native File Search / Vector Store / MCP Hub where they accelerate the architecture.

### Test Cases and Evaluation
- **D-19:** Phase 1 should prepare the broader 15-20 test-case set from the task, not only a small 5-8 smoke set.
- **D-20:** Test coverage should include simple lookup, comparative query, research query, derived metric, ambiguous query, and no-data query.
- **D-21:** Evaluation must measure not just final answer text, but retrieval quality, coverage preview, source rejection, deterministic extraction, and trace completeness.

### Phase 1 Output Shape
- **D-22:** Phase 1 output should include implementation artifacts, research notes, executable spikes, deterministic verification, and trade-off tables.
- **D-23:** Spikes are evidence for implementation decisions; they are not accepted as complete until the relevant plan's verification commands pass and a summary artifact is written.
- **D-23A:** Prepared data artifacts are first-class phase outputs: source-card corpus, embedding/index manifest, build log, provider/model metadata, artifact paths, and rebuild instructions.
- **D-23B:** Typed workflow artifacts must include `DatasetArtifact`, `VisualizationSpec`, `FinalAnswer`, `MethodologyNote`, `FeedbackArtifact`, and source rejection records in addition to intent, research design, coverage, extraction plan, critique, and trace events.
- **D-23C:** Deterministic tools must expose safe operations for coverage preview, DuckDB queries, dataset artifact export, CSV/Parquet/manifest output, and visualization rendering from `DatasetArtifact`; LLMs choose tool plans, not raw numeric values.

### Success Criterion Priority
- **D-24:** The main implementation criterion is maximum demonstration value from multi-agent trace and UI transparency.
- **D-25:** Reliability remains non-negotiable: every numeric value must be source-bound and reproducible, but among reliable options the preferred path is the one with the strongest visible agent workflow and trace.
- **D-26:** Scalability matters: Phase 1 should leave the codebase easier, not harder, to grow into the full target architecture.

### the agent's Discretion
- The planner may choose exact spike ordering, file/module boundaries, schemas, and test harness structure.
- The planner may choose Qdrant local persistent mode or a configured Qdrant server URL, but must keep the Yandex document/query embedding contract, Qdrant collection contract, and durable manifest requirements intact.
- The planner may choose specific charting/eval libraries within the stack constraints.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Direction
- `.planning/PROJECT.md` — product goal, hard constraints, active requirements, and out-of-scope boundaries.
- `.planning/REQUIREMENTS.md` — v1 requirement IDs and phase mapping.
- `.planning/ROADMAP.md` — Phase 1 goal, deliverables, validation criteria, and phase boundaries.
- `.planning/STATE.md` — current project status, verified local data locations, and known implementation surface.

### Architecture and Data
- `.planning/ARCHITECTURE_STACK.md` — target stack and architecture decisions to follow fully in Phase 1 research/planning.
- `.planning/DATA_REPORT.md` — verified FedStat, World Bank, and CKAN data structure findings.
- `.planning/ARCHITECTURE_RESEARCH.md` — broader alternatives and rationale that led to the target stack.
- `.planning/YANDEX_AI_STUDIO_RESEARCH.md` — Yandex AI Studio capabilities, known smoke-test details, model/API notes, and integration patterns.

### Existing Repository Surface
- `app/llm/yandex_ai_studio.py` — current minimal Yandex AI Studio client wrapper.
- `requirements.txt` — current dependency baseline.
- `docs/PROJECT_WORKFLOW.md` — project workflow notes for GSD usage.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/llm/yandex_ai_studio.py`: minimal OpenAI-compatible chat completions client for Yandex AI Studio; can be used as a starting point but likely needs auth/header alignment, structured output support, tool-calling support, and model profile cleanup.

### Established Patterns
- Repository is still a thin scaffold. There are no accepted data adapters, catalog builders, retrieval modules, LangGraph workflow, Streamlit UI, eval harness, or tests yet.
- Durable planning context lives in `.planning/`; generated phase artifacts should stay under `.planning/phases/`.
- Secrets must stay in local environment variables or `.env` and must not be committed.

### Integration Points
- New code should likely grow under the architecture stack's proposed `app/` layout: `workflow/`, `retrieval/`, `data/`, `artifacts/`, `ui/`, `evals/`, and `safety/`.
- Local data is expected outside the repo under `/Users/a/Downloads/dumps/...`; code should reference configurable paths rather than committing dumps.
- CKAN integration should use bounded package/resource search and compressed candidate cards before handing anything to LLM context.

</code_context>

<specifics>
## Specific Ideas

- The user explicitly wants Phase 1 to follow `.planning/ARCHITECTURE_STACK.md` fully for retrieval, deterministic extraction, and LangGraph orchestration.
- The user wants one canonical Phase 1 only. Do not infer later phases from older roadmap history.
- The user rejected the three-person workstream split; execute as a single-track GSD phase.
- The user selected CKAN as an equal first-class source, not a secondary API.
- The user wants the broader 15-20 task test-case set prepared in Phase 1.
- The user expects Phase 1 to finish with prepared data and a ready embedding/search index. Reprocessing later is an exception, not the normal continuation path.
- The user wants long-running embedding to start early; while it runs, agents should prepare the workflow, extraction, UI, and demo integration that can consume the completed index.
- The user selected multi-agent trace and transparent UI wow-effect as the dominant implementation criterion, while preserving source-bound reliability.
- The user accepts that not every full-stack capability will be complete in Phase 1, as long as the result is a working scalable seed that can grow into `.planning/ARCHITECTURE_STACK.md`.

</specifics>

<deferred>
## Deferred Ideas

- Broad DeepSeek/YandexGPT/Qwen benchmarking is deferred; Phase 1 targets Qwen 3.6 per architecture stack and can test alternatives later if needed.
- Full production coverage of every role/tool in `.planning/ARCHITECTURE_STACK.md` may be staged after the initial working slice, but Phase 1 must explicitly document the growth path.

</deferred>

---

*Phase: 01-data-architecture-research*
*Context gathered: 2026-05-09*
