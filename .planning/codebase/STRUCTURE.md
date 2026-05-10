# Codebase Structure

**Analysis Date:** 2026-05-10

## Directory Layout

```text
matmod/
├── AGENTS.md                                      # Repository workflow rules for Codex/GSD
├── requirements.txt                              # Python runtime, data, LLM, retrieval, and UI dependencies
├── app/                                          # Importable DataAgent application package
│   ├── artifacts/                                # Pydantic artifact contracts
│   ├── catalog/                                  # SQLite/DuckDB-compatible source catalog
│   ├── data/                                     # Source-card builders and deterministic data tools
│   ├── demo/                                     # Demo/readiness aggregation entrypoint
│   ├── evals/                                    # Golden-case evaluation runner
│   ├── llm/                                      # Yandex AI Studio/Qwen client
│   ├── retrieval/                                # Qdrant embedding index and hybrid retrieval
│   ├── ui/                                       # Streamlit diagnostic UI and view models
│   └── workflow/                                 # Graph contracts and current graph runner
├── scripts/                                      # CLI builders, probes, eval helpers, and embedding monitor
├── tests/                                        # Pytest suite for contracts, builders, retrieval, graph, UI readiness
├── docs/                                         # Human workflow documentation
├── .planning/                                    # Durable GSD memory, roadmap, phase artifacts, eval evidence
│   ├── codebase/                                 # Codebase maps consumed by GSD planning/execution
│   └── phases/
│       ├── 01-data-architecture-research/        # Accepted Phase 1 infrastructure artifacts and evidence
│       └── 02-jury-mvp/                          # Phase 2 seed context and remote workstream review
└── .local/                                       # Generated local data, embedding cache, and local Qdrant state
    ├── dataagent/phase1/                         # Generated source cards/catalog/corpus/cache logs
    ├── qdrant/                                   # Local Qdrant state
    ├── qdrant-method-check/                      # Local Qdrant method/probe state
    └── qdrant-partial-dev/                       # Partial local Qdrant snapshot state
```

## Directory Purposes

**`app/`:**
- Purpose: Main importable application code.
- Contains: typed artifacts, catalog logic, data tools, retrieval, workflow, evals, demo readiness, UI, and LLM client.
- Key files: `app/artifacts/source_cards.py`, `app/artifacts/workflow_artifacts.py`, `app/workflow/run_graph.py`, `app/ui/streamlit_app.py`.
- Phase 2 guidance: product code belongs here; keep script-only orchestration in `scripts/`.

**`app/artifacts/`:**
- Purpose: Shared Pydantic contracts for source metadata and workflow artifacts.
- Contains: `SourceCandidateCard`, `EmbeddingDocument`, `IntentFrame`, `CoverageReport`, `ExtractionPlan`, `DatasetArtifact`, `FinalAnswer`, `TraceEvent`.
- Key files: `app/artifacts/source_cards.py`, `app/artifacts/workflow_artifacts.py`.
- Phase 2 guidance: define new cross-layer schemas here first, then consume them from workflow/UI/evals.

**`app/catalog/`:**
- Purpose: Local catalog abstraction over source-card metadata.
- Contains: SQLite schema and rebuild/query helpers.
- Key files: `app/catalog/source_catalog.py`.
- Phase 2 guidance: add catalog query helpers here when scouts/coverage need structured source-card lookup.

**`app/data/`:**
- Purpose: Source builders and deterministic numeric/data operations.
- Contains: `app/data/source_card_builders.py`, `app/data/deterministic_tools.py`.
- Key files: `app/data/source_card_builders.py`, `app/data/deterministic_tools.py`.
- Phase 2 guidance: source-specific extraction adapters for FedStat, World Bank, and CKAN should live here, either in `app/data/deterministic_tools.py` for small additions or new focused modules such as `app/data/fedstat_adapter.py` when logic grows.

**`app/retrieval/`:**
- Purpose: Embedding/Qdrant index config, population, lexical search, dense search, rerank seam, and candidate rejection.
- Contains: `app/retrieval/embedding_index.py`, `app/retrieval/hybrid_retrieval.py`.
- Key files: `app/retrieval/embedding_index.py`, `app/retrieval/hybrid_retrieval.py`.
- Phase 2 guidance: retrieval ranking fixes and Qdrant query behavior belong here; do not introduce a separate vector index outside this directory.

