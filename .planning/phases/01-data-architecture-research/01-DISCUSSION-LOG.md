# Phase 1: Исследование данных и вариантов реализации - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-09
**Phase:** 1-Исследование данных и вариантов реализации
**Areas discussed:** architecture status, source scope, retrieval, deterministic extraction, orchestration, model choice, CKAN role, test cases, output shape, success criterion

---

## Architecture Stack Status

| Option | Description | Selected |
|--------|-------------|----------|
| Treat `.planning/ARCHITECTURE_STACK.md` as target stack | Phase 1 validates risks inside the selected stack. | yes |
| Treat it as strong hypothesis | Compare with alternatives before locking. | |
| Treat it as research note | No obligation to follow it. | |

**User's choice:** Treat `.planning/ARCHITECTURE_STACK.md` as the target stack.
**Notes:** User explicitly wants implementation discussion to start from this architecture.

---

## First MVP Source Scope

| Option | Description | Selected |
|--------|-------------|----------|
| World Bank first | Cleaner format, fastest end-to-end. | |
| FedStat first | Harder and more important for Russian statistics. | |
| FedStat + World Bank + CKAN from start | Broader, more ambitious, slower. | yes |

**User's choice:** FedStat + World Bank + CKAN from the start.
**Notes:** This changes Phase 1 from a narrow baseline into a full-source architecture research phase.

---

## Metadata Retrieval

| Option | Description | Selected |
|--------|-------------|----------|
| Simple lexical baseline | DuckDB/SQLite FTS and keyword matching only. | |
| Minimal hybrid | Lexical + embeddings + rerank in limited form. | |
| Full architecture stack | Follow `.planning/ARCHITECTURE_STACK.md` fully. | yes |

**User's choice:** Full implementation/research per `.planning/ARCHITECTURE_STACK.md`.
**Notes:** Retrieval should include lexical BM25/FTS, dense embeddings, reranking, source cards, evidence bundles, and rejection reasons where feasible.

---

## Deterministic Extraction

| Option | Description | Selected |
|--------|-------------|----------|
| SQL-first baseline | DuckDB first, adapters only as needed. | |
| pandas-first | Faster to write simple scripts. | |
| Full architecture stack | Follow `.planning/ARCHITECTURE_STACK.md` fully. | yes |

**User's choice:** Full implementation/research per `.planning/ARCHITECTURE_STACK.md`.
**Notes:** DuckDB, PyArrow, Polars, FedStat normalizer, World Bank adapter, CKAN path, coverage preview, and canonical long-format should be considered.

---

## LangGraph Orchestration

| Option | Description | Selected |
|--------|-------------|----------|
| Schemas/functions only | No graph skeleton in Phase 1. | |
| Minimal graph skeleton | Intent -> Scout -> Coverage -> Extraction plan -> Critic. | |
| Full architecture stack | Follow `.planning/ARCHITECTURE_STACK.md` fully. | yes |

**User's choice:** Full implementation/research per `.planning/ARCHITECTURE_STACK.md`.
**Notes:** Target is a hierarchical supervisor with typed artifacts and specialist agents.

---

## LLM / Model Choice

| Option | Description | Selected |
|--------|-------------|----------|
| Use smoke-tested DeepSeek 3.2 | Avoid spending time on model comparison. | |
| Compare DeepSeek/Qwen/YandexGPT now | Benchmark multiple models in Phase 1. | |
| Target Qwen per stack | Test alternatives later. | yes |

**User's choice:** Target Qwen per architecture stack; benchmark alternatives later.
**Notes:** DeepSeek was smoke-tested, but the architecture target remains Qwen/Yandex AI Studio.

---

## CKAN Role

| Option | Description | Selected |
|--------|-------------|----------|
| Discovery/freshness only | Prefer local files for data. | |
| First-class source | CKAN is equal with FedStat and World Bank. | yes |
| Research only | Do not include in prototype path yet. | |

**User's choice:** CKAN is a first-class source.
**Notes:** Planner should include CKAN package/resource search and compressed source candidate handling.

---

## Test Cases

| Option | Description | Selected |
|--------|-------------|----------|
| 5-8 golden prompts | Smaller smoke/eval set. | |
| 15-20 task-style tests | Broader test-case set from task expectations. | yes |
| 2-3 smoke tests | Minimal validation only. | |

**User's choice:** Prepare 15-20 test cases.
**Notes:** Include simple, comparative, research, derived metric, ambiguous, and no-data cases.

---

## Phase 1 Output Shape

| Option | Description | Selected |
|--------|-------------|----------|
| Research report only | Documentation and recommendation. | |
| Research report + executable spikes + trade-offs | Evidence-backed planning package. | yes |
| Near-complete MVP skeleton | Larger implementation push in Phase 1. | |

**User's choice:** Research report plus executable spikes and trade-off tables.
**Notes:** Spikes should inform Phase 2; they should not silently become final production decisions.

---

## Phase 2 Recommendation Criterion

| Option | Description | Selected |
|--------|-------------|----------|
| Fastest end-to-end demo | Prioritize speed. | |
| Most reliable source-bound extraction | Prioritize correctness above demo quality. | |
| Strongest multi-agent trace/UI wow-effect | Prioritize visible agent workflow and transparency. | yes |

**User's choice:** Strongest multi-agent trace/UI wow-effect.
**Notes:** Source-bound reliability remains a non-negotiable constraint, but among viable paths the preferred MVP is the one that best demonstrates the hierarchical DataAgent and transparent trace.

---

## the agent's Discretion

- Exact spike ordering.
- Exact module/file boundaries.
- Whether dense embeddings are local or Yandex AI Studio first.
- Exact eval harness implementation.

## Deferred Ideas

- Broad model benchmark against DeepSeek/YandexGPT is deferred until later.
- Final production MVP implementation remains Phase 2.
