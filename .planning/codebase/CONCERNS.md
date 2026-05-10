# Codebase Concerns

**Analysis Date:** 2026-05-10

## Tech Debt

**Phase 1 readiness is truthful but not product-ready:**
- Issue: The implemented surface is a diagnostic infrastructure slice, not the full jury MVP. `app/demo/run_demo.py`, `app/workflow/run_graph.py`, `app/evals/run_eval.py`, and `app/ui/streamlit_app.py` correctly expose gates, but they do not complete source-bound user answers.
- Files: `app/demo/run_demo.py`, `app/workflow/run_graph.py`, `app/evals/run_eval.py`, `app/ui/streamlit_app.py`, `.planning/phases/01-data-architecture-research/phase1-test-acceptance.md`, `.planning/phases/02-jury-mvp/02-SEED-CONTEXT.md`
- Impact: Phase 1 is acceptable as prepared-data/search/workflow/UI infrastructure only. It blocks Phase 2 until the same paths produce correct terminal outcomes for all 20 golden cases.
- Fix approach: Preserve the source-card corpus, catalog, Qdrant contract, artifact schemas, and trace models; replace the gated graph/readiness path with a real workflow that executes retrieval, coverage, deterministic extraction, critic, visualization, and narration.

**Workflow graph is a narrow smoke path, not the target architecture:**
- Issue: `app/workflow/run_graph.py` builds `IntentFrame`, retrieval evidence, gated coverage/extraction placeholders, and `FinalAnswer`; it does not execute the full node chain from the roadmap.
- Files: `app/workflow/run_graph.py`, `app/workflow/graph_contract.py`, `app/artifacts/workflow_artifacts.py`, `.planning/phases/01-data-architecture-research/langgraph-contract.md`
- Impact: Phase 2 target workflow remains missing: `User query -> Supervisor -> Intent Analyst -> Research Designer / Direct path -> FedStat/WB/CKAN Scouts -> Coverage & Schema -> Extraction Planner -> Deterministic Tools -> Methodology Critic -> Visualization -> Narrator`.
- Fix approach: Use `app/workflow/graph_contract.py` and `app/artifacts/workflow_artifacts.py` as contract seeds, but implement each node as executable code with persisted artifacts and machine-readable status transitions.

**Extraction probes stop before answer-grade extraction:**
- Issue: `scripts/run_extraction_probes.py` records FedStat, World Bank, and CKAN coverage/tool-shape evidence, but all source families end with `extraction_status=skipped_with_reason`.
- Files: `scripts/run_extraction_probes.py`, `app/data/deterministic_tools.py`, `.planning/phases/01-data-architecture-research/extraction-probes.current.json`, `.planning/phases/01-data-architecture-research/extraction-probes.current.md`
- Impact: No golden case can produce deterministic numeric answers through the current pipeline. This is an MVP blocker, not an infrastructure failure.
- Fix approach: Promote source-specific extraction adapters from probe evidence into case-driven tools that produce `DatasetArtifact` records, CSV/Parquet exports, reproducibility scripts, and visualization specs.

**Retrieval relies heavily on lexical matching while dense retrieval is gated/stale:**
- Issue: `app/retrieval/hybrid_retrieval.py` falls back to `LexicalBM25Retriever` and a deterministic keyword reranker when dense Qdrant or bge-reranker access is unavailable.
- Files: `app/retrieval/hybrid_retrieval.py`, `app/retrieval/embedding_index.py`, `scripts/run_retrieval_spike.py`, `.planning/phases/01-data-architecture-research/retrieval-eval.current.csv`
- Impact: Retrieval eval has 20/20 dense rows as `gated_skip`, 14/20 source-family matches, and 6/20 no-candidate rows. Direct indicator ranking is not reliable enough for jury behavior.
- Fix approach: Finish full Qdrant population, refresh manifests, add query embedding checks, and add domain-aware ranking so direct indicator/source matches beat weak contextual matches.

**Readiness and test expectations disagree about stale index status:**
- Issue: `app/demo/run_demo.py` correctly reports `qdrant_status=stale` when index and corpus hashes differ, but `tests/test_demo_readiness.py` accepts only `ready` or `gated_skip`.
- Files: `app/demo/run_demo.py`, `tests/test_demo_readiness.py`, `.planning/phases/01-data-architecture-research/embedding-index-manifest.json`, `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json`
- Impact: `python3 -m pytest -q` currently fails 1 test. The failure is a real stale-artifact signal after the full corpus rebuild, not random test flakiness.
- Fix approach: Either refresh the main Qdrant index manifest to the 36,321-chunk corpus or update the test to accept and assert the explicit stale state until the index is rebuilt.

