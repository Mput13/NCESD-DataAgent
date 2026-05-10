---
phase: 02-jury-mvp
plan: "06"
subsystem: workflow-finalization
tags:
  - critic
  - visualization
  - narrator
  - finalization
  - tdd
dependency_graph:
  requires:
    - 02-03  # deterministic tools, dataset/script artifacts
    - 02-05  # extraction, coverage, Phase2State
  provides:
    - run_user_query (complete WorkflowResponse)
    - continue_user_query (clarification follow-up)
    - Methodology Critic guardrails
    - deterministic VisualizationSpec
    - source-bound Narrator
  affects:
    - app/workflow/service.py
    - app/workflow/graph.py
    - tests/test_phase2_finalization.py
tech_stack:
  added:
    - app/workflow/nodes/critic.py
    - app/workflow/nodes/visualization.py
    - app/workflow/nodes/narrator.py
  patterns:
    - TDD RED/GREEN cycle per task
    - Qwen target path + deterministic test fallback (test_only_*_fallback markers)
    - Post-critique deterministic guardrails after LLM verdict
    - Numeric assertion via regex ledger from dataset records
key_files:
  created:
    - app/workflow/nodes/critic.py
    - app/workflow/nodes/visualization.py
    - app/workflow/nodes/narrator.py
  modified:
    - app/workflow/service.py
    - tests/test_phase2_finalization.py
    - tests/test_phase2_workflow_service.py
    - tests/test_phase2_contracts.py
decisions:
  - "Critic runs deterministically after LLM verdict: gated coverage or missing ok dataset overrides LLM pass"
  - "Visualization chart_type derived from column analysis: period+single geo=line, period+multi geo=grouped_line"
  - "assert_message_numbers_are_supported uses regex ledger from dataset records to catch unsupported numerics"
  - "continue_user_query persists pending state as JSON; re-finalizes with existing data when available"
  - "Fallback markers (test_only_critic_fallback, test_only_narrator_fallback) excluded from jury readiness by plan 02-07"
metrics:
  duration: "~25 minutes"
  completed: "2026-05-10"
  tasks_completed: 3
  tests_added: 51
  tests_total_passing: 83
  files_created: 3
  files_modified: 4
---

# Phase 2 Plan 06: Critic, Visualization, Narrator Finalization Layer Summary

**One-liner:** Critic guardrails + deterministic visualization + source-bound narrator enforce that `run_user_query` returns only evidence-backed `passed`/`needs_clarification`/`not_found` WorkflowResponses.

## Objective Achieved

