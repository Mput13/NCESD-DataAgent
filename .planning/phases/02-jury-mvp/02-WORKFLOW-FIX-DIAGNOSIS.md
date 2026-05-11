# Phase 2 Workflow Fix Diagnosis

**Created:** 2026-05-11  
**Updated:** 2026-05-11 after graph-aware RAG code review  
**Purpose:** зафиксировать ошибки текущего Phase 2 workflow перед переработкой кода.  
**Scope:** запрос пользователя -> агенты/узлы -> артефакты -> eval/UI.  

## Executive Summary

Phase 2 сейчас выглядит не как самостоятельный source-bound агент, а как смесь:

- реального workflow service;
- golden-case acceptance harness;
- подсказочной `golden-coverage-matrix`;
- live LLM требований без стабильного bounded режима;
- слишком слабого eval, который пропускает пустые ответы как "acceptable".

Главная проблема не в самом русском языке. Файлы реально сохранены в UTF-8, русские строки в `golden-cases.yaml` и Python-коде читаются корректно. Видимые `Рљ...` в PowerShell - это проблема отображения консоли. Но русская семантика всё равно обрабатывается хрупко: через небольшие alias/synonym словари, regex и LLM-промпты без отдельного слоя нормализации запроса.

Самая опасная архитектурная ошибка: acceptance fixtures начали протекать в runtime. `case_id` из acceptance runner попадает в `Phase2State`, после чего `Research Designer` читает `golden-coverage-matrix.json` и передает `matrix_hint` в LLM. Это превращает golden cases из независимого измерителя качества в подсказку для агента. В обычном пользовательском запросе такой подсказки нет, поэтому eval начинает проверять не продукт, а продукт плюс шпаргалку.

После добавления graph-aware RAG часть retrieval-артефактов изменилась. Теперь актуальная картина не "dense + lexical + reranker seam", а:

```text
query
-> LexicalBM25Retriever
-> DenseQdrantRetriever
-> KnowledgeGraphStore.graph_first_card_ids(query)
-> GraphExpander.expand(dense seed card_ids)
-> Qdrant payload fetch for graph neighbours
-> RRF fusion
-> HybridRetrievalResult(candidates, rejected_candidates, SubgraphContext)
```

Это улучшает retrieval-контекст, но не исправляет само по себе workflow-ошибки: graph candidates всё равно должны пройти coverage, extraction planner, deterministic tools, critic и acceptance scoring. Graph RAG не должен получать `golden-coverage-matrix` как answer key.

## Current Runtime Data Flow

Фактическая цепочка сейчас:

```text
scripts/run_phase2_acceptance.py
  -> loads golden-cases.yaml
  -> loads golden-coverage-matrix.json
  -> for each case builds WorkflowRunConfig(case_id=GC-...)
  -> app.workflow.service.run_user_query(query, run_config)
  -> run_user_query_to_pending_finalization()
  -> initial Phase2State includes:
       run_id
       query
       intent=None
       evidence=None
       coverage_reports=[]
       extraction_plan=None
       dataset_artifacts=[]
       script_artifacts=[]
       _case_id=GC-...
       _live_llm_required=True
       _live_embeddings_required=True
  -> app.workflow.graph.build_phase2_graph().invoke(state)
  -> supervisor
  -> intent_analyst
  -> research_designer
       reads golden-coverage-matrix.json when _case_id exists
       passes matrix_hint to design_research()
  -> source_scouts
       run_source_scouts()
       -> HybridRetriever.search()
       -> BM25 + dense Qdrant + graph_first + graph expansion + RRF
       -> EvidenceBundleArtifact(selected_sources, rejected_sources)
  -> coverage_schema
  -> extraction_planner
  -> deterministic_tools
  -> finalization_pending
  -> service._finalize_state()
  -> critic
  -> visualization
  -> narrator
  -> WorkflowResponse
  -> acceptance scorer
```

This means the product path and eval path are not cleanly separated.

## Target Runtime Data Flow

Нужная цепочка должна быть такой:

