# Roadmap: DataAgent

**Created:** 2026-05-08  
**Reset:** 2026-05-10  
**Granularity:** Explicit Phase 1 infrastructure acceptance followed by Phase 2 jury MVP  
**Core Value:** Опора на факты — каждая цифра со ссылкой, числа извлекает код

---

## Phase 1: Data Architecture Implementation (`01-data-architecture-research`)

**Canonical directory:** `.planning/phases/01-data-architecture-research`

**Naming note:** the slug keeps `research` for continuity with existing GSD artifacts. In this roadmap, Phase 1 is not prose-only research. It is the single implementation-oriented phase for the current milestone: build the MVP architecture through small, verifiable plans, deterministic source adapters, a durable prepared-data and embedding-index product, traceable artifacts, and an end-to-end demo path.

**Goal:** Implement and validate the DataAgent architecture enough to demonstrate the core data loop on prepared data: natural-language request → structured intent/research design → relevant source discovery over a materialized FedStat, World Bank, and CKAN metadata/Qdrant embedding index → deterministic coverage/extraction path → source-bound artifacts → visible diagnostic Streamlit trace and feedback loop. Current priority is data relevance and extraction correctness; UI beauty and polished output are deferred.

**Boundary:** Phase 1 may create production-bound code, scripts, tests, data-preparation manifests, local embedding indexes, and UI contracts. By the end of Phase 1 the source-card corpus and embedding/search index should be ready for demo use; rebuilding that data in a later phase should be treated as an exceptional recovery path, not the normal plan. Every implemented slice needs explicit evidence, deterministic verification, and a summary artifact.

**Scalability contract:** Phase 1 is allowed to implement a narrow working slice, but it must be designed as the seed of the full `.planning/ARCHITECTURE_STACK.md` vision. Any shortcut must preserve extension seams: source adapters, typed artifacts, embedding document format, Qdrant collection contract, retrieval providers, graph nodes, deterministic tools, trace events, and UI view models should be replaceable or extensible without rewriting or re-embedding the whole data product.

**Covers:** NLU-01..04, SRCH-01..04, DATA-01..05, ART-01..06, RBST-01..04, UI-01..04, ENG-01..04

**Execution model:** single-track GSD execution. Do not split work into Core/Data/UI owners or parallel human workstreams unless the roadmap is explicitly changed.

### Plans

- [x] `01-01-PLAN.md` — Requirements map, 15-20 golden cases, and eval rubric
- [x] `01-02-PLAN.md` — Prepared-data contract, source-card builders, and embedding corpus format
- [x] `01-03-PLAN.md` — Materialized embedding/search index and retrieval evaluation
- [x] `01-04-PLAN.md` — Qwen/Yandex, runnable LangGraph narrow flow, deterministic extraction, data-relevance eval, and diagnostic UI models while indexing runs
- [x] `01-05-PLAN.md` — Runnable readiness/demo package over prepared data, Qdrant status, relevance/extraction evidence, and minimal diagnostic Streamlit surface

### Deliverables

- Requirement-to-artifact map covering all v1 requirements.
- 15-20 test cases across simple, comparative, research, derived metric, ambiguous, and no-data requests.
- Deterministic source inventory for local dumps and bounded CKAN package/resource access.
- Shared source-card/evidence contracts for FedStat, World Bank, and CKAN.
- Local SQLite/DuckDB catalog for source cards, schemas, coverage hints, embedding chunks, and rejection logs.
- Stable embedding document/chunk format with source ids, chunk ids, content hashes, metadata version, provenance, coverage, units, dimensions, and source/resource URLs.
- Materialized local source-card corpus and embedding/search index ready for demo use, with manifest, build logs, provider/model metadata, and rebuild instructions.
- Retrieval implementation and evaluation over a real Qdrant collection with lexical BM25/FTS, dense embeddings, bge-reranker-compatible rerank seam, and credential-aware fallback evidence. Phase 1 may use Qdrant local persistent mode for speed, but retrieval must use the Qdrant client/collection abstraction rather than a throwaway custom vector index. Missing embedding credentials may gate vector population, but do not permit replacing Qdrant with a custom vector path.
- DuckDB SQL-first extraction probes, deterministic tool contracts, DatasetArtifact export, and adapter strategy for FedStat, World Bank, and CKAN.
- Hardened Yandex AI Studio/Qwen integration notes and runnable gated checks.
- Runnable narrow LangGraph flow with typed artifacts, budgets/tool scopes, checkpoint/rewind rules, and trace ownership. It must execute at least the demo path over prepared retrieval/extraction contracts; prose-only graph contracts do not satisfy Phase 1.
- Minimal runnable diagnostic Streamlit surface exposing state, trace, artifacts, index readiness, feedback/fix requests, and source rejection details. Visual polish is explicitly secondary to data relevance, Qdrant readiness, and deterministic extraction correctness.
- Executable golden-case data relevance evaluation that checks source-family relevance, top-candidate relevance, source rejection reasons, Qdrant/dense status, coverage evidence, deterministic extraction evidence, no-data honesty, and trace completeness.
- Final implementation decision package documenting what is accepted, what remains risky, and what must be verified before demo.
- Architecture growth map explaining how the Phase 1 slice expands into the full `ARCHITECTURE_STACK.md` design.

