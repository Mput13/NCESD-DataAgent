# Phase 2 Seed Context: Full Jury MVP

This is seed context for the next session. It is intentionally not named `02-CONTEXT.md` so `$gsd-discuss-phase 2` still runs and captures unresolved decisions before planning.

## Starting Point

Phase 1 is accepted only as infrastructure, not as a functional MVP.

Canonical Phase 1 acceptance evidence:

- `.planning/phases/01-data-architecture-research/phase1-test-acceptance.md`
- `.planning/phases/01-data-architecture-research/phase1-actual-state-verification.md`
- `.planning/ARCHITECTURE_STACK.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`

Current Phase 1 acceptance result:

- `python3 -m pytest -vv`: 27 collected, 26 passed, 1 failed.
- Demo readiness: `overall_status=blocked`, `qdrant_status=stale`, `dense_retrieval_ready=false`.
- Retrieval eval over 20 golden cases: all dense rows `gated_skip`, 14 source-family matches, 6 no-candidate cases.
- Extraction probes: coverage evidence exists, extraction is `skipped_with_reason`.
- Data relevance eval: 0 passed / 0 failed / 20 gated.
- Workflow smoke: trace exists, but coverage/extraction are gated and `final_answer.status=ok` is semantically wrong.
- Streamlit UI is diagnostic only; it does not run a full user-query workflow.

## User Decision

The user explicitly rejected a low acceptance bar. Phase 2 must target all 20 golden cases, not a small demo subset.

Acceptance is not "2-3 representative cases." Staged implementation order is allowed, but final Phase 2 acceptance requires all 20 golden cases to reach correct terminal outcomes.

Valid terminal outcomes:

- `passed`: relevant source selection, coverage checked, deterministic extraction completed, sourced answer produced, dataset/script/artifacts available, trace visible.
- `needs_clarification`: query is genuinely ambiguous and the system asks a useful specific question.
- `not_found`: trusted/available sources were checked and rejected with explicit reasons.

Invalid final outcomes:

- `gated`
- `stale`
- `skipped_with_reason`
- `no_candidate`
- `final_answer.status=ok` while coverage or extraction is gated
- unsupported numeric claims
- UI-only demo path that bypasses the evaluated workflow

## Target Workflow

Phase 2 must implement the full jury MVP workflow:

```text
User query
→ Supervisor
→ Intent Analyst
→ Research Designer / Direct path
→ FedStat/WB/CKAN Scouts
→ Coverage & Schema
→ Extraction Planner
→ Deterministic Tools
→ Methodology Critic
→ Visualization
→ Narrator
→ answer + dataset + script + sources + trace
```

## UI Target

Streamlit remains the first UI target, but the Phase 1 diagnostic shell is not enough.

The jury UI must:

- accept a natural-language query;
- run the same workflow used by tests/evals;
- show state transitions and agent outputs;
- show selected and rejected sources;
- show coverage checks;
- show generated extraction plan and deterministic SQL/script;
- show dataset preview and downloadable dataset/script artifacts;
- show visualization generated from `DatasetArtifact`;
- show final answer with source provenance;
- show limitations, clarification questions, or not-found evidence when relevant.

## Source-Bound Invariants

- Every number must come from deterministic tools or trusted source adapters.
- LLM may classify, plan, select, critique, and narrate, but it must not read table values or invent numeric facts.
- CKAN is a trusted NSED catalog API, not general web search. Use bounded package/resource search and cache only promoted metadata.
- Qdrant remains the vector-store abstraction; do not replace it with a throwaway custom vector path.
- Full source-card corpus/catalog artifacts from Phase 1 are valuable and should be preserved.

## Remote Workstream Review

`origin/workstream-1/core-integration` was fetched and reviewed after Phase 1 acceptance.

Decision: do not merge it wholesale.

Why:

- It deletes current Phase 1 artifacts, tests, scripts, and summaries.
- It rewinds `.planning/STATE.md` and `.planning/ROADMAP.md` to a pre-execution view.
- Its workflow/scout/extraction path remains explicitly stubbed.
- It regresses the verified Yandex AI Studio endpoint/auth behavior: remote uses `https://ai.api.cloud.yandex.net/v1` with `Bearer`, while current verified code uses `https://llm.api.cloud.yandex.net/v1` with `Api-Key`.
- It introduces useful LangGraph/contract ideas, but they must be ported selectively and tested against Phase 2 acceptance.

Potentially useful ideas to port:

- `AgentState` as a single workflow state object.
- `StateGraph` routing with supervisor/intent/scout/coverage/extraction/critic/narrator nodes.
- explicit typed artifacts for intent, research design, coverage, extraction plan, dataset, critique, visualization, final answer, and trace.
- human-in-the-loop clarification routing.

Do not port:

- stub scout/extraction behavior as accepted implementation;
- old planning state;
- deletion of existing Phase 1 evidence;
- Yandex endpoint/auth regression.

## Discussion Questions For `$gsd-discuss-phase 2`

Start discussion from these decisions:

1. Confirm all 20 golden cases are the Phase 2 acceptance set.
2. Decide the exact valid terminal statuses and scoring threshold for all 20 cases.
3. Decide whether to finish full embedding index before core workflow work or allow parallel work while embedding completes.
4. Choose how to handle CKAN cases: bounded live CKAN preparation now, or explicit not-found/needs-source-prep only if evidence supports it.
5. Decide the first implementation wave order without lowering final acceptance: workflow state/contracts, retrieval ranking, coverage/extraction adapters, UI.
6. Decide how strict the LLM requirement is for MVP: Qwen live calls required, or deterministic fallback allowed only when credentials are absent, with explicit gate.

## Next Command

```text
$gsd-discuss-phase 2
```