```text
User query
  -> RequestEnvelope
       query_text
       locale/language
       user_context (optional, non-secret)
       runtime_options (timeouts, live/mock policy)
       no golden expected answer
  -> Supervisor
       decides route budget only
       direct | research | clarification | no_data_candidate
  -> Intent Analyst
       produces IntentFrame:
         category
         metric/concept candidates
         geography candidates
         period policy
         source preferences explicitly stated by user
         missing critical fields
         confidence + ambiguity reasons
  -> Research Designer
       only for research/comparative/derived cases
       produces ResearchDesignArtifact:
         hypotheses
         indicators needed
         dimensions
         join/formula policy
         assumptions
       must not receive golden expected source_id
  -> Source Scouts
       FedStat scout
       World Bank scout
       CKAN scout
       each scout receives IntentFrame + optional ResearchDesignArtifact
       each scout returns SourceCandidateCard-like selected/rejected evidence
       graph-aware retrieval may add SubgraphContext as context/evidence
       graph output is not itself proof of coverage or extractability
  -> Coverage & Schema
       deterministic adapter inspection first
       checks available periods/geographies/units/frequency/missing values
       returns CoverageReport per candidate
  -> Extraction Planner
       receives only IntentFrame + ResearchDesignArtifact + CoverageReports
       emits allowlisted operations and typed filters
       no arbitrary SQL from user/LLM
  -> Deterministic Tools
       executes source adapters
       emits DatasetArtifact + ScriptArtifact or NoDataExplanationArtifact
  -> Methodology Critic
       verifies data/source/methodology consistency
       can request repair or clarification
  -> Visualization
       builds chart/table spec only from DatasetArtifact
  -> Narrator
       produces user-facing message from artifacts
       numbers only from DatasetArtifact records/provenance
  -> WorkflowResponse
       final_outcome: passed | needs_clarification | not_found
       includes trace, sources, coverage, extraction, dataset/script, limitations
```

Eval should wrap this same path from outside:

```text
Golden case
  -> run normal user query without expected source_id/source_family hints
  -> compare WorkflowResponse to expected rubric
  -> fail if expected passed but response is not_found/needs_clarification without evidence
```

## Finding 1 - Golden Matrix Leaks Into Runtime

**Symptom:** Phase 2 code can behave differently when invoked by golden-case eval than when invoked by a real user.

**Evidence:**

- `WorkflowRunConfig` carries `case_id`; service copies it into internal `_case_id`.
- `graph.py` checks `_case_id`, loads `.planning/phases/02-jury-mvp/golden-coverage-matrix.json`, builds `matrix_hint`, and passes it to `design_research`.
- `state.py` explicitly adds `matrix_hint` into the Research Designer prompt as "Подсказка из матрицы покрытия".

**Why this likely happened:** the team tried to force all 20 golden cases to pass quickly. The golden matrix was originally useful as an external coverage plan, but then became part of the agent's thinking.

**Why this is bad:** the agent is no longer solving the user request. It is solving "user request + hidden answer key". Any success under this mode is not evidence that arbitrary jury queries work.

**How it should be implemented:**

- `case_id` may exist only in eval metadata, not inside `Phase2State`.
- `golden-coverage-matrix.json` may be used by acceptance scorer after a response is produced.
- Runtime may use source catalog, retrieval index, source cards, and deterministic adapters.
- Runtime must never use expected terminal outcome, expected adapter, expected source family, expected source id, or expected filters from golden fixtures.

**Fix direction:**

- Remove `_case_id` from `Phase2State`.
- Remove `matrix_hint` from `design_research`.
- Keep `case_id` only in `run_acceptance` result rows and artifact folder naming.
- Add a test that fails if `app/workflow/**` reads `golden-coverage-matrix.json` or `golden-cases.yaml`.

## Finding 2 - Acceptance Scoring Allows Empty `not_found` For Expected `passed`

**Symptom:** existing `.planning/phases/02-jury-mvp/phase2-golden-results.json` reports `unacceptable=0` while it contains 16 `not_found` outcomes, many with `sources_count=0`, `dataset_count=0`, `script_count=0`, and expected `passed`.

**Evidence:**

- `phase2-golden-results.json` summary: `passed=0`, `needs_clarification=4`, `not_found=16`, `unacceptable=0`.
- Many cases have `matrix_expected_terminal_outcome="passed"` and `final_outcome="not_found"` with no sources/datasets/scripts.
- `scripts/run_phase2_acceptance.py::_check_matrix_alignment` allows any valid terminal outcome when expected outcome is `passed`.

**Why this likely happened:** the acceptance bar was encoded as "avoid invalid statuses" instead of "meet the case-specific expected behavior". That made `not_found` a universal escape hatch.

**How it should be implemented:**

For each golden case:

