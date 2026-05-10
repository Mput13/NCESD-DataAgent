---
phase: 02-jury-mvp
plan: "01"
subsystem: workflow-contracts
tags: [langgraph, pydantic, workflow-response, artifacts, service-entrypoint]
requires:
  - phase: 01-data-architecture-research
    provides: Phase 1 source-card, workflow artifact, graph smoke, and prepared-data manifest contracts.
provides:
  - Strict Phase 2 terminal outcome contract: passed, needs_clarification, not_found.
  - Shared WorkflowResponse schema for Streamlit, eval, and CLI callers.
  - Shared run_user_query import path guarded against fake final responses before plan 02-06.
affects: [02-jury-mvp, streamlit, evals, workflow-runtime, narrator]
tech-stack:
  added: [langgraph>=1.1.10]
  patterns:
    - Pydantic response models with terminal-outcome validators.
    - Service entrypoint raises explicit NotImplementedError until finalization exists.
key-files:
  created:
    - app/workflow/service.py
    - tests/test_phase2_contracts.py
  modified:
    - requirements.txt
    - app/artifacts/workflow_artifacts.py
key-decisions:
  - "Final user outcomes are constrained to passed, needs_clarification, and not_found; internal gated/stale/skipped/no_candidate states stay component-level only."
  - "run_user_query is the only shared frontend/eval/CLI entrypoint and must not return a fake WorkflowResponse before plan 02-06 implements finalization."
patterns-established:
  - "WorkflowResponse is the frontend-facing contract for answer blocks, sources, artifacts, trace, limitations, feedback actions, and component statuses."
  - "TDD contract tests pin terminal-status validation before downstream runtime work."
requirements-completed: [NLU-01, NLU-02, NLU-03, NLU-04, ART-01, ART-02, ART-03, ART-04, ART-05, ART-06, RBST-01, RBST-02, RBST-03, RBST-04, UI-02, UI-03, ENG-02, ENG-03]
duration: 3min
completed: 2026-05-10T11:52:36Z
---

# Phase 02 Plan 01: Response/Status/Artifact Contract Summary

**Strict Phase 2 response contract with LangGraph declared, terminal outcome validation, and one guarded workflow service entrypoint**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-10T11:49:49Z
- **Completed:** 2026-05-10T11:52:36Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Declared `langgraph>=1.1.10` and added import sanity coverage for Phase 2 runtime dependencies.
- Added `TerminalOutcome`, `FeedbackAction`, `ScriptArtifact`, `NoDataExplanationArtifact`, and `WorkflowResponse` to the canonical workflow artifact module.
- Enforced terminal response rules: `passed` requires dataset and script artifacts, `needs_clarification` requires clarification questions, and `not_found` requires no-data evidence.
- Added `WorkflowRunConfig.default()` and `run_user_query()` as the shared Streamlit/eval/CLI service import path.

## Task Commits

1. **Task 1: Declare LangGraph runtime dependency** - `63d8785` (feat)
2. **Task 2 RED: Add failing response contract tests** - `78dfc1f` (test)
3. **Task 2 GREEN: Add strict Phase 2 response models** - `a04fe62` (feat)
4. **Task 3 RED: Add failing service entrypoint tests** - `ea1afec` (test)
5. **Task 3 GREEN: Create shared workflow service entrypoint contract** - `117cc0a` (feat)

_Note: TDD tasks have separate red and green commits._

## Files Created/Modified

- `requirements.txt` - Adds the LangGraph runtime dependency required by the Phase 2 architecture.
- `tests/test_phase2_contracts.py` - Covers dependency imports, strict response validation, and service entrypoint defaults.
- `app/artifacts/workflow_artifacts.py` - Defines strict terminal outcomes and frontend/eval/CLI response artifacts.
- `app/workflow/service.py` - Defines `WorkflowRunConfig` and the guarded `run_user_query` service entrypoint.

## Decisions Made

- Internal workflow statuses such as `gated`, `skipped_with_reason`, `stale`, and `no_candidate` are invalid as final user outcomes. They can remain visible in `component_statuses`.
- `run_user_query` deliberately raises `NotImplementedError("Phase 2 final WorkflowResponse implementation is provided by plan 02-06")` until the critic/visualization/narrator finalization plan wires real final responses.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Concurrent Phase 2 agents modified unrelated files during execution. This plan only staged and committed its declared files and left unrelated changes untouched.

## Known Stubs

- `app/workflow/service.py` intentionally does not return a `WorkflowResponse` yet. This is required by the plan to prevent fake final success before plan `02-06` implements finalization.

## User Setup Required

None - no external service configuration required.

## Verification

- `python3 -m pytest tests/test_phase2_contracts.py -q` passed.
- `python3 -m pytest tests/test_phase2_contracts.py tests/test_workflow_graph.py -q` passed with `10 passed`.

## Self-Check: PASSED

- Verified created/modified files exist: `requirements.txt`, `tests/test_phase2_contracts.py`, `app/artifacts/workflow_artifacts.py`, `app/workflow/service.py`, and this summary.
- Verified task commits exist: `63d8785`, `78dfc1f`, `a04fe62`, `ea1afec`, and `117cc0a`.

## Next Phase Readiness

Plans `02-02` through `02-08` can now import one shared `WorkflowResponse` and `run_user_query` contract. Downstream work must preserve the final-outcome restrictions and replace the service guard only when plan `02-06` has real critic, visualization, narrator, and artifact-backed finalization.

---
*Phase: 02-jury-mvp*
*Completed: 2026-05-10*