**Remote workstream is reference-only and unsafe to merge wholesale:**
- Issue: `origin/workstream-1/core-integration` deletes current Phase 1 artifacts/tests/scripts, rewinds planning, keeps stub scout/extraction behavior, and regresses Yandex endpoint/auth.
- Files: `.planning/phases/02-jury-mvp/remote-workstream-review.md`, `.planning/STATE.md`, `.planning/ROADMAP.md`
- Impact: Wholesale merge would erase accepted infrastructure evidence and lower Phase 2 acceptance quality.
- Fix approach: Port only small reviewed ideas such as a single `AgentState`, `StateGraph` routing, explicit typed artifacts, and clarification routing. Do not port old planning state, stubs, or Yandex auth changes.

## Known Bugs

**Pytest failure from stale Qdrant status:**
- Symptoms: `python3 -m pytest -q` reports `1 failed, 26 passed`; failing test is `tests/test_demo_readiness.py::test_demo_readiness_reports_gates_without_dense_success`.
- Files: `tests/test_demo_readiness.py`, `app/demo/run_demo.py`, `.planning/phases/01-data-architecture-research/phase1-test-acceptance.md`
- Trigger: Run `python3 -m pytest -q` while `.planning/phases/01-data-architecture-research/embedding-index-manifest.json` points at the old 11-chunk corpus hash and `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json` records the current 36,321 chunks.
- Workaround: Treat the failure as expected stale-index evidence until the index manifest is refreshed or the test is updated to include `stale`.

**Final answer can report `ok` while coverage and extraction are gated:**
- Symptoms: `python3 -m app.workflow.run_graph ... --index-manifest .planning/phases/01-data-architecture-research/partial-embedding-index-manifest.json` returns top-level `status=ok` and `final_answer.status=ok` while `coverage_status=gated` and `extraction_status=gated`.
- Files: `app/workflow/run_graph.py`, `.planning/phases/01-data-architecture-research/run-graph-smoke.current.json`, `.planning/phases/01-data-architecture-research/phase1-test-acceptance.md`
- Trigger: Running the graph smoke on a case with selected sources but no deterministic extraction.
- Workaround: Do not expose this status as jury-ready behavior. Phase 2 must make final statuses derive from coverage/extraction truth.

**GC-001 retrieves a weak GDP-adjacent FedStat candidate:**
- Symptoms: For "Какой ВВП России в 2024 году?", retrieval picks `fedstat:62470:fedstatru/data/parquet/62470.parquet`, recorded as GDP-related share/context rather than the direct GDP indicator.
- Files: `.planning/phases/01-data-architecture-research/retrieval-eval.current.csv`, `.planning/phases/01-data-architecture-research/phase1-test-acceptance.md`, `app/retrieval/hybrid_retrieval.py`
- Trigger: Lexical/hybrid retrieval with dense status gated.
- Workaround: Treat current retrieval candidates as suggestions requiring critic/coverage validation, not final source selection.

**Streamlit query input does not execute the real workflow:**
- Symptoms: `app/ui/streamlit_app.py` accepts `st.chat_input`, but `active_query` is only displayed; the UI renders readiness artifacts from `app/demo/run_demo.py` and does not call `app/workflow/run_graph.py`.
- Files: `app/ui/streamlit_app.py`, `app/demo/run_demo.py`, `app/workflow/run_graph.py`
- Trigger: User enters any query in Streamlit.
- Workaround: Use current UI only as a diagnostic readiness shell. Phase 2 must wire query submission to the same workflow used by tests/evals.

## Security Considerations

**Local secrets are environment-driven and must stay out of artifacts:**
- Risk: Yandex AI Studio, Yandex embeddings, and Qdrant can be configured via local environment variables. Artifact and planning files are committed and must never include API key values.
- Files: `app/llm/yandex_ai_studio.py`, `app/retrieval/embedding_index.py`, `scripts/build_embedding_index.py`, `.gitignore`, `AGENTS.md`
- Current mitigation: Code loads `.env` through `python-dotenv` and records only missing variable names such as `YANDEX_AI_STUDIO_API_KEY or YANDEX_EMBEDDING_API_KEY` in manifests; `.env` contents were not read for this audit.
- Recommendations: Keep recording env var names only, add tests that generated manifests/logs do not contain key-like values, and never write request headers or raw secret-bearing config to `.planning/`.