- If expected is `passed`, `final_outcome` must be `passed`.
- If expected is `needs_clarification`, response must include specific clarification questions and no extraction.
- If expected is `not_found`, response must include checked sources, rejected sources, and rejection reasons.
- For `passed`, acceptance must require non-empty selected sources, coverage reports, at least one ok dataset when the request asks for data, script artifact, trace events, and source-bound citations.
- A `not_found` for expected `passed` can be acceptable only if the matrix explicitly allows an alternative and records the evidence reason. That exception must be rare and machine-readable.

**Fix direction:**

- Rewrite `_check_matrix_alignment` to treat `expected=passed, got=not_found` as failure by default.
- Add artifact-count and evidence-count checks to `_score_response`.
- Fail empty `not_found`: no checked sources or no rejection reasons must be unacceptable.
- Update demo readiness to depend on passed counts, not just `unacceptable=0`.

## Finding 3 - Product CLI Is Not Reproducible From Windows PowerShell

**Symptom:** `python scripts\run_phase2_acceptance.py --limit 3` fails with `ModuleNotFoundError: No module named 'app'`.

**Evidence:** direct run from repo root failed until `PYTHONPATH=.` was set.

**Why this matters:** if the primary verification command does not run in the user's shell, downstream agents will make local assumptions, skip the command, or produce stale evidence.

**How it should be implemented:**

- Either package the repo in editable mode, or make scripts add repo root to `sys.path` consistently.
- All docs should provide Windows-compatible and POSIX-compatible commands.
- CI/test commands should use the same import path as local scripts.

**Fix direction:**

- Add a small bootstrap at top of `scripts/run_phase2_acceptance.py`, or move it to `python -m scripts.run_phase2_acceptance`.
- Update README and Phase 2 docs with exact commands.

## Finding 4 - Acceptance Can Hang Without Bounded Component Timeouts

**Symptom:** `PYTHONPATH=.; python scripts\run_phase2_acceptance.py --limit 3` timed out after more than 180 seconds.

**Likely causes:**

- multiple live LLM calls per query: supervisor, intent analyst, research designer, coverage assessment, extraction planner, critic, narrator;
- dense retrieval can call query embeddings/Qdrant;
- CKAN scout can hit network;
- no per-node budget in `WorkflowRunConfig`.

**How it should be implemented:**

Each workflow run should carry explicit budgets:

```text
WorkflowRunConfig
  total_timeout_s
  node_timeout_s
  llm_timeout_s
  retrieval_timeout_s
  ckan_timeout_s
  qdrant_timeout_s
  max_llm_calls
  max_selected_sources
  max_rejected_sources
```

Each node should return a typed gate/failure artifact when budget is exceeded. The final response can be `not_found` or `needs_clarification` only if evidence supports it; otherwise verification should fail as `runtime_timeout`.

**Fix direction:**

- Add timeouts to config and pass them into Yandex, Qdrant, CKAN, and node execution.
- Acceptance runner should have per-case timeout and produce `run_timeout` unacceptable reason.
- Trace events should include duration and timeout reason.

## Finding 5 - Russian Query Handling Is Too Narrow, Not Encoding-Broken

**Symptom:** Russian strings are correctly encoded, but query understanding still depends on small handcrafted alias maps and synonyms.

**Evidence:**

- `query_understanding.py` has limited `CONCEPTS`, `_GEO_ALIASES`, and source aliases.
- `hybrid_retrieval.py` uses limited `_STOPWORDS`, `_SYNONYM_MAP`, and query phrase filters.
- This is okay as a retrieval helper, but risky as the main source of semantic robustness.

**Why this likely caused bad behavior:** Russian economic requests have morphology, abbreviations, mixed source names, and ambiguous concepts. A narrow alias list can overfit to the 20 golden cases while failing natural variations.

**How it should be implemented:**

Use a layered query understanding contract:

```text
Raw user text
  -> LanguageNormalizer
       lowercase/casefold
       ё/е policy
       punctuation and dash normalization
       Russian morphology/stemming where practical
       abbreviation expansion: РФ, Росстат, ЕМИСС, ИПЦ, ВВП, ППС
  -> Intent Analyst LLM
       structured JSON with confidence
       missing field detection
       candidate concepts, not single forced answer
  -> Deterministic Concept Resolver
       maps concepts to known catalog concepts and source families
       keeps alternatives with scores
  -> Source Scouts
```

The LLM should not directly choose a hidden golden source. It should produce structured intent candidates; deterministic resolvers and retrieval should ground them.

**Fix direction:**

- Add `QueryUnderstandingArtifact` before `IntentFrame`, or expand `IntentFrame` with normalized query, concept candidates, confidence, and alternatives.
- Add tests with Russian paraphrases outside the 20 golden cases.
- Separate "source preference explicitly stated by user" from "source family guessed by system".

