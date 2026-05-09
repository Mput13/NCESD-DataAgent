# Roadmap: DataAgent

**Created:** 2026-05-08  
**Reset:** 2026-05-10  
**Granularity:** Single active phase for the current milestone  
**Core Value:** Опора на факты — каждая цифра со ссылкой, числа извлекает код

---

## Phase 1: Data Architecture Implementation (`01-data-architecture-research`)

**Canonical directory:** `.planning/phases/01-data-architecture-research`

**Naming note:** the slug keeps `research` for continuity with existing GSD artifacts. In this roadmap, Phase 1 is not prose-only research. It is the single implementation-oriented phase for the current milestone: build the MVP architecture through small, verifiable plans, deterministic source adapters/spikes, traceable artifacts, and an end-to-end demo path.

**Goal:** Implement and validate the DataAgent architecture enough to demonstrate the core product loop: natural-language request → structured intent/research design → source discovery over FedStat, World Bank, and CKAN → deterministic coverage/extraction path → source-bound artifacts → visible Streamlit trace and feedback loop.

**Boundary:** Phase 1 may create production-bound code, scripts, tests, and UI contracts. It must not silently accept unverified spikes as complete implementation. Every implemented slice needs explicit evidence, deterministic verification, and a summary artifact.

**Covers:** NLU-01..04, SRCH-01..04, DATA-01..05, ART-01..06, RBST-01..04, UI-01..04, ENG-01..04

**Execution model:** single-track GSD execution. Do not split work into Core/Data/UI owners or parallel human workstreams unless the roadmap is explicitly changed.

### Plans

- [ ] `01-01-PLAN.md` — Requirements map, 15-20 golden cases, and eval rubric
- [ ] `01-02-PLAN.md` — Deterministic data inventory and typed source-card builders
- [ ] `01-03-PLAN.md` — Hybrid retrieval comparison and deterministic extraction probes
- [ ] `01-04-PLAN.md` — Qwen/Yandex client hardening and LangGraph contract/architecture slice
- [ ] `01-05-PLAN.md` — Streamlit trace/UI demo contract and implementation decision package

### Deliverables

- Requirement-to-artifact map covering all v1 requirements.
- 15-20 test cases across simple, comparative, research, derived metric, ambiguous, and no-data requests.
- Deterministic source inventory for local dumps and bounded CKAN package/resource access.
- Shared source-card/evidence contracts for FedStat, World Bank, and CKAN.
- Retrieval comparison with lexical, dense, rerank, and credential-aware fallback evidence.
- DuckDB SQL-first extraction probes and adapter strategy for FedStat, World Bank, and CKAN.
- Hardened Yandex AI Studio/Qwen integration notes and runnable gated checks.
- LangGraph architecture contract or skeleton with typed artifacts and trace ownership.
- Streamlit-first trace/UI contract exposing state, trace, artifacts, and feedback/fix requests.
- Final implementation decision package documenting what is accepted, what remains risky, and what must be verified before demo.

### Validation

- [ ] Local data and CKAN access paths are documented with bounded, reproducible commands.
- [ ] No numeric claim is produced from LLM memory; numeric data comes only from deterministic code or trusted source adapters.
- [ ] Retrieval and extraction decisions are backed by artifacts, not only prose.
- [ ] The visible trace shows selected sources, rejected sources, coverage checks, extraction plans, and no-data reasoning.
- [ ] `requirements.txt` and run/test commands reproduce the implemented slices.
- [ ] Phase summaries exist for completed plans before the phase is marked complete.

---

**Total active phases:** 1  
**Total v1 requirements:** 27  
**Coverage:** 100%

---
*Last updated: 2026-05-10 — reset to one canonical implementation-oriented Phase 1*
