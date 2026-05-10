# Roadmap: DataAgent

**Created:** 2026-05-08  
**Reset:** 2026-05-10  
**Granularity:** Single active phase for the current milestone  
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

- [ ] `01-01-PLAN.md` — Requirements map, 15-20 golden cases, and eval rubric
- [ ] `01-02-PLAN.md` — Prepared-data contract, source-card builders, and embedding corpus format
- [ ] `01-03-PLAN.md` — Materialized embedding/search index and retrieval evaluation
- [ ] `01-04-PLAN.md` — Qwen/Yandex, runnable LangGraph narrow flow, deterministic extraction, data-relevance eval, and diagnostic UI models while indexing runs
- [ ] `01-05-PLAN.md` — Runnable readiness/demo package over prepared data, Qdrant status, relevance/extraction evidence, and minimal diagnostic Streamlit surface

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

- [ ] Local data and CKAN access paths are documented with bounded, reproducible commands.
- [ ] The source-card corpus and Qdrant embedding/search collection are built or explicitly gated by missing credentials, with a manifest that records provider, model URI, dimensions, chunk counts, hashes, collection name, Qdrant mode/path or URL, and local artifact paths.
- [ ] Long-running embedding/indexing work starts as soon as the source-card corpus is ready; orchestration, UI, and extraction work proceeds in parallel while it runs.
- [ ] No numeric claim is produced from LLM memory; numeric data comes only from deterministic code or trusted source adapters.
- [ ] Retrieval and extraction decisions are backed by artifacts, not only prose.
- [ ] Data relevance evaluation runs against golden cases and records pass/fail/gated status for source selection, source rejection, Qdrant/dense status, coverage, extraction, no-data, and trace evidence.
- [ ] The visible trace shows selected sources, rejected sources, coverage checks, extraction plans, and no-data reasoning.
- [ ] At least 2-3 representative golden cases run through the integrated demo path with trace/artifacts, or block on explicit credential/data gates with recorded evidence.
- [ ] `requirements.txt` and run/test commands reproduce the implemented slices.
- [ ] Phase summaries exist for completed plans before the phase is marked complete.
- [ ] The final decision package identifies extension seams and deferred full-stack capabilities without treating them as discarded scope.

---

**Total active phases:** 1  
**Total v1 requirements:** 27  
**Coverage:** 100%

---
*Last updated: 2026-05-10 — reset to one canonical implementation-oriented Phase 1*