## Finding 5A - Graph RAG Helps Recall But Can Hide Semantic Overfit

**Symptom:** graph-aware retrieval introduces `graph_first` and graph expansion, but the graph is built from the same source-card metadata and the same narrow query understanding aliases.

**Current implementation shape:**

- `query_understanding.py` parses concepts, geographies, years, and source families.
- `graph_store.py` builds an in-memory SQLite graph with SourceCard, Indicator, Dataset, Provider, Unit, Geography, Period, Resource, Concept, and Alias nodes.
- `HybridRetriever.search()` fuses lexical, dense, graph-first, and graph-neighbour candidates with RRF.
- `SubgraphContext` can be passed upstream as structured context.

**Why this matters:** Graph RAG can improve recall for semantically adjacent cards, but it can also amplify bad aliases or weak concepts. If "ВВП" maps too broadly, graph expansion can return plausible-but-wrong GDP-adjacent cards. If source preference is treated as expected source instead of user-stated preference, graph filtering can reject useful alternatives too early.

**How it should be implemented:**

Graph RAG should be treated as retrieval evidence:

```text
Graph candidate
  -> SourceCandidateArtifact
  -> CoverageReport
  -> ExtractionPlan
  -> DatasetArtifact or NoDataExplanationArtifact
```

It should not produce terminal decisions directly. A graph neighbour is only "interesting", not "correct", until deterministic coverage and extraction confirm it.

**Fix direction:**

- Include `retrieval_path` / `fusion_modes` / `subgraph_context` in source candidate evidence so downstream agents can see why a card appeared.
- Add exact-source and extraction-ready top-k retrieval metrics for `hybrid_graph`, not just source-family hits.
- Add paraphrase tests where graph-first should help, and adversarial tests where graph expansion must not over-select broad period/geography/unit neighbours.
- Update `graph_store.py` documentation if needed: current code uses in-memory SQLite metadata graph, not a separate graph embedding collection.

## Finding 6 - Agents Are Nodes, But Their Interfaces Are Too Implicit

**Symptom:** The graph names agents, but many handoffs are plain dicts inside `Phase2State`, and downstream nodes infer meaning from ad hoc fields.

**Examples:**

- Scouts return selected/rejected source dicts, not a stricter `SourceCandidateArtifact`.
- Coverage receives `intent_fields` from `IntentFrame.known_fields`, which may lack normalized countries/periods/indicator IDs.
- Extraction planner picks primary report by source_id and available periods, then deterministic tools infer source family from `source_id` string.
- `_resolve_source_family` uses string heuristics like uppercase/dot patterns.

**How it should be implemented:**

Each agent handoff should have an explicit contract:

```text
Intent Analyst -> IntentFrame
  normalized_query
  category
  concepts[]
  geographies[]
  periods[]
  source_preferences_from_user[]
  missing_fields[]
  ambiguity_reasons[]

Research Designer -> ResearchDesignArtifact
  required_indicators[]
  dimensions[]
  formulas[]
  join_keys[]
  assumptions[]

Source Scout -> SourceCandidateArtifact[]
  source_family
  source_id
  card_id
  indicator_id
  title
  match_mode
  retrieval_path
  fusion_modes
  subgraph_context_id
  confidence
  provenance_url
  coverage_hints
  extraction_readiness
  rejection_reasons[]

Coverage -> CoverageReport[]
  source_family
  source_id
  requested_filters
  available_periods
  available_geographies
  unit
  frequency
  status
  reason

Extraction Planner -> ExtractionPlan
  source_family
  source_id
  adapter_name
  typed_filters
  operations
  formula/join plan if needed
```

**Fix direction:**

- Add `source_family` and `adapter_name` directly to `ExtractionPlan`.
- Stop inferring source family from string patterns.
- Replace generic selected source dicts with Pydantic artifacts or typed models.
- Add contract tests that create each artifact and pass it to the next node without golden fixtures.

## Finding 7 - Offline/No-Response LLM Fallbacks Are A Product Bug

**Symptom:** Phase 2 accumulated many workarounds whose purpose is to keep the workflow "working" when the LLM is unavailable, offline, missing credentials, or not responding. This is the wrong product behavior.

Examples already visible in the codebase:

- `WorkflowRunConfig.live_llm_required=False` lets callers request a non-live path.
- `app/workflow/run_graph.py` exposes `--no-live-llm` and describes deterministic fallback for tests.
- `app/workflow/service.py::continue_user_query` merges clarification manually if LLM re-analysis fails.
- `app/workflow/nodes/coverage.py` returns deterministic reports as-is when LLM assessment fails.
- `app/workflow/nodes/extraction_planner.py` falls back to rule-based operation/filter selection on LLM error.
- `app/workflow/nodes/narrator.py` still contains test-only fallback scaffolding and message markers.
- Tests still normalize the idea that `live_llm_required=False` can return terminal responses in some service paths.

**Why this is bad:** the target product requires real Yandex/Qwen calls for Supervisor, Intent Analyst, Research Designer, Coverage assessment where used, Extraction Planner reasoning, Methodology Critic, and Narrator. If the LLM is unavailable, the system must not silently continue with keyword/rule/manual substitutes and must not produce a jury-ready response.

This is not a useful offline feature. It hides integration failures and encourages agents to build around no-internet/no-response behavior instead of fixing the live path.

**How it should be implemented:**

```text
RuntimeMode:
  LIVE_JURY
    requires Qwen credentials
    requires embedding/Qdrant readiness
    requires network/API response within timeout
    no offline or no-response fallback
    LLM failure -> explicit gated/error artifact, not terminal success
  UNIT_TEST
    may mock YandexAIStudioClient.structured_chat at test boundary only
    verifies contracts and routing
```

There should be no product/runtime mode that says "LLM unavailable, keep going with local heuristics". Unit tests can mock the LLM dependency, but runtime code must not contain fake LLM behavior.

**Fix direction:**

- Remove `live_llm_required=False` as a product/runtime path. If retained for tests, keep it outside product service entrypoints or make it raise immediately.
- Remove `--no-live-llm` from product workflow CLI, or mark it as unit-test-only and ensure it cannot generate acceptance/readiness artifacts.
- Delete/manual-fail all no-response fallbacks in workflow nodes:
  - no manual clarification merge when LLM re-analysis fails;
  - no rule-based extraction planner fallback after Qwen failure;
  - no silent coverage "LLM failed, continue anyway" path for product mode;
  - no narrator fallback response.
- Replace these with explicit `llm_unavailable`, `llm_timeout`, or `llm_error` component status and trace evidence.
- Acceptance/demo readiness must fail if any LLM node used offline fallback, no-response fallback, or skipped live model execution.
- Tests should mock the Yandex client directly and assert the runtime called it, not ask product code to run "without LLM".

## Finding 8 - Trace Exists, But It Is Not Strong Enough As Evidence

**Symptom:** trace count can be 0 or 1 in `phase2-golden-results.json`, yet the result is still acceptable.

**How it should be implemented:**

For a `passed` response, trace should contain at least:

```text
supervisor
intent_analyst
source_scouts
coverage_schema
extraction_planner
deterministic_tools
critic
narrator
```

For `needs_clarification`:

```text
supervisor
intent_analyst
clarification decision with missing fields
```

For `not_found`:

```text
supervisor
intent_analyst
source_scouts
coverage_schema or bounded search evidence
not_found explanation
```

**Fix direction:**

- Acceptance should check required trace states by final outcome.
- Trace events should carry node input summary, output artifact id, decision, duration, and warnings.
- UI should render trace from the same `WorkflowResponse`, not from separate debug-only artifacts.

## Priority Fix Order

1. **Separate eval fixtures from runtime.** Remove golden matrix hints from graph/state/research designer.
2. **Fix acceptance scorer.** `expected=passed` must not accept empty `not_found`.
3. **Make CLI reproducible and bounded.** Fix imports and add per-case timeout.
4. **Strengthen handoff contracts.** Add typed source candidate and extraction plan routing fields.
5. **Rebuild query understanding.** Add Russian normalization/concept candidates before retrieval.
6. **Make Graph RAG auditable.** Record graph-first/graph-neighbour evidence without treating graph hits as final truth.
7. **Define runtime modes.** LIVE_JURY vs LOCAL_DEV vs UNIT_TEST.
8. **Add non-golden smoke set.** Test arbitrary Russian paraphrases so code stops orbiting only the 20 cases.

## Notes For Future Agents

- Golden cases are an acceptance/eval set, not a product API and not a hidden prompt source.
- The agent must be source-bound: numbers from deterministic adapters only.
- CKAN is bounded trusted catalog search, not general web search.
- If the system cannot find data, it must show checked sources and rejection reasons.
- If the system asks clarification, it must name missing fields and concrete options.
- If a query is expected to pass, `not_found` is a failure unless an explicit evidence-backed alternative outcome is allowed.