### Validation

- [x] Local data and CKAN access paths are documented with bounded, reproducible commands.
- [x] The source-card corpus and Qdrant embedding/search collection are built or explicitly gated by missing credentials, with a manifest that records provider, model URI, dimensions, chunk counts, hashes, collection name, Qdrant mode/path or URL, and local artifact paths.
- [x] Long-running embedding/indexing work starts as soon as the source-card corpus is ready; orchestration, UI, and extraction work proceeds in parallel while it runs.
- [x] No numeric claim is produced from LLM memory; numeric data comes only from deterministic code or trusted source adapters.
- [x] Retrieval and extraction decisions are backed by artifacts, not only prose.
- [x] Data relevance evaluation runs against golden cases and records pass/fail/gated status for source selection, source rejection, Qdrant/dense status, coverage, extraction, no-data, and trace evidence.
- [x] The visible trace contract shows selected sources, rejected sources, coverage checks, extraction plans, and no-data/gated reasoning.
- [x] Representative Phase 1 diagnostic paths run with trace/artifacts or explicit gates. This is accepted only as infrastructure evidence; Phase 2 acceptance requires all 20 golden cases to reach correct terminal outcomes.
- [x] `requirements.txt` and run/test commands reproduce the implemented slices.
- [x] Phase summaries exist for completed plans before the phase is marked complete.
- [x] The final decision package identifies extension seams and deferred full-stack capabilities without treating them as discarded scope.

## Phase 2: Full Jury MVP (`02-jury-mvp`)

**Canonical directory:** `.planning/phases/02-jury-mvp`

**Status:** Planned; ready for `$gsd-execute-phase 02`.

**Why this phase exists:** Phase 1 is accepted only as infrastructure. The acceptance report `.planning/phases/01-data-architecture-research/phase1-test-acceptance.md` shows the current system is not a functional MVP: pytest is 26/27, demo readiness is blocked/stale, dense retrieval is gated for all 20 golden cases, extraction is probe-level, data relevance eval is 0 passed / 20 gated, and the current Streamlit UI is diagnostic rather than a jury UI.

**Goal:** Build the full source-bound DataAgent MVP that can be shown to the jury: a user enters a natural-language economic query in Streamlit and the UI runs the real workflow

`User query → Supervisor → Intent Analyst → Research Designer / Direct path → FedStat/WB/CKAN Scouts → Coverage & Schema → Extraction Planner → Deterministic Tools → Methodology Critic → Visualization → Narrator → answer + dataset + script + sources + trace`.

**Non-negotiable acceptance target:** all 20 golden cases must reach a correct terminal outcome. A correct terminal outcome is one of:

- `passed`: source selection is relevant, coverage is checked, deterministic extraction produced the required data, answer is source-bound, dataset/script/artifacts are available, and trace is visible.
- `needs_clarification`: the request is genuinely ambiguous and the system asks a specific useful question instead of pretending to answer.
- `not_found`: the system proves that available/trusted sources do not contain the requested data and explains checked/rejected sources.

The following are not acceptable final outcomes for golden cases: `gated`, `stale`, `skipped_with_reason`, `no_candidate`, `final_answer.status=ok` while coverage/extraction is gated, unsupported numeric claims, or UI-only demo paths that bypass the evaluated workflow.

