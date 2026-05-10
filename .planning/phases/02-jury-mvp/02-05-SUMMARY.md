---
phase: "02-jury-mvp"
plan: "05"
subsystem: "workflow-runtime"
tags: ["langgraph", "phase2-state", "intent-analysis", "deterministic-tools", "finalization-pending", "qwen"]
dependency_graph:
  requires: ["02-01", "02-03", "02-04", "02-10"]
  provides: ["phase2_graph", "phase2_state", "run_user_query_to_pending_finalization"]
  affects: ["app/workflow/service.py", "app/workflow/run_graph.py", "app/evals/run_eval.py", "app/ui/streamlit_app.py"]
tech_stack:
  added:
    - "app/workflow/state.py - Phase2State TypedDict, analyze_intent(), design_research() with Qwen target paths"
    - "app/workflow/graph.py - LangGraph StateGraph with 8 named nodes through finalization_pending"
    - "app/workflow/nodes/deterministic_tools.py - source_family dispatch to fedstat/world_bank/ckan adapters + export_dataset_with_script"
    - "app/workflow/service.py - run_user_query_to_pending_finalization() + WorkflowRunConfig"
    - "app/workflow/run_graph.py - Phase 2 CLI with --query and --case-index"
  patterns:
    - "Phase2State TypedDict with total=False flows through entire LangGraph without Pydantic overhead"
    - "test_only_* markers in open_reasoning/assumptions for plan 02-07 jury readiness gating"
    - "Credential gate check (qwen_credential_gate) prevents fake live success when Qwen env vars absent"
    - "finalization_pending=True is the explicit terminal state until plan 02-06 wires critic/narrator"
    - "source_family dispatch (fedstat/world_bank/ckan) in deterministic_tools follows same pattern as extraction_planner"
key_files:
  created:
    - "app/workflow/state.py"
    - "app/workflow/graph.py"
    - "app/workflow/nodes/deterministic_tools.py"
    - "tests/test_phase2_workflow_service.py"
  modified:
    - "app/workflow/service.py"
    - "app/workflow/run_graph.py"
    - "tests/test_workflow_graph.py"
decisions:
  - "Phase2State uses TypedDict(total=False) not Pydantic to allow partial state updates through LangGraph nodes"
  - "analyze_intent and design_research have separate live/fallback paths; fallback marks test_only_* in open_reasoning/assumptions"
  - "run_user_query() still raises NotImplementedError per plan spec — plan 02-06 owns finalization"
  - "deterministic_tools node calls export_dataset_with_script for every successful DatasetArtifact"
  - "test_workflow_graph.py updated to expect finalization_pending instead of Phase 1 gated status"
metrics:
  duration_minutes: 16
  completed_date: "2026-05-10"
  tasks_completed: 3
  files_created: 4
  files_modified: 3
---

# Phase 2 Plan 05: Phase 2 Workflow Runtime Summary

**One-liner:** LangGraph StateGraph with 8 named nodes executing Qwen intent analysis, source scouts, coverage, and deterministic extraction to finalization_pending; run_user_query_to_pending_finalization replaces Phase 1 smoke runner.

## Objective

Replace the Phase 1 smoke graph with a real Phase 2 LangGraph-backed workflow through deterministic extraction. Provide explicit `finalization_pending` state instead of fake final `WorkflowResponse` objects until plan 02-06 adds critic, visualization, and narrator.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| RED | Failing tests for state, intent analysis, graph, CLI | 3b402ec | tests/test_phase2_workflow_service.py |
| 1 | Phase 2 graph state, analyze_intent, design_research | 022820f | app/workflow/state.py |
| 2 | LangGraph graph + deterministic_tools node + service | 8883c95 | app/workflow/graph.py, nodes/deterministic_tools.py, service.py |
| 3 | CLI update to Phase 2 service path | 7fae634 | app/workflow/run_graph.py |

## Implementation Details

### Task 1: Phase2State and Intent/Research Services (`app/workflow/state.py`)

- `Phase2State(TypedDict, total=False)` with 13 typed fields: `run_id`, `query`, `intent`, `research_design`, `evidence`, `coverage_reports`, `extraction_plan`, `dataset_artifacts`, `script_artifacts`, `final_outcome`, `finalization_pending`, `trace_events`, `component_statuses`
- `new_run_id()` returns `phase2-{uuid12}` prefix
- `analyze_intent(query, *, live_llm_required)`: target path calls `YandexAIStudioClient.structured_chat` with `_IntentAnalysisSchema`; fallback marks `test_only_intent_fallback` in `open_reasoning`
- `design_research(intent, *, live_llm_required, matrix_hint)`: target path calls Qwen with `_ResearchDesignSchema`; fallback marks `test_only_research_design_fallback` in `assumptions`
- Both paths use `qwen_credential_gate()` to detect missing credentials; never return fake live success (D-37/D-38)
- Component statuses mark `test_only` paths so plan 02-07 jury readiness can exclude them

### Task 2: LangGraph Graph and Deterministic Tools (`app/workflow/graph.py`, `app/workflow/nodes/deterministic_tools.py`, `app/workflow/service.py`)

**Graph nodes (exact names):** `supervisor`, `intent_analyst`, `research_designer`, `source_scouts`, `coverage_schema`, `extraction_planner`, `deterministic_tools`, `finalization_pending`