**CKAN access is bounded but still a live network dependency:**
- Risk: `app/data/deterministic_tools.py` performs live `requests.get` calls to CKAN endpoints with 20-second timeouts. Unbounded expansion or accepting arbitrary endpoints could create slow or unsafe calls.
- Files: `app/data/deterministic_tools.py`, `scripts/run_extraction_probes.py`, `app/data/source_card_builders.py`
- Current mitigation: CKAN usage is framed as trusted NSED catalog API access, `package_search` uses row limits, and probe code only calls `package_show` for a promoted package id.
- Recommendations: Keep endpoint roots allowlisted for Phase 2, cache promoted CKAN metadata, cap resources inspected, and make live CKAN failures explicit `not_found` or `needs_source_prep` evidence rather than silent retries.

**Generated SQL is restricted but still needs source adapter boundaries:**
- Risk: `app/data/deterministic_tools.py::run_duckdb_query` accepts arbitrary `SELECT`/`WITH` SQL strings. DuckDB can read local files when SQL includes functions such as `read_parquet`.
- Files: `app/data/deterministic_tools.py`, `scripts/run_extraction_probes.py`
- Current mitigation: Non-read SQL is rejected by prefix check, and Phase 1 probes use fixed parameterized toy queries.
- Recommendations: In Phase 2, do not pass free-form LLM SQL directly to `run_duckdb_query`. Generate extraction plans as structured operations over approved local paths, compile them to SQL in deterministic adapters, and log the compiled SQL/script artifact.

**Remote branch includes Yandex auth regression risk:**
- Risk: The reviewed remote branch uses an older Yandex base URL/auth pattern (`https://ai.api.cloud.yandex.net/v1` with bearer auth) instead of the verified current path.
- Files: `.planning/phases/02-jury-mvp/remote-workstream-review.md`, `app/llm/yandex_ai_studio.py`, `tests/test_yandex_ai_studio.py`
- Current mitigation: Current tests assert the verified `https://llm.api.cloud.yandex.net/v1` host and `Api-Key` auth.
- Recommendations: Keep `tests/test_yandex_ai_studio.py` as a merge guard and reject any Phase 2 port that weakens endpoint/auth tests.

## Performance Bottlenecks

**Full embedding build is long-running and currently stale relative to corpus:**
- Problem: Prepared corpus has 36,321 chunks; main index manifest records `chunk_count=11`, `vector_count=0`, old corpus hash, and `dense_status=gated_skip`.
- Files: `scripts/build_embedding_index.py`, `scripts/monitor_embedding_build.py`, `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json`, `.planning/phases/01-data-architecture-research/embedding-index-manifest.json`, `.planning/phases/01-data-architecture-research/demo-readiness.current.json`
- Cause: Full-corpus embedding/indexing depends on Yandex embedding credentials, network throughput, retry policy, cache progress, and manifest refresh.
- Improvement path: Keep resumable cache behavior in `scripts/build_embedding_index.py`, monitor `.local/dataagent/phase1/embedding-cache.jsonl`, refresh `embedding-index-manifest.json` only when collection vector count and corpus hash match, and fail readiness when stale.

**Lexical retrieval loads the full embedding corpus into memory for each retriever:**
- Problem: `app/retrieval/hybrid_retrieval.py::load_documents_from_index_manifest` reads all JSONL lines into a list and `LexicalBM25Retriever` tokenizes all documents in memory.
- Files: `app/retrieval/hybrid_retrieval.py`, `.local/dataagent/phase1/embedding-corpus.jsonl`, `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json`
- Cause: Phase 1 uses a simple BM25 approximation instead of a persistent lexical index.
- Improvement path: For Phase 2, move lexical retrieval to SQLite FTS/DuckDB-backed search or a cached service-level index so each UI query does not rebuild token statistics over 36,321 chunks.

**Qdrant local mode can conflict with concurrent writers/readers:**
- Problem: `app/retrieval/embedding_index.py` uses local Qdrant path `.local/qdrant` by default while scripts may build or query collections concurrently.
- Files: `app/retrieval/embedding_index.py`, `scripts/build_embedding_index.py`, `.local/qdrant/meta.json`
- Cause: Local embedded Qdrant is convenient for Phase 1 but fragile when long builds, UI queries, and evals run at the same time.
- Improvement path: For jury readiness, prefer a single managed local service or clearly separated collection/path per build, then atomically promote a manifest after validation.

