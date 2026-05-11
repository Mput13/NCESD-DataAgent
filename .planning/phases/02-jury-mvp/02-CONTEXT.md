# Phase 2: Full Jury MVP - Context

**Gathered:** 2026-05-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 delivers the full working jury prototype for DataAgent. Phase 1 is accepted only as infrastructure: it produced source-card/catalog/corpus artifacts, Qdrant/Yandex embedding build paths, typed workflow artifacts, eval scaffolding, extraction probes, and a diagnostic Streamlit shell, but it did not produce a functional end-user MVP.

The Phase 2 boundary is the full source-bound workflow described in `.planning/ARCHITECTURE_STACK.md`:

```text
User query
-> Supervisor
-> Intent Analyst
-> Research Designer / Direct path
-> FedStat/WB/CKAN Scouts
-> Coverage & Schema
-> Extraction Planner
-> Deterministic Tools
-> Methodology Critic
-> Visualization
-> Narrator
-> answer + dataset + script + sources + trace
```

The user explicitly clarified that Phase 2 must implement the full functionality described in `.planning/ARCHITECTURE_STACK.md`. This is not a small demo subset, not a prototype excuse, and not a reduced MVP. The architecture stack is the minimum baseline for the jury prototype; later work may improve it, but Phase 2 planning must not lower the target by arguing that the system is "only a prototype" or "only an MVP".

Phase 2 final acceptance targets all 20 golden cases. Staged implementation order is allowed, but final Phase 2 acceptance requires every golden case to reach a correct terminal outcome: `passed`, `needs_clarification`, or `not_found`.

Invalid final states for Phase 2 are: `gated`, `stale`, `skipped_with_reason`, `no_candidate`, `final_answer.status=ok` while coverage or extraction is gated, unsupported numeric claims, and any UI-only path that bypasses the evaluated workflow.

</domain>

<decisions>
## Implementation Decisions

### Scope and Acceptance Bar

- **D-01:** Phase 2 implements the full `.planning/ARCHITECTURE_STACK.md` capability set as the minimum jury prototype.
- **D-02:** Do not simplify Phase 2 into a "representative" 2-3 case demo. The final acceptance set is all 20 golden cases in `.planning/phases/01-data-architecture-research/golden-cases.yaml`.
- **D-03:** The planner decides implementation waves autonomously. Preferred execution style is fast, parallelizable workstreams where independent parts can run at the same time.
- **D-03A:** Plans may stage implementation waves, but every wave must preserve the final full-functionality target and must not redefine success downward.
- **D-04:** Phase 1 infrastructure artifacts are reused and upgraded; they are not evidence that product behavior is complete.
- **D-05:** Current `gated`, `stale`, `skipped_with_reason`, `no_candidate`, or probe-only outputs are accepted only as diagnostic Phase 1 evidence, never as Phase 2 final outcomes.

### Terminal Status Semantics

- **D-06:** Valid final golden-case terminal outcomes are only `passed`, `needs_clarification`, and `not_found`.
- **D-07:** `passed` means the request traverses the complete pipeline and returns an answer: relevant source selection, coverage checked, deterministic extraction completed, source-bound answer produced, dataset/script/artifacts available, visualization when relevant, and trace visible.
- **D-08:** `needs_clarification` means the request is genuinely ambiguous and the system asks a specific useful question instead of pretending to answer.
- **D-09:** `not_found` means trusted/available sources were checked and rejected with explicit evidence.
- **D-10:** `final_answer.status=ok` while coverage or extraction is gated is a bug to fix, not an acceptable partial success.

### Workflow Runtime