**`app/workflow/`:**
- Purpose: Workflow state, route budgets, node contracts, and current graph runner.
- Contains: `app/workflow/graph_contract.py`, `app/workflow/run_graph.py`.
- Key files: `app/workflow/graph_contract.py`, `app/workflow/run_graph.py`.
- Phase 2 guidance: implement the real Supervisor → Intent → Scout → Coverage → Extraction → Critic → Visualization → Narrator graph here. Preserve `TraceEvent` ownership in `app/artifacts/workflow_artifacts.py`.

**`app/evals/`:**
- Purpose: Machine-readable scoring against golden cases and evidence artifacts.
- Contains: `app/evals/run_eval.py`.
- Key files: `app/evals/run_eval.py`.
- Phase 2 guidance: extend this runner to evaluate all 20 cases against real workflow outputs and valid terminal outcomes.

**`app/demo/`:**
- Purpose: Demo readiness aggregation from prepared artifacts.
- Contains: `app/demo/run_demo.py`.
- Key files: `app/demo/run_demo.py`.
- Phase 2 guidance: keep readiness strict and evidence-based; move product execution to `app/workflow/`, not into demo aggregation.

**`app/ui/`:**
- Purpose: Streamlit diagnostic UI and UI-facing trace/readiness models.
- Contains: `app/ui/streamlit_app.py`, `app/ui/trace_models.py`.
- Key files: `app/ui/streamlit_app.py`, `app/ui/trace_models.py`.
- Phase 2 guidance: update `app/ui/streamlit_app.py` so user query submission invokes the real workflow and shows answer, dataset, script, sources, trace, selected/rejected source cards, coverage, extraction plan, visualization, and feedback/fix requests.

**`app/llm/`:**
- Purpose: Yandex AI Studio/Qwen integration.
- Contains: `app/llm/yandex_ai_studio.py`.
- Key files: `app/llm/yandex_ai_studio.py`.
- Phase 2 guidance: call this module from workflow nodes for structured artifacts; keep verified `llm.api.cloud.yandex.net` and `Api-Key` behavior.

**`scripts/`:**
- Purpose: Command-line materialization, evaluation, extraction probes, and embedding monitoring.
- Contains: `scripts/build_source_cards.py`, `scripts/build_source_catalog.py`, `scripts/build_embedding_corpus.py`, `scripts/build_embedding_index.py`, `scripts/build_partial_embedding_snapshot.py`, `scripts/monitor_embedding_build.py`, `scripts/run_extraction_probes.py`, `scripts/run_retrieval_spike.py`.
- Phase 2 guidance: add one-off or repeatable artifact builders here; import reusable logic from `app/`.

**`tests/`:**
- Purpose: Pytest suite for contracts, data builders, retrieval, workflow, eval, demo readiness, and Yandex client behavior.
- Contains: `tests/test_source_cards_contract.py`, `tests/test_source_card_builders.py`, `tests/test_source_catalog_and_corpus.py`, `tests/test_embedding_index.py`, `tests/test_hybrid_retrieval.py`, `tests/test_deterministic_tools_and_trace.py`, `tests/test_workflow_graph.py`, `tests/test_eval_runner.py`, `tests/test_demo_readiness.py`, `tests/test_yandex_ai_studio.py`.
- Phase 2 guidance: place tests next to the relevant behavioral area by naming (`test_workflow_*.py`, `test_*_retrieval.py`, `test_*_extraction.py`, `test_ui_*.py`) in `tests/`.

**`.planning/`:**
- Purpose: Durable project memory, roadmap, architecture research, phase plans, acceptance evidence, and generated GSD codebase maps.
- Contains: `.planning/STATE.md`, `.planning/ROADMAP.md`, `.planning/ARCHITECTURE_STACK.md`, `.planning/phases/01-data-architecture-research/`, `.planning/phases/02-jury-mvp/`, `.planning/codebase/`.
- Phase 2 guidance: record decisions and acceptance evidence here; do not treat `.planning/phases/01-data-architecture-research/` as disposable because Phase 2 depends on its artifacts.