Plan 02-06 implements the finalization enforcement layer that turns internal workflow evidence into safe final responses. `run_user_query` now returns a complete `WorkflowResponse` instead of raising `NotImplementedError`. All three finalization nodes are implemented with TDD (RED -> GREEN pattern).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | TDD failing tests for all finalization nodes | 54aeed1 | tests/test_phase2_finalization.py |
| 1 (GREEN) | Methodology Critic final-outcome guard | 69d2f05 | app/workflow/nodes/critic.py |
| 2 (GREEN) | Visualization from DatasetArtifact | 9297ed4 | app/workflow/nodes/visualization.py |
| 3 (GREEN) | Narrator, service finalization, clarification | dc12478 | app/workflow/nodes/narrator.py, service.py |
| fix | Update stale tests (NotImplementedError) | 0a736cc | tests/*.py |

## Implementation Details

### Task 1: Methodology Critic (`app/workflow/nodes/critic.py`)

`run_methodology_critic(state, *, live_llm_required)` calls `YandexAIStudioClient.structured_chat` in the target path. When `live_llm_required=False`, uses a deterministic fallback marked `test_only_critic_fallback`.

**Concrete post-critique guardrails** (applied after LLM verdict):
- Coverage all `ok` required for `passed`
- At least one `DatasetArtifact` with `status="ok"` and `rows>0` required for `passed`
- Every ok `DatasetArtifact` must have non-empty `provenance`
- Unit/frequency warnings -> `pass_with_warnings`

`derive_final_outcome(state, critique)` maps `CritiqueReport.verdict` to `TerminalOutcome`:
- `pass`/`pass_with_warnings` -> `passed` (if guardrails pass)
- `needs_user_clarification` -> `needs_clarification`
- `not_found`/`needs_repair` -> `not_found`

### Task 2: Visualization (`app/workflow/nodes/visualization.py`)

`build_visualization(dataset, *, query_category)` creates `VisualizationSpec` deterministically:
- Uses `render_visualization_from_dataset_artifact` from `app/data/deterministic_tools.py`
- `period` column + single `geo_id` value -> `line`
- `period` column + multiple `geo_id` values -> `grouped_line`
- No period, categorical data -> `bar`
- Otherwise -> `table`
- None dataset or empty records -> `skipped_with_reason`

### Task 3: Narrator (`app/workflow/nodes/narrator.py`)

`build_workflow_response(state, *, final_outcome, critique, visualization, live_llm_required)`:
- Target path calls `YandexAIStudioClient.structured_chat` with compact source-bound context
- Fallback marked `test_only_narrator_fallback`
- Answer blocks by outcome: `summary`/`methodology`/`limitations`/`how_found` for `passed`; clarification questions for `needs_clarification`; `NoDataExplanationArtifact` for `not_found`

`assert_message_numbers_are_supported(message, datasets)`:
- Extracts integers and decimals from message via regex
- Builds ledger from dataset records, provenance, periods
- Raises `ValueError` for any number not in ledger (e.g. hallucinated `999999`)

### Service Finalization (`app/workflow/service.py`)

`run_user_query(query, *, run_config)`:
- Calls `run_user_query_to_pending_finalization` (graph through extraction)
- Then `_finalize_state`: critic -> visualization -> narrator
- Persists pending state via `_write_pending_clarification_state`
- Returns complete `WorkflowResponse`

`continue_user_query(run_id, clarification_answer, *, run_config)`:
- Loads `pending-clarification.json` from artifact directory
- Merges answer into `IntentFrame.known_fields` / `missing_fields`
- Appends trace event
- Re-finalizes with existing data if ok datasets exist; otherwise re-runs full pipeline
- Can change outcome from `needs_clarification` to `passed` or `not_found`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated stale tests expecting NotImplementedError**
- **Found during:** Task 3 verification (full test suite run)
- **Issue:** `test_phase2_workflow_service.py` and `test_phase2_contracts.py` contained tests that expected `run_user_query` to raise `NotImplementedError`. Plan 02-06 specifically implements this function, so the old tests became contradictions.
- **Fix:** Updated tests to verify `run_user_query` returns `WorkflowResponse` with valid terminal outcome
- **Files modified:** `tests/test_phase2_workflow_service.py`, `tests/test_phase2_contracts.py`
- **Commit:** 0a736cc

**2. [Rule 1 - Bug] Windows path separator in test assertion**
- **Found during:** Task 3 verification
- **Issue:** `test_workflow_run_config_default_points_to_phase2_artifacts` used `str()` comparison which fails on Windows due to `\` vs `/`
- **Fix:** Changed to `Path()` comparison which is OS-agnostic
- **Files modified:** `tests/test_phase2_contracts.py`
- **Commit:** 0a736cc

## Known Stubs

**Qwen live path in critic.py and narrator.py:**
- `run_methodology_critic(state, live_llm_required=True)` calls real Yandex API (not stubbed)
- `build_workflow_response(state, ..., live_llm_required=True)` calls real Yandex API (not stubbed)
- Both are tested with monkeypatched LLM client
- Plan 02-07 must verify that `test_only_critic_fallback` and `test_only_narrator_fallback` markers are absent in the jury-ready path

## Threat Flags

None. No new network endpoints, auth paths, or schema changes introduced. The narrator's numeric assertion (`assert_message_numbers_are_supported`) reduces the risk of hallucinated numeric claims in responses.

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| app/workflow/nodes/critic.py | FOUND |
| app/workflow/nodes/visualization.py | FOUND |
| app/workflow/nodes/narrator.py | FOUND |
| app/workflow/service.py (with run_user_query + continue_user_query) | FOUND |
| tests/test_phase2_finalization.py | FOUND |
| .planning/phases/02-jury-mvp/02-06-SUMMARY.md | FOUND |
| Commit 54aeed1 (test RED) | FOUND |
| Commit 69d2f05 (feat critic GREEN) | FOUND |
| Commit 9297ed4 (feat visualization GREEN) | FOUND |
| Commit dc12478 (feat narrator + service GREEN) | FOUND |
| 83 tests passing | PASSED |