**Source-card corpus scale makes rebuilds expensive:**
- Problem: Source-card and embedding corpus artifacts contain 36,321 records, so accidental rebuild/re-embed cycles waste time and can invalidate manifests.
- Files: `scripts/build_source_cards.py`, `scripts/build_source_catalog.py`, `scripts/build_embedding_corpus.py`, `.planning/phases/01-data-architecture-research/source-cards-manifest.json`, `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json`
- Cause: Full prepared data is already large enough that manifest/corpus hash churn matters.
- Improvement path: Preserve current artifacts, rebuild only on source-card contract or source data changes, and use manifest hashes as promotion gates.

## Fragile Areas

**Status semantics are too loose for product acceptance:**
- Files: `app/workflow/run_graph.py`, `app/workflow/graph_contract.py`, `app/artifacts/workflow_artifacts.py`, `app/evals/run_eval.py`
- Why fragile: `WorkflowStatus` allows `ok`, `gated`, `skipped_with_reason`, `needs_clarification`, `no_data`, and `failed`, while Phase 2 acceptance allows only `passed`, `needs_clarification`, or `not_found` as final golden-case terminal outcomes.
- Safe modification: Introduce separate internal component statuses and final user outcome statuses. Final answer generation must be blocked unless coverage/extraction/critic evidence supports the terminal status.
- Test coverage: Existing tests check gated evidence visibility, but no tests assert that `final_answer.status=ok` is impossible when coverage or extraction is gated.

**Readiness artifacts are easy to desynchronize:**
- Files: `.planning/phases/01-data-architecture-research/source-cards-manifest.json`, `.planning/phases/01-data-architecture-research/source-catalog-manifest.json`, `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json`, `.planning/phases/01-data-architecture-research/embedding-index-manifest.json`, `app/demo/run_demo.py`
- Why fragile: Demo readiness depends on multiple generated manifests with hashes, counts, vector counts, and external local artifacts. One stale manifest blocks readiness.
- Safe modification: Treat `app/demo/run_demo.py` as the single readiness gate, add tests for `stale`, and promote index manifests only after checking corpus hash and positive Qdrant vector count.
- Test coverage: `tests/test_demo_readiness.py` currently misses the accepted stale state and fails on current reality.

**Source-card builders normalize heterogeneous metadata into one card model:**
- Files: `app/data/source_card_builders.py`, `app/artifacts/source_cards.py`, `scripts/build_source_cards.py`
- Why fragile: FedStat wide parquet, World Bank indicator metadata, and CKAN package metadata have different coverage, units, geography, and resource semantics. Thin metadata can overstate extraction readiness.
- Safe modification: Keep builder output conservative: metadata cards are retrieval candidates, not extraction guarantees. Require coverage preview before extraction and record missing units/geography/periods explicitly.
- Test coverage: Current tests cover card contract shape and representative builder flags, not answer-grade coverage for all 20 golden cases.

**Partial index can mask main index staleness:**
- Files: `.planning/phases/01-data-architecture-research/partial-embedding-index-manifest.json`, `.planning/phases/01-data-architecture-research/embedding-index-manifest.json`, `app/workflow/run_graph.py`, `app/demo/run_demo.py`
- Why fragile: Workflow smoke can run against `partial_ready` with 5,748 vectors while demo readiness correctly blocks on the main stale manifest.
- Safe modification: Make Phase 2 tests and UI use one canonical readiness-approved manifest. Partial manifests can remain debugging artifacts but must not satisfy jury readiness.
- Test coverage: Existing smoke tests assert trace emission, not full readiness or all-case correctness.

**UI view models are diagnostic-only but look interactive:**
- Files: `app/ui/streamlit_app.py`, `app/ui/trace_models.py`, `app/demo/run_demo.py`
- Why fragile: Users can enter a query, but the query does not drive retrieval/extraction/answer generation. This can create false confidence during demos.
- Safe modification: Disable or label diagnostic-only paths until Phase 2 wires the query to the real workflow. The production UI should call the same workflow/eval code path and render returned artifacts.
- Test coverage: `tests/test_demo_readiness.py` only checks import/view-model readiness, not query execution.

**Remote integration ideas overlap current contracts without matching current state:**
- Files: `.planning/phases/02-jury-mvp/remote-workstream-review.md`, `app/workflow/graph_contract.py`, `app/artifacts/workflow_artifacts.py`
- Why fragile: Similar concepts from the remote branch can look merge-ready while deleting accepted artifacts and tests.
- Safe modification: Cherry-pick ideas manually and run `python3 -m pytest -q`, readiness, retrieval eval, extraction eval, and golden-case eval after every port.
- Test coverage: No automated guard checks that Phase 1 planning/evidence artifacts remain present after a merge.