**`.local/`:**
- Purpose: Generated local artifacts and local runtime state that should not be committed.
- Contains: `.local/dataagent/phase1/source-cards.json`, `.local/dataagent/phase1/source-catalog.sqlite`, `.local/dataagent/phase1/embedding-corpus.jsonl`, `.local/dataagent/phase1/embedding-cache.jsonl`, `.local/qdrant/`.
- Phase 2 guidance: large generated data and caches stay here; manifests in `.planning/` reference them.

## Key File Locations

**Entry Points:**
- `scripts/build_source_cards.py`: Build deterministic source candidate cards from FedStat, World Bank, and CKAN.
- `scripts/build_source_catalog.py`: Build the SQLite source catalog.
- `scripts/build_embedding_corpus.py`: Build metadata-only embedding chunks.
- `scripts/build_embedding_index.py`: Build or gate the Qdrant embedding index.
- `scripts/run_retrieval_spike.py`: Run retrieval evaluation and write CSV/markdown artifacts.
- `scripts/run_extraction_probes.py`: Run deterministic coverage/extraction probes and write SQL evidence.
- `app/workflow/run_graph.py`: Run the current narrow graph over a golden case.
- `app/evals/run_eval.py`: Run data relevance/evidence evaluation.
- `app/demo/run_demo.py`: Assess prepared-data demo readiness.
- `app/ui/streamlit_app.py`: Start the current Streamlit diagnostic UI.
- `app/llm/yandex_ai_studio.py`: Run Qwen credential gate or smoke prompt.

**Configuration:**
- `requirements.txt`: Python dependencies for Pydantic, requests, Qdrant, DuckDB/PyArrow, Streamlit, evals, and UI.
- `.planning/config.json`: GSD project configuration.
- `AGENTS.md`: Repository workflow rules.
- `.planning/STATE.md`: Current phase state and decisions.
- `.planning/ROADMAP.md`: Phase 1 infrastructure and Phase 2 jury MVP roadmap.
- `.planning/ARCHITECTURE_STACK.md`: Target architecture.
- `.env`: environment configuration may exist locally; do not read or commit contents.

**Core Logic:**
- `app/artifacts/source_cards.py`: Source-card and embedding contracts.
- `app/artifacts/workflow_artifacts.py`: Workflow, trace, dataset, final answer, and feedback artifacts.
- `app/catalog/source_catalog.py`: SQLite catalog materialization.
- `app/data/source_card_builders.py`: FedStat/World Bank/CKAN source-card builder functions.
- `app/data/deterministic_tools.py`: Deterministic coverage, extraction, dataset export, and visualization helpers.
- `app/retrieval/embedding_index.py`: Yandex embedding config/provider and Qdrant wrapper.
- `app/retrieval/hybrid_retrieval.py`: Lexical + dense + rerank retrieval interface.
- `app/workflow/graph_contract.py`: Node contracts, route budgets, graph state, trace append helper.
- `app/workflow/run_graph.py`: Current graph smoke runner.
- `app/ui/trace_models.py`: UI trace/readiness view models.

**Testing:**
- `tests/test_source_cards_contract.py`: Source-card contract validation.
- `tests/test_source_card_builders.py`: Source builder behavior.
- `tests/test_source_catalog_and_corpus.py`: Catalog and embedding corpus behavior.
- `tests/test_embedding_index.py`: Qdrant/embedding manifest behavior.
- `tests/test_hybrid_retrieval.py`: Hybrid retrieval behavior.
- `tests/test_deterministic_tools_and_trace.py`: Deterministic tools and trace contracts.
- `tests/test_workflow_graph.py`: Graph contracts and graph smoke behavior.
- `tests/test_eval_runner.py`: Eval runner behavior.
- `tests/test_demo_readiness.py`: Demo readiness and Streamlit import behavior.
- `tests/test_yandex_ai_studio.py`: Yandex client and credential gates.