- **D-11:** Implement the real workflow runtime that maps to the architecture stack roles: Supervisor, Intent Analyst, Research Designer, FedStat Scout, World Bank Scout, CKAN Scout, Coverage & Schema, Extraction Planner, Deterministic Tools, Methodology Critic, Visualization, and Narrator.
- **D-12:** The current `Phase1Graph` narrow smoke runner is a seed and trace-contract reference only. Phase 2 must replace or extend it into real product execution.
- **D-13:** Use one typed workflow state object through the graph. The remote workstream `AgentState` idea may be ported selectively if it preserves current Phase 1 artifacts and tests.
- **D-14:** Simple direct lookups may skip unnecessary agents, but the implementation must still have the full architecture available for comparative, research, ambiguous, derived-metric, and no-data queries.
- **D-15:** Human-in-the-loop clarification and repair routing are in scope for Phase 2 because they are required for valid `needs_clarification` behavior and user feedback/fix requests.
- **D-15A:** Implement the full contract from `.planning/ARCHITECTURE_STACK.md`, not a simplified local substitute. This includes the complete artifact/state/trace contract needed by downstream UI and evaluation surfaces.

### Source Search and Retrieval

- **D-16:** FedStat, World Bank, and CKAN are all first-class source paths in Phase 2.
- **D-17:** CKAN is a trusted NSED catalog API, not general web search. Use bounded `package_search` / `package_show`, compressed source cards, and promoted metadata only.
- **D-18:** Qdrant remains the vector-store abstraction. Do not replace it with an ad hoc local vector path.
- **D-18A:** For Phase 2 jury/eval/workflow/UI concurrency, Qdrant Docker/server mode is the target runtime. Configure workflow, eval, and Streamlit to use one shared server through `QDRANT_URL`.
- **D-18B:** `QdrantClient(path=".local/qdrant")` embedded/local mode is acceptable only for small tests, isolated development, or explicit fallback. It is not the preferred Phase 2 runtime because it holds a storage lock per Python process, lacks normal server concurrency, starts a storage context in every process, and warns above 20,000 points; the current collection has 36,321 points.
- **D-18C:** Phase 2 plans must include a Docker/server Qdrant setup and readiness probe so parallel scouts, evals, workflow smoke runs, and Streamlit can safely query one promoted collection.
- **D-18D:** Do not make Python embedded Qdrant performance or storage locking a hidden demo risk. If server mode cannot be started, record the blocker explicitly and do not claim full jury readiness on an unsafe concurrency path.
- **D-19:** Run full embedding/Qdrant index refresh in parallel with workflow, extraction, eval, and response-contract work. Do not serialize the whole phase behind index completion if useful work can proceed independently.
- **D-19A:** Final readiness cannot remain stale or gated. The target path uses real embedding calls and a current Qdrant index/readiness artifact.
- **D-20:** Retrieval ranking must be good enough that direct indicator intents beat weak contextual matches. The known GC-001 GDP source-ranking issue is a Phase 2 blocker.
- **D-21:** Source scouts must return selected and rejected source cards with reasons, match modes, risks, units, coverage hints, and provenance links.

### Coverage and Deterministic Extraction

- **D-22:** Coverage Preview must check actual periods, geographies, units, frequency, missing values, source-specific schema risks, and alternatives before extraction.
- **D-23:** Deterministic extraction must work for FedStat wide Parquet, World Bank long Parquet, and promoted CKAN resources where golden cases require them.
- **D-24:** LLMs may classify, plan, select, critique, and narrate, but numeric values must come only from deterministic tools or trusted source adapters.
- **D-25:** Extraction Planner should select safe operations and SQL/Python templates; it must not become an unconstrained free-form code generator.
- **D-26:** Dataset exports must include dataset file, script, manifest, provenance, quality flags, and source links.

### Critic, Visualization, Narrator

- **D-27:** Methodology Critic must block or repair bad outputs before narration. It must catch unit mismatches, missing coverage, wrong aggregations, unsupported sources, and no-data dishonesty.
- **D-28:** Visualization is part of the full jury workflow when relevant. It must be generated from `DatasetArtifact`, not from LLM text.
- **D-29:** Narrator must produce different answer shapes for direct lookup, comparison, research, clarification, and not-found cases, while preserving sources, methodology, limitations, and trace.
- **D-30:** Unsupported numeric claims are hard failures even if the prose looks plausible.

### Frontend Response Contract and Streamlit Test UI