## Scaling Limits

**Golden-case acceptance is still all gated:**
- Current capacity: `app/evals/run_eval.py` can score 20 golden cases and records `passed=0`, `failed=0`, `gated=20` in `.planning/phases/01-data-architecture-research/data-relevance-eval.current.json`.
- Limit: The system cannot scale to jury acceptance while Qdrant/dense retrieval and deterministic extraction remain gated.
- Scaling path: Turn the eval runner into the Phase 2 acceptance harness with strict terminal states, then make each implementation wave reduce gated rows until all 20 cases reach `passed`, `needs_clarification`, or `not_found`.

**Prepared data is local-machine dependent:**
- Current capacity: Manifests point to `.local/dataagent/phase1/*` artifacts and local dumps under `/Users/a/Downloads/dumps`.
- Limit: A fresh machine without these local artifacts cannot reproduce retrieval or readiness from git alone.
- Scaling path: Keep large dumps uncommitted, but document exact local artifact preparation commands, validate missing artifacts as explicit gates, and use content hashes for promoted artifacts.

**Current CKAN path is metadata-first, not data-product-first:**
- Current capacity: CKAN source cards can be built from bounded package metadata and resource summaries.
- Limit: CKAN extraction has no promoted package/resource data path, so CKAN-required golden cases cannot pass as `passed` without further preparation.
- Scaling path: Promote CKAN resources case by case, cache package/resource metadata, add source-specific download/format validation, and return `not_found` only after checked/rejected source evidence exists.

## Dependencies at Risk

**Yandex AI Studio / embeddings credentials:**
- Risk: Missing or mismatched credentials gate Qwen structured output and dense embeddings; folder/model mismatches are known to produce permission errors.
- Impact: `app/llm/yandex_ai_studio.py` and `app/retrieval/embedding_index.py` cannot provide live Qwen/dense behavior; evals remain gated.
- Migration plan: Keep explicit `gated_skip` behavior for absent credentials, but Phase 2 jury readiness needs either verified live credentials or a recorded decision for deterministic fallback where credentials are absent.

**Qdrant local embedded mode:**
- Risk: Local path mode is fast but fragile under concurrent build/query and can produce stale manifests if collection state is not promoted atomically.
- Impact: Demo readiness remains `blocked` / `stale`, and dense retrieval cannot be trusted.
- Migration plan: Use the same `QdrantEmbeddingIndex` abstraction with either a managed local Qdrant service or isolated build/promote directories; keep manifest checks mandatory.

**Requests-based live services:**
- Risk: CKAN and Yandex calls rely on network availability, API timeouts, and remote schemas.
- Impact: Phase 2 may fail unpredictably if live calls are used in the UI without cached evidence or bounded retries.
- Migration plan: Cache promoted metadata/artifacts for demo cases, keep live calls bounded, and separate live-source refresh from answer execution.

**Remote workstream branch:**
- Risk: Its contracts overlap attractive Phase 2 work but regress current artifacts, tests, and Yandex integration.
- Impact: Direct merge can destroy current accepted infrastructure and mislead acceptance.
- Migration plan: Do not merge wholesale. Port small pieces only after comparing against `.planning/phases/02-jury-mvp/remote-workstream-review.md`.

## Missing Critical Features

**Real Phase 2 workflow runtime:**
- Problem: The current graph does not execute the full source-bound workflow from user query through deterministic answer.
- Blocks: Jury MVP, all 20 golden-case terminal outcomes, product UI.
- Files: `app/workflow/run_graph.py`, `app/workflow/graph_contract.py`, `.planning/phases/02-jury-mvp/02-SEED-CONTEXT.md`

**Strict terminal outcome model:**
- Problem: Current outputs use `ok`, `gated`, `no_data`, and `skipped_with_reason`; Phase 2 final states must be `passed`, `needs_clarification`, or `not_found`.
- Blocks: Machine-readable acceptance and honest final answers.
- Files: `app/artifacts/workflow_artifacts.py`, `app/workflow/run_graph.py`, `app/evals/run_eval.py`

**Answer-grade deterministic extraction adapters:**
- Problem: FedStat, World Bank, and CKAN have probe scaffolds but no case-complete extraction path.
- Blocks: Numeric answers, dataset export, reproducibility scripts, visualizations from data.
- Files: `app/data/deterministic_tools.py`, `scripts/run_extraction_probes.py`, `app/data/source_card_builders.py`