**Phase 1 Artifact Manifests:**
- `.planning/phases/01-data-architecture-research/source-cards-manifest.json`: Source-card payload manifest.
- `.planning/phases/01-data-architecture-research/source-catalog-manifest.json`: SQLite catalog manifest.
- `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json`: Embedding corpus manifest.
- `.planning/phases/01-data-architecture-research/embedding-index-manifest.json`: Qdrant embedding index manifest.
- `.planning/phases/01-data-architecture-research/retrieval-eval.csv`: Retrieval eval rows.
- `.planning/phases/01-data-architecture-research/extraction-probes.json`: Extraction probe evidence.
- `.planning/phases/01-data-architecture-research/data-relevance-eval.json`: Data relevance eval output.
- `.planning/phases/01-data-architecture-research/demo-readiness.json`: Demo readiness output.
- `.planning/phases/01-data-architecture-research/golden-cases.yaml`: 20-case acceptance set.

**Generated Local Artifacts:**
- `.local/dataagent/phase1/source-cards.json`: Full generated source-card payload.
- `.local/dataagent/phase1/source-catalog.sqlite`: SQLite source catalog.
- `.local/dataagent/phase1/embedding-corpus.jsonl`: Metadata-only embedding corpus.
- `.local/dataagent/phase1/embedding-cache.jsonl`: Yandex embedding cache.
- `.local/dataagent/phase1/embedding-build.pid`: Embedding build process marker.
- `.local/dataagent/phase1/embedding-build.stdout.log`: Embedding build stdout log.
- `.local/dataagent/phase1/embedding-monitor.log`: Embedding monitor log.
- `.local/qdrant/`: Local Qdrant collection state.

**Phase 2 Planning Inputs:**
- `.planning/phases/02-jury-mvp/02-SEED-CONTEXT.md`: Phase 2 seed context.
- `.planning/phases/02-jury-mvp/remote-workstream-review.md`: Remote branch review and selective-porting rule.
- `.planning/phases/01-data-architecture-research/phase1-test-acceptance.md`: Phase 1 accepted-as-infrastructure test/gate record.
- `.planning/phases/01-data-architecture-research/phase1-actual-state-verification.md`: Actual runnable surface and current gates.
- `.planning/phases/01-data-architecture-research/architecture-growth-map.md`: Growth map from Phase 1 slice to target architecture.

## Naming Conventions

**Files:**
- Python modules use `snake_case.py`: `app/data/deterministic_tools.py`, `app/workflow/run_graph.py`.
- Tests use `test_*.py`: `tests/test_workflow_graph.py`, `tests/test_demo_readiness.py`.
- Scripts use verb-oriented `snake_case.py`: `scripts/build_source_cards.py`, `scripts/run_extraction_probes.py`.
- Planning documents use uppercase or phase-prefixed markdown: `.planning/ROADMAP.md`, `.planning/phases/01-data-architecture-research/01-05-SUMMARY.md`.
- Phase 1 artifacts use descriptive lowercase names: `.planning/phases/01-data-architecture-research/retrieval-eval.csv`, `.planning/phases/01-data-architecture-research/demo-readiness.json`.

**Directories:**
- Application subpackages are functional nouns: `app/artifacts/`, `app/retrieval/`, `app/workflow/`, `app/ui/`.
- Phase directories use numeric prefix and slug: `.planning/phases/01-data-architecture-research/`, `.planning/phases/02-jury-mvp/`.
- Generated local runtime artifacts live under `.local/dataagent/phase1/`.

**Classes and Models:**
- Pydantic models use PascalCase nouns: `SourceCandidateCard`, `CoverageReport`, `DatasetArtifact`, `WorkflowTraceViewModel`.
- Dataclasses use PascalCase nouns: `EmbeddingIndexConfig`, `RetrievalCandidate`, `RouteBudget`.
- Enums/literals describe domain states: `MatchMode`, `WorkflowStatus`, `RouteName`.

**Functions:**
- Functions use `snake_case` verbs or builders: `build_fedstat`, `run_duckdb_query`, `assess_demo_readiness`, `run_golden_case`.
- Private helpers use leading underscore: `_run_retrieval`, `_plan_coverage_and_extraction`, `_qdrant_status`.

## Where to Add New Code

**New Phase 2 Workflow Node:**
- Primary code: `app/workflow/`
- Shared artifacts: `app/artifacts/workflow_artifacts.py`
- Tests: `tests/test_workflow_graph.py` or a new focused file such as `tests/test_workflow_phase2.py`
- Guidance: keep workflow state centralized in `GraphState` or its Phase 2 replacement; append canonical `TraceEvent` records from `app/artifacts/workflow_artifacts.py`.

