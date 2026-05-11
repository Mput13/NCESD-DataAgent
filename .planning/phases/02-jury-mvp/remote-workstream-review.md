# Remote Workstream Review

Reviewed branch: `origin/workstream-1/core-integration`

Reviewed commits:

- `033174b feat(ws1): add contracts, LangGraph workflow skeleton, LLM layer, and tests`
- `99f12e4 merge: resolve conflict in app/llm/__init__.py, keep ws1 exports`

## Decision

Do not merge this branch wholesale into the current Phase 2 base.

It is useful as reference material, but incorrect as a direct integration target.

## Why It Is Not Directly Mergeable

The diff from current `HEAD` to `origin/workstream-1/core-integration` would:

- delete current Phase 1 scripts for source cards, source catalog, embedding corpus/index builds, partial snapshots, embedding monitor, extraction probes, and retrieval eval;
- delete current Phase 1 tests for source cards, catalog/corpus, embedding index, hybrid retrieval, eval runner, workflow graph, demo readiness, deterministic tools, and Yandex AI Studio;
- delete current Phase 1 evidence artifacts, manifests, summaries, golden cases, retrieval/eval outputs, and final recommendation artifacts;
- rewind `.planning/STATE.md` to "Phase 1 planned, not executed";
- replace the current verified Yandex AI Studio endpoint/auth with an older likely-regressed client using `https://ai.api.cloud.yandex.net/v1` and `Bearer` auth instead of the verified `https://llm.api.cloud.yandex.net/v1` and `Api-Key` auth;
- introduce a LangGraph pipeline whose scout, coverage, extraction, and data-extractor functions remain explicitly stubbed or delegated to missing future `app.data.*` modules.

This conflicts with the accepted Phase 1 state and would erase the evidence needed for Phase 2 planning.

## Useful Ideas To Port Selectively

These ideas may be useful in Phase 2 if ported carefully and verified:

- a single `AgentState` object passed through all workflow nodes;
- LangGraph `StateGraph` routing for intent, research design, source scouts, coverage, extraction, critic, narrator, and clarification loops;
- explicit typed artifacts for intent, design, source candidates, coverage, extraction plan, dataset, critique, visualization, answer, and trace;
- human-in-the-loop clarification routing;
- contract tests for workflow graph shape.

## Ideas Not Accepted As Implementation

- Stub scout/search behavior is not accepted.
- Stub extraction returning empty datasets is not accepted.
- Tests that only mock every node are not enough for Phase 2 acceptance.
- Any final answer path that can succeed without deterministic extraction is not accepted.
- Any planning state that lowers acceptance to a subset of cases is not accepted.

## Phase 2 Integration Rule

Remote code can only be ported in small reviewed pieces. Each piece must preserve current Phase 1 artifacts and must pass the Phase 2 acceptance direction:

- all 20 golden cases are evaluated;
- final states are `passed`, `needs_clarification`, or `not_found`;
- `gated`, `stale`, `skipped_with_reason`, and `no_candidate` are not acceptable final outcomes;
- numbers only come from deterministic tools or trusted source adapters.