**Jury UI that executes the evaluated workflow:**
- Problem: Streamlit renders readiness and trace view models but does not submit queries into the workflow.
- Blocks: User-facing demo acceptance at `http://localhost:8501`.
- Files: `app/ui/streamlit_app.py`, `app/demo/run_demo.py`, `app/workflow/run_graph.py`

**Dense Qdrant readiness over the full corpus:**
- Problem: Main manifest is stale relative to the 36,321-chunk corpus and has zero vectors.
- Blocks: Dense retrieval, hybrid ranking confidence, demo readiness.
- Files: `.planning/phases/01-data-architecture-research/embedding-index-manifest.json`, `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json`, `scripts/build_embedding_index.py`

**Coverage preview before extraction for every passed case:**
- Problem: Coverage is currently a gated artifact, not a source-specific verification of periods, geographies, units, frequency, and missing values.
- Blocks: Source-bound answers and methodology critic acceptance.
- Files: `app/workflow/run_graph.py`, `app/data/deterministic_tools.py`, `.planning/phases/01-data-architecture-research/extraction-probes.current.json`

**Methodology critic enforcement:**
- Problem: Critic/narrator trace exists, but it does not block `ok` final status when coverage/extraction are gated.
- Blocks: Reliable final answer status and unsupported-claim prevention.
- Files: `app/workflow/run_graph.py`, `app/artifacts/workflow_artifacts.py`, `tests/test_workflow_graph.py`

## Test Coverage Gaps

**No all-20 Phase 2 acceptance test:**
- What's not tested: Correct terminal outcomes for all 20 golden cases with no `gated`, `stale`, `skipped_with_reason`, or `no_candidate` final states.
- Files: `app/evals/run_eval.py`, `.planning/phases/01-data-architecture-research/golden-cases.yaml`, `tests/test_eval_runner.py`
- Risk: Small representative demos can pass while the MVP fails the user's stated acceptance bar.
- Priority: High

**No test prevents `final_answer.status=ok` with gated coverage/extraction:**
- What's not tested: Final answer status must match coverage and extraction truth.
- Files: `app/workflow/run_graph.py`, `tests/test_workflow_graph.py`
- Risk: UI or eval may present gated results as successful answers.
- Priority: High

**No UI test verifies query submission runs workflow:**
- What's not tested: A Streamlit query calling the same workflow/eval path and rendering returned sources, coverage, dataset/script, visualization, answer, and trace.
- Files: `app/ui/streamlit_app.py`, `tests/test_demo_readiness.py`
- Risk: UI can remain a diagnostic shell while appearing interactive.
- Priority: High

**No deterministic extraction tests against real promoted cases:**
- What's not tested: FedStat wide parquet normalization, World Bank long parquet filtering, and CKAN promoted resource extraction producing `DatasetArtifact` records for golden cases.
- Files: `app/data/deterministic_tools.py`, `scripts/run_extraction_probes.py`, `tests/test_deterministic_tools_and_trace.py`
- Risk: Extraction remains probe-level and never proves numeric answer capability.
- Priority: High

**No stale-manifest acceptance test despite live stale state:**
- What's not tested: Readiness should explicitly accept `stale` as a possible blocked state and assert its reason.
- Files: `app/demo/run_demo.py`, `tests/test_demo_readiness.py`
- Risk: Tests fail on correct stale detection or get loosened incorrectly.
- Priority: Medium

**No regression guard for preserving Phase 1 artifacts during branch ports:**
- What's not tested: Required Phase 1 scripts, tests, manifests, summaries, and evidence artifacts still exist after integrating remote ideas.
- Files: `.planning/phases/02-jury-mvp/remote-workstream-review.md`, `.planning/phases/01-data-architecture-research/`, `scripts/`, `tests/`
- Risk: A tempting workflow branch can delete accepted infrastructure.
- Priority: Medium

**No manifest secret-leak test:**
- What's not tested: Generated manifests/build logs avoid writing actual API key values.
- Files: `scripts/build_embedding_index.py`, `app/llm/yandex_ai_studio.py`, `.planning/phases/01-data-architecture-research/embedding-index-build.md`, `.planning/phases/01-data-architecture-research/embedding-index-manifest.json`
- Risk: Future logging changes can leak secrets into committed planning artifacts.
- Priority: Medium

---

*Concerns audit: 2026-05-10*