**New Source Scout Behavior:**
- Primary code: `app/retrieval/` for source-card search/ranking, `app/catalog/source_catalog.py` for catalog access, `app/data/deterministic_tools.py` for CKAN tool calls.
- Tests: `tests/test_hybrid_retrieval.py` and new scout-focused tests if needed.
- Guidance: return selected and rejected source cards with reasons; do not hide weak candidates.

**New FedStat Extraction Adapter:**
- Primary code: `app/data/`
- Recommended file if substantial: `app/data/fedstat_adapter.py`
- Shared artifact updates: `app/artifacts/workflow_artifacts.py` for extraction/dataset fields.
- Tests: new `tests/test_fedstat_extraction.py` or additions to `tests/test_deterministic_tools_and_trace.py`.
- Artifact outputs: dataset/script/manifests under a planned phase directory in `.planning/phases/02-jury-mvp/` or generated local data under `.local/dataagent/phase2/`.

**New World Bank Extraction Adapter:**
- Primary code: `app/data/`
- Recommended file if substantial: `app/data/world_bank_adapter.py`
- Tests: new `tests/test_world_bank_extraction.py`.
- Guidance: preserve canonical long-format assumptions from `app/data/deterministic_tools.py`.

**New CKAN Resource Promotion/Extraction:**
- Primary code: `app/data/`
- Recommended file if substantial: `app/data/ckan_adapter.py`
- Tests: new `tests/test_ckan_extraction.py`.
- Guidance: CKAN remains bounded trusted catalog/resource access; cache only promoted metadata/resources and record rejection reasons.

**New Deterministic Tool:**
- Primary code: `app/data/deterministic_tools.py` for small tools, or source-specific adapter module in `app/data/` for larger tools.
- Tests: `tests/test_deterministic_tools_and_trace.py` or source-specific tests.
- Guidance: tools may return numbers; LLM nodes may not.

**New Retrieval Ranking or Rerank Logic:**
- Primary code: `app/retrieval/hybrid_retrieval.py`.
- Supporting Qdrant logic: `app/retrieval/embedding_index.py`.
- Tests: `tests/test_hybrid_retrieval.py`.
- Guidance: keep `HybridRetrievalResult` status fields and rejected candidate reasons intact.

**New UI View or Control:**
- Primary code: `app/ui/streamlit_app.py`.
- View models: `app/ui/trace_models.py`.
- Tests: `tests/test_demo_readiness.py` or new UI import/view-model tests.
- Guidance: UI should consume workflow/demo artifacts instead of duplicating product logic.

**New Eval Gate:**
- Primary code: `app/evals/run_eval.py`.
- Supporting scripts: `scripts/run_retrieval_spike.py` only if retrieval-specific.
- Tests: `tests/test_eval_runner.py`.
- Guidance: Phase 2 eval must cover all 20 cases and reject `gated`, `stale`, `skipped_with_reason`, `no_candidate`, or unsupported numeric final states.

**New Artifact Builder Script:**
- Primary code: `scripts/`.
- Reusable logic: import from `app/`.
- Tests: test reusable functions in `tests/`; script smoke can be covered through existing runners.
- Guidance: scripts should write manifest files with artifact paths, counts, hashes, statuses, and rebuild commands.

## Artifact Locations

**Durable Phase 1 Evidence:**
- `.planning/phases/01-data-architecture-research/01-01-SUMMARY.md`
- `.planning/phases/01-data-architecture-research/01-02-SUMMARY.md`
- `.planning/phases/01-data-architecture-research/01-03-SUMMARY.md`
- `.planning/phases/01-data-architecture-research/01-04-SUMMARY.md`
- `.planning/phases/01-data-architecture-research/01-05-SUMMARY.md`
- `.planning/phases/01-data-architecture-research/phase1-test-acceptance.md`
- `.planning/phases/01-data-architecture-research/phase1-actual-state-verification.md`

**Prepared Data Products:**
- `.local/dataagent/phase1/source-cards.json`
- `.local/dataagent/phase1/source-catalog.sqlite`
- `.local/dataagent/phase1/embedding-corpus.jsonl`
- `.local/dataagent/phase1/embedding-cache.jsonl`
- `.local/qdrant/`