- **D-31:** Do not build a full custom frontend in Phase 2 planning unless a later explicit request changes this. Prepare a frontend-facing response format suitable for a chat-like LLM interface similar to Claude.
- **D-32:** The response contract must support message-style output plus structured blocks for answer, citations/sources, dataset artifacts, generated script, visualization spec, trace/state timeline, selected/rejected sources, coverage, extraction plan, limitations, clarification questions, not-found evidence, and feedback/fix requests.
- **D-33:** Streamlit remains a simple fast test surface. It should call the same workflow entrypoint used by tests/evals and render enough of the response contract for manual testing, but it is not the primary polished frontend deliverable.
- **D-34:** UI polish is useful only after product behavior is real. Do not spend Phase 2 effort on decorative design before source selection, coverage, extraction, eval, trace, and frontend response contract are working.

### Yandex/Qwen and Credentials

- **D-35:** Qwen via Yandex AI Studio remains the target LLM path for structured intent/planning/critic/narration.
- **D-36:** Preserve the verified Yandex chat endpoint/auth pattern from current code: `https://llm.api.cloud.yandex.net/v1` with `Authorization: Api-Key ...`.
- **D-37:** All LLM calls and embedding calls specified by the architecture stack must be real calls in the target path. "Live" means actual Yandex/Qwen and embedding API calls, not mocked responses, canned outputs, or silent deterministic substitutes.
- **D-38:** Deterministic fallback may be used only for local tests where explicitly marked, but it must not hide missing Qwen/Yandex integration in the jury path and must not be counted as final Phase 2 readiness.

### Testing and Manual Acceptance

- **D-38A:** Automatic tests and golden-case evals are required but not sufficient.
- **D-38B:** After implementation, run manual testing through the quick UI/workflow surface and incorporate user feedback from that testing before claiming Phase 2 complete.
- **D-38C:** Manual testing should verify not only final text, but the whole product behavior: pipeline traversal, trace readability, source selection/rejection, deterministic numeric provenance, dataset/script artifacts, frontend response format, clarification behavior, not-found honesty, and feedback/fix-request flow.

### Remote Workstream

- **D-39:** Do not merge `origin/workstream-1/core-integration` wholesale.
- **D-40:** Selectively port only useful ideas, such as a single workflow state, LangGraph routing, clarification loops, and contract tests.
- **D-41:** Do not port stub scouts, stub extraction, old planning state, deletion of Phase 1 evidence, or the regressed Yandex endpoint/auth behavior.

### the agent's Discretion

- The planner chooses the implementation wave order and should seek parallel work where file ownership and dependencies allow it. Fast implementation is preferred.
- The planner should run embedding/Qdrant readiness work in parallel with workflow/extraction/eval/frontend-response-contract work where possible. Final readiness still requires real LLM/embedding calls and no unresolved stale/gated critical path.
- The planner may refactor modules and schemas to support the full workflow, provided Phase 1 artifacts, source-bound invariants, and tests are preserved or deliberately migrated with evidence.
- The planner may add focused tests and eval artifacts beyond the existing suite where needed for golden-case acceptance.

</decisions>

<specifics>
## Specific Ideas

- User clarification for this discussion: "В этой фазе мы должны реализовать ПОЛНЫЙ функционал который описан в ARCHITECTURE_STACK.md. Фаза 1 была каркасом - сейчас наша задача - полностью рабочий прототип, который мы покажем жюри. Повторюсь МЫ ДЕЛАЕМ ВЕСЬ ФУНКЦИОНАЛ."
- User delegated implementation wave ordering to the planner with a preference for parallel processes and fast delivery.
- Minimum success includes complete pipeline traversal and an actual answer, not only isolated artifacts.
- User clarified that all LLM and embedding requests indicated by the stack must be real calls in the target path.
- User added a Qdrant runtime decision: local embedded Qdrant is fine for small tests, but Phase 2 should use Docker/server Qdrant via `QDRANT_URL` because the 36,321-point collection is above the local-mode warning threshold and Phase 2 will run parallel scouts, evals, UI, and workflow smoke processes.
- User wants manual testing and feedback after implementation in addition to automatic tests.
- User clarified again that the full contract from `.planning/ARCHITECTURE_STACK.md` is required and not simplified.
- User does not want a full frontend built now. Prepare a chat-like frontend response format; keep Streamlit as a simple fast testing option.
- Treat `.planning/ARCHITECTURE_STACK.md` as the minimum for Phase 2, not a future wishlist.
- Phase 2 must expose the state machine, trace, artifacts, frontend response contract, and feedback/fix requests.
- Acceptance must cover all 20 golden cases, not only a small curated demo path.
- The current top-candidate weakness for the GDP query is an example of the source ranking quality bar Phase 2 must clear.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 2 Scope and Acceptance

