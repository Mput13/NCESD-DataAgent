# Phase 1 Main Artifact Comparison

**Compared:** 2026-05-09
**Working branch:** `codex/phase-1-discuss-clean`
**Source branch:** `main`
**Authority rule:** `01-CONTEXT.md` wins over all pre-discussion research and plan artifacts.

## Inputs Compared

- Current source of decisions: `.planning/phases/01-data-architecture-research/01-CONTEXT.md`
- Old research material: `main:.planning/phases/01-issledovanie-dannyh-i-variantov-realizacii/01-RESEARCH.md`
- Old plans: `main:.planning/phases/01-issledovanie-dannyh-i-variantov-realizacii/01-01-PLAN.md`, `01-02-PLAN.md`, `01-03-PLAN.md`
- Old roadmap change: `main:.planning/ROADMAP.md` added a "Plans: 3 plans" block for the pre-context plans

## Comparison Matrix

| Area | Matches CONTEXT.md and can transfer | Conflicts with CONTEXT.md and must be rewritten | Useful as recommendation/evidence only | Remaining gaps after discuss |
|---|---|---|---|---|
| Phase boundary | Old plans correctly treated Phase 1 as evidence/research before final Phase 2 decisions. | Old research says "Phase 1 should plan discovery work, not a full prototype" and warns against full LangGraph now; CONTEXT requires full target-stack research/spikes. | Keep the "recommendation, not accepted Phase 2 decision" language. | Plans must define how much executable spike code is enough to validate "full architecture" without shipping Phase 2. |
| Source scope | Old Plan 02 included FedStat, World Bank, and CKAN source cards. | Old research positioned CKAN mainly as live discovery/provenance/freshness, while CONTEXT says CKAN is first-class for discovery and data access. | Reuse bounded CKAN `package_search`/`package_show` limits, candidate-card compression, and failure logging. | Need plan tasks for CKAN resource inspection/download/cache path, not just package metadata. |
| Retrieval | Old plans used source cards, retrieval eval CSV, rejection reasons, and metadata-only cards. | Old Plan 02 excludes embedding APIs and treats embeddings/File Search only as markdown comparison; CONTEXT requires full hybrid retrieval per architecture stack where feasible. | Keep substring/RapidFuzz/FTS as baselines, but add dense embeddings and rerank evidence rather than treating them as optional prose. | Need concrete acceptance criteria for lexical + dense + rerank outputs and fallback behavior when API credentials are absent. |
| Extraction | Old plans included coverage preview, selected FedStat/WB probes, and no raw numeric answer prose. | Old research preferred small selected normalizer probes and "DuckDB vs pandas" exploration; CONTEXT already locks DuckDB SQL-first with PyArrow/adapters/Polars where useful. | Reuse bounded inventory/probe scripts, wide FedStat cautions, WB null coverage checks, and "skip huge 61028 full reads" guardrail. | Need full-stack normalizer/adapter strategy artifacts, not just one-off probes. |
| Orchestration | Old Plan 03 included structured NLU eval and Phase 2 decision brief. | Old research says LangGraph later if selected; CONTEXT locks LangGraph hierarchical supervisor research/planning in Phase 1. | Reuse typed artifacts, IntentFrame, SourceCandidateCard, CoverageReport, and no-data policy ideas. | Need a plan for LangGraph skeleton or graph design artifact covering supervisor, scouts, coverage, planner, critic, narrator, visualization, trace. |
| LLM/model | Old Plan 03 evaluated Yandex NLU and documented endpoint/header/model behavior. | Old plan defaults to DeepSeek V3.2; CONTEXT targets Qwen 3.6 via Yandex AI Studio and defers broad model benchmarking. | Reuse endpoint/auth smoke-test checks, skipped-missing-env behavior, and structured output validation pattern. | Need Qwen-targeted config path, with DeepSeek as fallback/evidence rather than the default locked model. |
| Test cases | Old Plan 01 created 6-8 golden cases. | CONTEXT requires the broader 15-20 task-style test set. | Reuse field schema for cases and categories: simple, comparative, research, derived_metric, ambiguous, no_data. | Need acceptance criteria for 15-20 cases and coverage across FedStat, World Bank, CKAN, no-data, ambiguity, trace. |
| UI/trace | Old plans mention traceability and Streamlit later, but do not strongly plan UI/state-machine wow-effect. | CONTEXT makes multi-agent trace and UI transparency the dominant Phase 2 recommendation criterion. | Reuse source rejection logs and artifacts as UI-ready trace inputs. | Need explicit research/spike plan for TraceEvent schema, state-machine visualization, artifact panels, feedback/fix request path, without final Phase 2 UI decisions. |
| Roadmap edits | Old roadmap "Plans: 3 plans" block is useful once new plans exist. | Old block points to wrong pre-context plan names and directory. | Recreate roadmap plan summary only after fresh plans pass checker. | Need ensure roadmap summary references current `01-data-architecture-research` plans. |

## Transfer Guidance For Fresh Plan

- Preserve old three-wave shape only as a starting structure: foundation, retrieval/extraction, NLU/recommendation.
- Expand or rewrite waves to honor CONTEXT decisions: full target stack, 15-20 cases, first-class CKAN, Qwen target, LangGraph research/skeleton, and trace/UI demonstration value.
- Every plan must read `.planning/phases/01-data-architecture-research/01-CONTEXT.md`.
- Old paths under `01-issledovanie-dannyh-i-variantov-realizacii` must not be reused in the new branch.
- Any sentence that says "not accepted Phase 2 decision" is still valuable; any sentence that weakens locked Phase 1 architecture decisions is not.

## Rejected From Old Artifacts

- "Full LangGraph implementation later if selected" conflicts with D-13 and D-14.
- "Do not call embedding APIs in this plan" conflicts with D-06 when credentials/access allow dense retrieval.
- "5-8 MVP prompts" conflicts with D-19.
- Defaulting to DeepSeek V3.2 conflicts with D-16; it may remain a fallback or historical smoke-test note only.
- Treating CKAN primarily as freshness/provenance conflicts with D-04.

## Useful Old Ideas To Carry Forward

- Requirements map with mandatory/emulatable/bonus/deferred classification.
- Data inventory script using bounded archive metadata reads and CKAN `rows=0`.
- SourceCandidateCard schema with provenance, availability flags, quality flags, match mode, and no numeric table values.
- Retrieval eval CSV and extraction coverage probe artifacts.
- NLU skipped-missing-env behavior and Pydantic validation of structured outputs.
- Phase 2 recommendation and decision brief language that keeps recommendations non-binding.

