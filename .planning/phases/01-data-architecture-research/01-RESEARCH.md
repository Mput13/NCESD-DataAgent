# Phase 1 Research Baseline

**Phase:** `01-data-architecture-research`  
**Updated:** 2026-05-10  
**Purpose:** Preserve the useful implementation research direction without carrying forward obsolete multi-phase or workstream assumptions.

## Summary

Phase 1 should implement the DataAgent MVP architecture through small, verifiable slices. The phase should produce runnable code and scripts where the plans require them, but every slice must remain source-bound and evidence-backed.

The expected result is a scalable seed, not a throwaway demo. If Phase 1 implements only a representative subset of the full architecture, it must still preserve the interfaces needed to grow into the complete `.planning/ARCHITECTURE_STACK.md` design.

The key design stance is:

- LLM handles intent, research design, planning, narration, and critique.
- Deterministic tools handle data discovery, coverage preview, extraction, joins, aggregations, and numeric values.
- Trace artifacts must make every source selection, rejection, coverage check, extraction decision, and no-data result visible.

## Target Stack

- **LLM:** Qwen via Yandex AI Studio OpenAI-compatible API.
- **Orchestration:** LangGraph-style supervisor with typed artifacts.
- **Sources:** FedStat local dump, World Bank local dump, and NSED CKAN package/resource API.
- **Retrieval:** lexical baseline plus dense/rerank path when credentials or local models allow; skipped dense/rerank checks must be recorded explicitly.
- **Extraction:** DuckDB SQL-first, with PyArrow/source adapters for normalization and Polars only where useful.
- **UI:** Streamlit-first trace/artifact surface.
- **Validation:** pytest or scriptable checks over 15-20 golden cases.

## Required Evidence

- Requirements map for all v1 requirements.
- Golden cases covering simple, comparative, research, derived metric, ambiguous, and no-data requests.
- Deterministic source inventory and bounded CKAN access notes.
- Source cards/evidence bundles with provenance, units, periods, geography, availability, and rejection reasons.
- Retrieval comparison and eval CSV.
- Extraction probes for FedStat, World Bank, and CKAN.
- Yandex/Qwen gated checks with credential-aware skip notes.
- LangGraph contract or skeleton with canonical trace event ownership.
- Streamlit trace/UI contract and implementation decision package.
- Architecture growth map: what is implemented now, what is intentionally deferred, and which extension seams make the full target architecture reachable.

## Extension Seams To Preserve

- **Source adapters:** FedStat, World Bank, and CKAN should share contracts while keeping source-specific normalization isolated.
- **Retrieval providers:** lexical, dense, and rerank paths should sit behind interfaces so local/Yandex/fallback providers can change.
- **Workflow artifacts:** intent, design, evidence, coverage, extraction, critique, narration, visualization, and trace objects should be typed and reusable across graph and UI layers.
- **Deterministic tools:** numeric extraction should be a tool library, not embedded in LLM prompts or UI code.
- **Trace events:** the same canonical trace should support Streamlit display now and replay/session history later.
- **UI view models:** Streamlit should adapt workflow artifacts for display without owning the core schema.

## Known Pitfalls

- Treating CKAN as general web search. CKAN is a trusted bounded catalog API only.
- Letting LLM produce numeric facts. Numeric values must come from deterministic code.
- Building a broad skeleton before the plan-specific evidence artifacts exist.
- Duplicating trace schemas between workflow and UI.
- Adding dependencies without updating `requirements.txt` and verification commands.
- Reintroducing owner-specific workstream docs.
- Hardcoding a narrow demo path in a way that blocks full `ARCHITECTURE_STACK.md` expansion.

## Open Questions For Execution

- Which retrieval path is feasible first: local lexical/FTS only, local embeddings, or Yandex embeddings?
- Which FedStat tables are small and representative enough for normalizer proof?
- Which CKAN resources are safe to inspect/download within bounded limits?
- How much LangGraph code is needed for an honest trace demo before full data adapters are complete?
- Which deferred capabilities are required for the next roadmap phase versus acceptable post-demo hardening?

## Sources To Read First

- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`
- `.planning/ARCHITECTURE_STACK.md`
- `.planning/DATA_REPORT.md`
- `.planning/YANDEX_AI_STUDIO_RESEARCH.md`
- `.planning/phases/01-data-architecture-research/01-CONTEXT.md`