- `.planning/ROADMAP.md` — Phase 2 goal, required capabilities, invalid final states, and validation gates.
- `.planning/STATE.md` — current state, Phase 1 acceptance as infrastructure, Phase 2 next action, and current repository surface.
- `.planning/REQUIREMENTS.md` — v1 requirement mapping; all functional acceptance maps to Phase 2.
- `.planning/phases/02-jury-mvp/02-SEED-CONTEXT.md` — seed decisions and discussion questions that led into this context.

### Architecture and Product Contract

- `.planning/ARCHITECTURE_STACK.md` — canonical minimum architecture and technology stack for the full jury prototype.
- `.planning/PROJECT.md` — product vision, source-bound core value, constraints, and out-of-scope boundaries.
- `.planning/DATA_REPORT.md` — verified FedStat, World Bank, and NSED CKAN data structure findings.
- `.planning/ARCHITECTURE_RESEARCH.md` — rationale and alternatives behind the chosen architecture.
- `.planning/YANDEX_AI_STUDIO_RESEARCH.md` — Yandex AI Studio capabilities and prior smoke-test details.

### Phase 1 Infrastructure Evidence To Preserve

- `.planning/phases/01-data-architecture-research/01-CONTEXT.md` — locked Phase 1 architecture and source-bound decisions carried forward.
- `.planning/phases/01-data-architecture-research/phase1-test-acceptance.md` — exact Phase 1 pass/fail/gated state and why Phase 2 exists.
- `.planning/phases/01-data-architecture-research/phase1-actual-state-verification.md` — current runnable surface, known gates, Streamlit status, and embedding/index state.
- `.planning/phases/01-data-architecture-research/golden-cases.yaml` — 20-case acceptance set for Phase 2.
- `.planning/phases/01-data-architecture-research/architecture-growth-map.md` — growth path from Phase 1 infrastructure to the target architecture.
- `.planning/phases/02-jury-mvp/remote-workstream-review.md` — selective-porting rule for remote branch ideas.

### Codebase Maps

- `.planning/codebase/ARCHITECTURE.md` — current layers, target Phase 2 flow, data flow, and abstractions.
- `.planning/codebase/STACK.md` — current dependencies, runtime assumptions, and Phase 2 stack guidance.
- `.planning/codebase/STRUCTURE.md` — module layout and where to add Phase 2 code.
- `.planning/codebase/INTEGRATIONS.md` — Yandex, embeddings, Qdrant, CKAN, FedStat, and World Bank integration constraints.
- `.planning/codebase/TESTING.md` — current test strategy and known gaps.
- `.planning/codebase/CONCERNS.md` — risks to address during Phase 2 planning.

### Existing Code Seeds

