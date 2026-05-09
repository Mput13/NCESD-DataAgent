# Phase 1: Исследование данных и вариантов реализации - Context

**Gathered:** 2026-05-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 delivers a full evidence-backed implementation research package for DataAgent: requirements map, data map, source/retrieval/extraction comparisons, model/orchestration validation plan, executable spikes where useful, and a recommended MVP scope for Phase 2. It does not ship the final MVP, but it must validate the target architecture deeply enough that Phase 2 can implement without reopening core stack decisions.

The phase is anchored in `.planning/ARCHITECTURE_STACK.md`. That document is treated as the target stack, not merely a loose research note.

</domain>

<decisions>
## Implementation Decisions

### Architecture Stack Status
- **D-01:** Treat `.planning/ARCHITECTURE_STACK.md` as the target architecture for Phase 1 research and planning.
- **D-02:** Phase 1 should validate risks and implementation details inside that stack, not compare against a radically simpler architecture unless a blocker is discovered.

### Source Scope
- **D-03:** FedStat, World Bank, and CKAN are all in scope from the start.
- **D-04:** CKAN is a first-class source path for discovery and data access, not just a bonus freshness check.
- **D-05:** Local dumps remain important for speed and reproducibility, but Phase 1 must research how live CKAN package/resource discovery integrates into the same source-bound workflow.

### Retrieval and Catalog
- **D-06:** Implement/research retrieval fully according to `.planning/ARCHITECTURE_STACK.md`: lexical BM25/FTS plus dense embeddings and reranking where feasible.
- **D-07:** Metadata indexing should use compact source cards and evidence bundles rather than loading raw CKAN/API/table responses into LLM context.
- **D-08:** Retrieval must support exact code/title matches, Russian and English lexical search, semantic matches, proxy candidates, methodology matches, and rejection reasons.

### Deterministic Extraction
- **D-09:** Implement/research data extraction fully according to `.planning/ARCHITECTURE_STACK.md`: DuckDB SQL-first with PyArrow/source adapters for normalization and Polars where useful.
- **D-10:** FedStat requires a real normalizer strategy for wide Parquet tables, including first-row headers, dimensions, period columns, units, source URLs, and coverage preview.
- **D-11:** World Bank requires a real adapter strategy for indicator cards, countries/aggregates, coverage by country/period, and canonical long-format output.
- **D-12:** LLMs may choose plans and explain results, but numbers must come only from deterministic tools.

### Orchestration and Agents
- **D-13:** Implement/research the orchestration fully according to `.planning/ARCHITECTURE_STACK.md`: LangGraph hierarchical supervisor with typed artifacts.
- **D-14:** The minimum target graph for research/planning is Lead DataAgent/Supervisor, Intent/Triage, Research Designer, FedStat Scout, World Bank Scout, CKAN Scout, Coverage & Schema, Extraction Planner, deterministic tools, Methodology Critic, Narrator, and Visualization where relevant.
- **D-15:** Simple direct lookups should be able to skip unnecessary agents, but complex research queries should use parallel source scouts and critic loops.

### LLM Choice
- **D-16:** Use Qwen 3.6 via Yandex AI Studio as the target model per architecture stack.
- **D-17:** Do not spend Phase 1 primarily on broad model benchmarking. DeepSeek/YandexGPT comparisons can be tested later if needed.
- **D-18:** Yandex AI Studio integration should remain part of the target: OpenAI-compatible API, structured outputs/tool calling, and optional native File Search / Vector Store / MCP Hub where they accelerate the architecture.

### Test Cases and Evaluation
- **D-19:** Phase 1 should prepare the broader 15-20 test-case set from the task, not only a small 5-8 smoke set.
- **D-20:** Test coverage should include simple lookup, comparative query, research query, derived metric, ambiguous query, and no-data query.
- **D-21:** Evaluation must measure not just final answer text, but retrieval quality, coverage preview, source rejection, deterministic extraction, and trace completeness.

### Phase 1 Output Shape
- **D-22:** Phase 1 output should include research report(s), executable spikes, and trade-off tables.
- **D-23:** Spikes are evidence for planning and MVP selection; they are not automatically accepted as production implementation without explicit Phase 2 planning.

### Success Criterion Priority
- **D-24:** The main recommendation criterion for Phase 2 is maximum demonstration value from multi-agent trace and UI transparency.
- **D-25:** Reliability remains non-negotiable: every numeric value must be source-bound and reproducible, but among reliable options the preferred path is the one with the strongest visible agent workflow and trace.

### the agent's Discretion
- The planner may choose exact spike ordering, file/module boundaries, schemas, and test harness structure.
- The planner may decide whether to implement dense embeddings locally or through Yandex AI Studio first, as long as the full architecture target is respected.
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
- Repository is still a thin scaffold. There are no implemented data adapters, catalog builders, retrieval modules, LangGraph workflow, Streamlit UI, eval harness, or tests yet.
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
- The user selected CKAN as an equal first-class source, not a secondary API.
- The user wants the broader 15-20 task test-case set prepared in Phase 1.
- The user selected multi-agent trace and transparent UI wow-effect as the dominant Phase 2 recommendation criterion, while preserving source-bound reliability.

</specifics>

<deferred>
## Deferred Ideas

- Broad DeepSeek/YandexGPT/Qwen benchmarking is deferred; Phase 1 targets Qwen 3.6 per architecture stack and can test alternatives later if needed.
- Final production MVP implementation remains Phase 2, after Phase 1 research/spikes and explicit planning.

</deferred>

---

*Phase: 01-data-architecture-research*
*Context gathered: 2026-05-09*