**Manifest and Gate Products:**
- `.planning/phases/01-data-architecture-research/source-cards-manifest.json`
- `.planning/phases/01-data-architecture-research/source-catalog-manifest.json`
- `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json`
- `.planning/phases/01-data-architecture-research/embedding-index-manifest.json`
- `.planning/phases/01-data-architecture-research/embedding-index-build.md`
- `.planning/phases/01-data-architecture-research/retrieval-eval.csv`
- `.planning/phases/01-data-architecture-research/retrieval-comparison.md`
- `.planning/phases/01-data-architecture-research/extraction-probes.json`
- `.planning/phases/01-data-architecture-research/extraction-probes.md`
- `.planning/phases/01-data-architecture-research/data-relevance-eval.json`
- `.planning/phases/01-data-architecture-research/data-relevance-eval.md`
- `.planning/phases/01-data-architecture-research/demo-readiness.json`

**Extraction Probe Artifacts:**
- `.planning/phases/01-data-architecture-research/extraction-probe-artifacts/fedstat-wide-preview.sql`
- `.planning/phases/01-data-architecture-research/extraction-probe-artifacts/world-bank-coverage-preview.sql`
- `.planning/phases/01-data-architecture-research/extraction-probe-artifacts/ckan-resource-preview.sql`

**Phase 2 Artifacts:**
- Existing seed inputs: `.planning/phases/02-jury-mvp/02-SEED-CONTEXT.md`, `.planning/phases/02-jury-mvp/remote-workstream-review.md`.
- Future Phase 2 plans/summaries should be added under `.planning/phases/02-jury-mvp/`.
- Future Phase 2 machine-readable outputs should use descriptive names under `.planning/phases/02-jury-mvp/`, such as `workflow-eval.json`, `golden-case-results.json`, `demo-readiness.json`, `dataset-artifacts/`, and `extraction-scripts/`.
- Future large generated local data should use `.local/dataagent/phase2/` and be referenced by manifests in `.planning/phases/02-jury-mvp/`.

## Special Directories

**`.planning/phases/01-data-architecture-research/`:**
- Purpose: Accepted Phase 1 infrastructure plans, summaries, manifests, evals, probes, readiness reports, and verification evidence.
- Generated: Mixed; contains both hand-authored GSD docs and generated JSON/CSV/SQL artifacts.
- Committed: Yes for planning/evidence artifacts.
- Guidance: preserve this directory because Phase 2 uses its golden cases, prepared-data manifests, acceptance reports, and architecture growth map.

**`.planning/phases/02-jury-mvp/`:**
- Purpose: Phase 2 jury MVP planning and future acceptance artifacts.
- Generated: Mixed.
- Committed: Yes.
- Guidance: put Phase 2 plans, summaries, decisions, and machine-readable acceptance evidence here.

**`.planning/codebase/`:**
- Purpose: Codebase maps consumed by GSD planners/executors.
- Generated: Yes.
- Committed: Yes.
- Guidance: update `ARCHITECTURE.md` and `STRUCTURE.md` when architecture or layout changes.

**`.local/dataagent/phase1/`:**
- Purpose: Generated source-card, catalog, embedding corpus, embedding cache, PID/log files.
- Generated: Yes.
- Committed: No.
- Guidance: do not move large generated data into `.planning/`; reference it from manifests.

**`.local/qdrant/`, `.local/qdrant-method-check/`, `.local/qdrant-partial-dev/`:**
- Purpose: Local Qdrant state and experimental/partial local collections.
- Generated: Yes.
- Committed: No.
- Guidance: Qdrant readiness must be recorded in manifests before being used as product evidence.

**`/Users/a/Downloads/dumps/`:**
- Purpose: Local external data dumps for FedStat and World Bank.
- Generated: External local data.
- Committed: No.
- Known paths: `/Users/a/Downloads/dumps/fedstatru/fedstatru.zip`, `/Users/a/Downloads/dumps/wb/data.zip`, `/Users/a/Downloads/dumps.zip`.
- Guidance: scripts may read these paths by default; do not commit dumps.

---

*Structure analysis: 2026-05-10*