**Phase 2 boundary:** This phase may replace the Phase 1 diagnostic shell with a real product UI and may refactor the workflow runtime, but it must preserve source-bound invariants, full prepared-data artifacts, traceability, and deterministic extraction. It should not merge stale workstream branches that delete Phase 1 evidence or replace real artifacts with unverified stubs.

**Remote workstream note:** `origin/workstream-1/core-integration` contains useful architectural ideas for a LangGraph skeleton and typed contracts, but it is not directly mergeable into the current branch. It deletes Phase 1 artifacts/tests/scripts, rewinds `.planning` to a pre-execution state, includes stub extraction/scout behavior, and regresses the verified Yandex API base URL/auth header. Treat it as reference material only unless individual pieces are ported and verified against the Phase 2 acceptance gates.

**Covers:** all v1 requirements that are still pending or only infrastructure-level after Phase 1, especially ART-01..06, RBST-01..03, UI-01..04, ENG-01..04, and the functional versions of NLU/SRCH/DATA requirements across all golden cases.

**Plans:** 10 plans

### Plans

- [ ] `02-01-PLAN.md` — Response/status/artifact contract and shared workflow service interface
- [ ] `02-09-PLAN.md` — Operational Qdrant server promotion, population, and readiness evidence
- [ ] `02-02-PLAN.md` — Source retrieval ranking hardening and all-20 retrieval evidence
- [ ] `02-03-PLAN.md` — FedStat and World Bank deterministic extraction adapters
- [ ] `02-04-PLAN.md` — CKAN promotion/extraction, source scouts, coverage, and safe extraction planning nodes
- [ ] `02-10-PLAN.md` — All-20 golden coverage/extraction matrix over Phase 1 cards and dumps
- [ ] `02-05-PLAN.md` — LangGraph workflow runtime through extraction with explicit finalization pending
- [ ] `02-06-PLAN.md` — Methodology critic, visualization, narrator, final service response, and clarification follow-up
- [ ] `02-07-PLAN.md` — Matrix-backed all-20 golden acceptance eval and strict demo readiness gate
- [ ] `02-08-PLAN.md` — Streamlit workflow/clarification surface, reproducibility docs, and manual UAT

### Required Capabilities

- Real Streamlit jury UI where query submission invokes the same workflow used by tests/evals.
- Real workflow runtime with explicit node artifacts for every architecture role.
- Separate source scouts for FedStat, World Bank, and CKAN, with selected and rejected source cards.
- Ranking good enough that direct indicator requests beat weak contextual matches.
- Coverage preview that checks periods, geographies, units, frequency, missing values, and source-specific risks before extraction.
- Deterministic extraction for FedStat wide Parquet, World Bank long Parquet, and promoted CKAN resources where cases require them.
- Dataset export plus reproducibility script for accepted answers.
- Methodology critic that blocks or repairs bad outputs; final answer status must match coverage/extraction truth.
- Visualization generated from `DatasetArtifact`, not from free-form LLM text.
- No numeric value outside deterministic dataset/tool artifacts.
- All 20 golden cases evaluated with machine-readable acceptance output.

### Validation

- [ ] `python3 -m pytest -q` passes.
- [ ] Golden-case eval covers all 20 cases and records no unacceptable final states.
- [ ] Demo readiness is `ready`, not `blocked`, `stale`, or `gated`.
- [ ] UI can run at `http://localhost:8501` and execute the real workflow from user input.
- [ ] Each passed case has sources, coverage, deterministic dataset, generated script, answer, and trace.
- [ ] Each `needs_clarification` or `not_found` case has explicit evidence and is not counted as a hidden failure.
- [ ] All Phase 2 decisions and limitations are recorded before jury-demo readiness is claimed.

---

**Total active phases:** 2  
**Total v1 requirements:** 27  
**Coverage:** 100% mapped; functional acceptance deferred to Phase 2  
**Phase 1 status:** accepted as infrastructure, not product MVP  
**Phase 2 status:** ready for discussion  

---
*Last updated: 2026-05-10 — Phase 2 explicitly added after Phase 1 test acceptance*
