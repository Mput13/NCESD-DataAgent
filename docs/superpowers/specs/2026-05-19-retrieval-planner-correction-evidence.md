# Retrieval Planner Correction Evidence - 2026-05-19

Status: implementation evidence and handoff artifact.

Related artifacts:

- `docs/superpowers/specs/2026-05-18-workflow-refactor-context.md`
- `docs/superpowers/specs/2026-05-18-workflow-intent-retrieval-v2.md`
- `docs/superpowers/specs/2026-05-18-intent-retrieval-planner-vision.md`
- `docs/superpowers/specs/2026-05-19-adr-intent-retrieval-boundary.md`
- `docs/superpowers/specs/2026-05-19-agent-artifact-drift-negative-example.md`
- `docs/superpowers/specs/2026-05-19-retrieval-planner-implementation-spec.md`

## Summary

The incorrect deterministic-only Retrieval Planner implementation was corrected.

Commit:

```text
f4c6fbe Fix retrieval planner LLM boundary
```

Branch:

```text
feat/fix-after-matmod
```

Remote:

```text
origin/feat/fix-after-matmod
```

## Problem Fixed

The prior working-tree implementation treated Retrieval Planner as a deterministic
transformation over `UserIntentArtifact`. That contradicted the accepted boundary:

```text
Intent Analyst -> Retrieval Planner -> Source Scouts
```

Accepted boundary:

- Intent Analyst produces durable semantic `UserIntentArtifact`.
- Retrieval Planner calls live/mock Qwen/Yandex structured output for primary
  `RetrievalInput` probe generation.
- Source Scouts execute planner probes and preserve per-probe evidence.
- Deterministic code inside Retrieval Planner may validate/post-process LLM output
  but must not generate primary probes.

## Implemented Scope

Runtime files changed:

- `app/artifacts/workflow_artifacts.py`
- `app/workflow/state.py`
- `app/workflow/graph.py`
- `app/workflow/nodes/scouts.py`
- `app/workflow/run_graph.py`
- `app/workflow/service.py`
- `app/workflow/runtime_paths.py`

Tests changed:

- `tests/test_phase2_workflow_nodes.py`
- `tests/test_phase2_workflow_service.py`
- `tests/test_workflow_graph.py`
- `tests/test_phase2_contracts.py`

Specs/state changed:

- `.planning/STATE.md`
- `docs/superpowers/specs/2026-05-18-workflow-refactor-context.md`
- `docs/superpowers/specs/2026-05-18-workflow-intent-retrieval-v2.md`
- `docs/superpowers/specs/2026-05-18-intent-retrieval-planner-vision.md`
- `docs/superpowers/specs/2026-05-19-adr-intent-retrieval-boundary.md`
- `docs/superpowers/specs/2026-05-19-agent-artifact-drift-negative-example.md`
- `docs/superpowers/specs/2026-05-19-retrieval-planner-implementation-spec.md`

## Behavior Now Enforced

`plan_retrieval` now:

- consumes `UserIntentArtifact`;
- calls `YandexAIStudioClient.structured_chat(...)` with a Retrieval Planner schema;
- asks Qwen/Yandex to generate source-card metadata probes;
- preserves explicit source scope and dimensions from intent;
- validates measure ids and source-family hints;
- clamps execution budget fields;
- adds a low-priority raw query fallback when absent;
- marks primary probes as `origin="llm"`;
- marks fallback as `origin="mechanical_fallback"`;
- refuses empty/non-primary LLM output for statistical requests;
- gates on missing credentials or LLM errors instead of synthesizing deterministic
  primary probes.

`_node_retrieval_planner` now:

- returns a gated/finalization-pending state when planner LLM work fails;
- traces the error as `retrieval_planner`;
- does not pass deterministic primary probes downstream on failure.

`build_phase2_graph` now compiles the pre-retrieval path as:

```text
supervisor -> intent_analyst -> retrieval_planner -> source_scouts
```