- `app/artifacts/workflow_artifacts.py` — current typed artifacts; may need extension for final terminal statuses and full workflow payloads.
- `app/artifacts/source_cards.py` — source-card and embedding-document contracts.
- `app/catalog/source_catalog.py` — SQLite catalog interface over prepared source cards.
- `app/retrieval/embedding_index.py` — Yandex embedding and Qdrant index contracts.
- `app/retrieval/hybrid_retrieval.py` — lexical/dense/rerank retrieval interface and ranking work area.
- `app/data/deterministic_tools.py` — deterministic coverage, extraction, export, and visualization helpers.
- `app/workflow/graph_contract.py` — node contracts, budgets, and current `GraphState`.
- `app/workflow/run_graph.py` — current narrow graph smoke runner to replace/extend into real workflow.
- `app/ui/streamlit_app.py` — diagnostic Streamlit shell to turn into jury UI.
- `app/evals/run_eval.py` — eval runner to extend from gated evidence scoring to final terminal outcome scoring.
- `app/llm/yandex_ai_studio.py` — verified Yandex AI Studio/Qwen client behavior.
- `requirements.txt` — dependency baseline; Phase 2 likely needs to add LangGraph if implementing the target graph directly.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `app/artifacts/workflow_artifacts.py`: Pydantic models already exist for intent, research design, evidence bundle, coverage, extraction plan, dataset artifact, methodology note, visualization spec, critique report, final answer, feedback, and trace. These are the natural extension point for Phase 2.
- `app/artifacts/source_cards.py`: Source-card and embedding-chunk contracts already enforce metadata-only retrieval inputs and stable source identities.
- `app/catalog/source_catalog.py`: SQLite catalog already materializes source cards, coverage hints, embedding chunks, and rejection metadata.
- `app/retrieval/embedding_index.py`: Qdrant/Yandex embedding build path exists, including gated credential evidence and local/remote Qdrant configuration.
- `app/retrieval/hybrid_retrieval.py`: Hybrid lexical/dense/rerank interface exists and should be improved rather than replaced.
- `app/data/deterministic_tools.py`: Deterministic utility layer exists for safe SQL/query/export/visualization contracts, but Phase 2 must promote it from probes to real extraction.
- `app/workflow/graph_contract.py`: Node contracts and route budgets already name the target architecture roles, but `Phase1Graph` is only a checkpoint-compatible smoke object.
- `app/ui/streamlit_app.py`: Current UI exposes readiness, trace, artifacts, selected/rejected sources, and feedback payloads, but does not execute the full workflow from arbitrary user input.
- `app/evals/run_eval.py`: Current eval runner scores gated evidence; Phase 2 should evolve it to score real workflow outputs and valid terminal statuses.
- `app/llm/yandex_ai_studio.py`: Current Yandex client has tests for verified base URL/auth and structured-output payload shape.

### Established Patterns

- All durable planning and evidence belongs under `.planning/`; generated local data and Qdrant state belong under `.local/`.
- Application code belongs under `app/`, with repeatable CLI builders and eval helpers under `scripts/`.
- Contracts should be Pydantic v2 models with stable machine-readable output.
- Trace events should use the canonical `TraceEvent` model in `app/artifacts/workflow_artifacts.py`.
- Tests should be evidence-first and should fail on silent gates, unsupported numeric claims, stale readiness, or source-bound invariant violations.
- Secrets must remain in `.env` / environment variables and must not be committed or quoted.

### Integration Points

- Streamlit should call the same workflow entrypoint that the golden-case eval runner uses.
- Workflow nodes should use retrieval/catalog/data/LLM modules as tools, not duplicate their logic.
- Final answer semantics must be coordinated across `workflow_artifacts.py`, `run_graph.py` or its replacement, `run_eval.py`, `run_demo.py`, and `streamlit_app.py`.
- Qdrant/dense readiness depends on `.planning/phases/01-data-architecture-research/embedding-index-manifest.json`, `.local/dataagent/phase1/embedding-cache.jsonl`, and `.local/qdrant`.
- Phase 2 should promote Qdrant server mode and configure shared access through `QDRANT_URL` so multiple Python clients do not contend for an embedded `.local/qdrant` storage lock.
- Local dumps stay outside the repo at `/Users/a/Downloads/dumps/...`; code should keep paths configurable.

</code_context>

<deferred>
## Deferred Ideas

None from this discussion. The user explicitly rejected deferring architecture-stack functionality out of Phase 2; downstream planning may stage work internally, but not move required Phase 2 capabilities into an unapproved later phase.

</deferred>

---

*Phase: 02-jury-mvp*
*Context gathered: 2026-05-10*