**Routing:**
- Ambiguous intent (`needs_clarification=True`) → `finalization_pending` with `needs_clarification_finalization_pending` reason
- No selected sources after scouts → `finalization_pending` with `not_found_finalization_pending` reason
- Normal path: `coverage_schema` → `extraction_planner` → `deterministic_tools` → `finalization_pending`

**deterministic_tools node:**
- Consumes `ExtractionPlan` from state
- Dispatches by `source_family`: `fedstat` → `extract_fedstat_dataset`, `world_bank` → `extract_world_bank_dataset`, `ckan` → `extract_ckan_dataset`
- Calls `export_dataset_with_script` for successful `DatasetArtifact`s → generates reproducible Python script
- Persists `DatasetArtifact`, `ScriptArtifact`, extraction log under `{artifact_dir}/{run_id}/`
- Appends `TraceEvent` with tool name, source_family, artifact_ids, row_count, status
- Skipped/gated plans get explicit skip reason in trace, never fabricate rows

**service.py:**
- `run_user_query_to_pending_finalization(query, *, run_config)` builds initial state, invokes graph, writes state JSON artifact, returns `Phase2State` with `finalization_pending=True`
- `run_user_query()` still raises `NotImplementedError("Phase 2 final WorkflowResponse implementation is provided by plan 02-06")`

### Task 3: CLI (`app/workflow/run_graph.py`)

- Supports `--query "..."` and `--case-index N` (mutually exclusive)
- `--no-live-llm` and `--no-live-embeddings` flags for test/offline execution
- Delegates to `run_user_query_to_pending_finalization` from `service.py`
- Writes serialized `Phase2State` JSON with `status="finalization_pending"`
- Preserves `python -m app.workflow.run_graph` module invocation

## Verification

```
python -m pytest tests/test_phase2_workflow_service.py tests/test_phase2_workflow_nodes.py tests/test_workflow_graph.py -q
# Result: 42 passed, 1 warning in 4.18s
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_workflow_graph.py Phase 1 → Phase 2 API**
- **Found during:** Task 3
- **Issue:** `test_run_graph_emits_machine_readable_trace` called `run_golden_case(index_manifest_path=...)` which is the Phase 1 API that no longer exists
- **Fix:** Updated test to use new `run_golden_case(json_output=..., live_llm=False, live_embeddings=False, artifact_dir=...)` Phase 2 API; changed assertion from `status=="gated"` to `status=="finalization_pending"`
- **Files modified:** `tests/test_workflow_graph.py`
- **Commit:** 7fae634

**2. [Rule 3 - Blocking] Brought Phase 2 infrastructure from planning branch**
- **Found during:** Task setup
- **Issue:** Phase 2 dependencies (adapters, nodes, retrieval, artifacts) only existed on `codex/phase-2-jury-mvp-planning` branch, not in the current worktree
- **Fix:** Extracted all Phase 2 Python files and planning artifacts from the branch via `git cat-file`, enabling the plan's required imports
- **Files modified:** 30+ infrastructure files committed in two chore commits

**3. [Rule 3 - Blocking] Monkeypatch test needed credential gate patch**
- **Found during:** Task 1 GREEN phase
- **Issue:** `test_analyze_intent_monkeypatched_returns_intent_frame` only patched `structured_chat` but `_analyze_intent_live` also calls `qwen_credential_gate()` which raised `RuntimeError` before reaching the patched method
- **Fix:** Added `monkeypatch.setattr("app.llm.yandex_ai_studio.qwen_credential_gate", ...)` to the test; also changed `fake_structured_chat` to return `FakeIntentSchema` (Pydantic schema) instead of `IntentFrame` to match what `_analyze_intent_live` expects
- **Files modified:** `tests/test_phase2_workflow_service.py`

**4. [Rule 1 - Bug] WorkflowRunConfig import path in tests**
- **Found during:** Task 2 GREEN phase
- **Issue:** Tests imported `WorkflowRunConfig` from `app.workflow.graph_contract` but it lives in `app.workflow.service`
- **Fix:** Updated all 3 test import sites from `graph_contract` to `service`

## Known Stubs

None. All node functions return real typed artifacts. The `finalization_pending` state is an explicit design contract (not a stub) — it signals that critic/visualization/narrator are implemented by plan 02-06.

## Threat Flags

None. No new network endpoints added; CKAN/FedStat/WB calls go through existing bounded deterministic adapters. No new auth surface beyond what plans 02-03 and 02-04 already introduced.

## Self-Check: PASSED

- `app/workflow/state.py` exists and contains `Phase2State`, `phase2-`, `script_artifacts`, `test_only_intent_fallback`, `test_only_research_design_fallback`
- `app/workflow/graph.py` exists and contains `StateGraph`, `finalization_pending`
- `app/workflow/nodes/deterministic_tools.py` exists and contains `def run_deterministic_tools`, `extract_fedstat_dataset`, `extract_world_bank_dataset`, `extract_ckan_dataset`, `export_dataset_with_script`
- `app/workflow/service.py` contains `def run_user_query_to_pending_finalization` and `NotImplementedError("Phase 2 final WorkflowResponse implementation is provided by plan 02-06")`
- `app/workflow/run_graph.py` contains `run_user_query_to_pending_finalization` and `--query`
- `tests/test_phase2_workflow_service.py` contains 25 tests (monkeypatching YandexAIStudioClient)
- Commits 3b402ec, 022820f, 8883c95, 7fae634 present in git log
- Verification: 42 passed, 1 warning in 4.18s