The pre-retrieval `research_designer` node remains as legacy import-compatible
code for older tests/downstream references, but it is no longer part of the
compiled pre-retrieval runtime path.

`run_source_scouts` now:

- consumes `RetrievalInput` when present;
- executes planner probes rather than relying on the raw query alone;
- merges/dedupes candidate results by stable source identity;
- preserves per-probe evidence, including `origin`, for selected/CKAN candidates.

## Acceptance Evidence

Targeted verification command:

```bash
python3 -m pytest tests/test_phase2_workflow_nodes.py tests/test_workflow_graph.py tests/test_phase2_workflow_service.py -q
```

Result:

```text
52 passed, 1 warning in 18.34s
```

The warning was an upstream LangGraph deprecation warning from
`langgraph.cache.base`.

The targeted tests prove:

- Retrieval Planner calls the mocked structured-output client for primary probes.
- Deterministic-only primary probe generation cannot satisfy acceptance.
- LLM unavailable/missing credentials gates instead of returning deterministic
  primary probes.
- A BRICS request with GDP, inflation, and unemployment produces LLM-origin probes
  for `world_bank`, `fedstat`, and `ckan` for each measure.
- Primary probe text excludes years, geography group, analysis verbs, and output
  shape.
- Dimension constraints carry geographies, geography group, period, and frequency.
- Raw query fallback exists only as low-priority `raw_query_fallback` with
  `origin="mechanical_fallback"`.
- Source Scouts consume `RetrievalInput` and preserve per-probe evidence.
- Graph routing is `intent_analyst -> retrieval_planner -> source_scouts`, not
  pre-retrieval `research_designer`.

## Full Suite Status

Full verification command:

```bash
python3 -m pytest -q
```

Result observed on 2026-05-19:

```text
288 passed, 18 failed, 1 warning
```

The remaining failures were outside this Retrieval Planner correction slice.
They were in existing diagnostics/acceptance/demo/web/Yandex helper surfaces,
including:

- World Bank coverage diagnostic expecting non-empty countries handoff;
- full mocked pipeline response trace expectation;
- embedding index Qdrant mode expectation;
- Phase 2 acceptance runner `used_test_only_fallbacks` plumbing;
- missing `split_rejections` API in hybrid retrieval;
- narrator diagnostic behavior when `live_llm_required=False`;
- web/static marker expectations;
- Yandex structured-output helper expectation for `json_schema` vs current
  `json_object`.

Do not treat those failures as evidence that deterministic-only Retrieval Planner
is still present. They are residual downstream/platform work.

## Not Done

This slice intentionally did not:

- clean `HybridRetriever` semantic heuristics;
- redesign Coverage Inventory;
- implement Source Selection/sufficiency;
- alter deterministic extraction;
- change Critic/Narrator final outcome guardrails;
- lower Phase 2 all-20 golden acceptance.

## Residual Risk

The corrected pre-retrieval path is contract-aligned, but the agent is not yet
end-to-end reliable. The next runtime risks are downstream:

- Source Scouts still hand candidates into legacy `EvidenceBundleArtifact`, not a
  full `SourceCandidatePool`.
- Coverage can still produce false `not_found` if geography/period/schema matching
  is too rigid.
- Downstream code still uses the legacy `IntentFrame` adapter in several places.
- Full acceptance remains blocked by failures outside this slice.

## Recommended Next Slice

Proceed to Source Scouts/Coverage handoff before retriever semantic cleanup:

```text
RetrievalInput + UserIntentArtifact + candidate evidence
-> Coverage Inventory
-> Source Selection / sufficiency
```

Immediate focus:

- ensure Coverage receives normalized geography/country constraints from
  `UserIntentArtifact`, not only legacy `IntentFrame.known_fields`;
- introduce source candidate pool or coverage input shape that preserves
  per-probe evidence and requested dimensions;
- prevent coverage/parser misses from becoming premature final `not_found`;
- keep all 20 golden cases as final acceptance target.
