---
phase: 02-jury-mvp
plan: "07"
subsystem: acceptance-gate
tags:
  - acceptance
  - eval
  - demo-readiness
  - golden-cases
  - tdd
dependency_graph:
  requires:
    - 02-02  # workflow nodes and scouts
    - 02-06  # run_user_query complete WorkflowResponse
    - 02-10  # coverage matrix golden-coverage-matrix.json
  provides:
    - scripts/run_phase2_acceptance.py (all-20 golden-case CLI runner)
    - app/evals/run_eval.score_phase2_results (Phase 2 eval scoring function)
    - app/demo/run_demo.assess_phase2_readiness (Phase 2 readiness gate)
  affects:
    - scripts/run_phase2_acceptance.py
    - app/evals/run_eval.py
    - app/demo/run_demo.py
    - tests/test_phase2_acceptance.py
tech_stack:
  added:
    - scripts/run_phase2_acceptance.py
    - scripts/__init__.py
  patterns:
    - TDD RED/GREEN cycle (failing tests committed before implementation)
    - UNACCEPTABLE_OUTCOMES frozenset gate (gated/stale/skipped_with_reason/no_candidate/ok)
    - test_only_* fallback marker detection (D-37/D-38 compliance)
    - Coverage matrix alignment per case (expected_terminal_outcome vs actual)
    - Phase 2 readiness requires all-20 cases, zero test-only fallbacks, zero unacceptable
key_files:
  created:
    - scripts/run_phase2_acceptance.py
    - scripts/__init__.py
    - tests/test_phase2_acceptance.py
  modified:
    - app/evals/run_eval.py
    - app/demo/run_demo.py
decisions:
  - "Acceptance runner uses run_user_query from app.workflow.service as the shared entrypoint — same path used by UI, evals, and CLI"
  - "UNACCEPTABLE_OUTCOMES frozenset: gated, stale, skipped_with_reason, no_candidate, ok, ok-with-gated-internals"
  - "score_phase2_results added to run_eval.py — evaluates passed cases for dataset>=1, script>=1, trace>=5"
  - "assess_phase2_readiness in run_demo.py gates overall_status=ready on total_cases==20, failed==0, unacceptable==0"
  - "scripts/__init__.py added to make scripts/ importable as a package in tests"
metrics:
  duration: ~20min
  completed: 2026-05-10
  tasks_completed: 3
  files_modified: 5
  files_created: 3
---

# Phase 2 Plan 07: Phase 2 Acceptance Gate Summary

All-20 golden-case acceptance runner, eval scoring extension, and demo readiness gate enforcing D-02/D-05 through D-10/D-38A.

## Tasks Completed

### Task 1: Add all-20 Phase 2 acceptance runner (TDD)

Created `scripts/run_phase2_acceptance.py` with:

- CLI args: `--goldens`, `--coverage-matrix`, `--json-output`, `--markdown-output`, `--artifact-dir`, `--limit`
- Iterates all 20 golden cases by default (`--limit` for local debugging only)
- Calls `run_user_query` from `app.workflow.service` with `WorkflowRunConfig.default().model_copy(update={...})`
- Validates each case against `golden-coverage-matrix.json`
- Rejects `gated`, `stale`, `skipped_with_reason`, `no_candidate`, `ok`, `ok-with-gated-internals` as unacceptable
- Writes `phase2-golden-results.json` and `.md` in normal usage
- Exits non-zero when any unacceptable outcome found (for CI gating)
- Exposes `_check_outcome_acceptability` and `_build_case_result_skeleton` as pure helpers for unit testing

### Task 2: Extend eval scoring for WorkflowResponse outcomes (TDD)

Extended `app/evals/run_eval.py` with:

- `score_phase2_results(results_path: Path, *, coverage_matrix_path: Path | None = None) -> dict[str, Any]`
- Aggregates: `passed`, `needs_clarification`, `not_found`, `failed`, `unacceptable`, `jury_ready`
- Per-case failure rules:
  - `final_outcome=="passed"` and `dataset_count < 1` → `passed_missing_dataset`
  - `final_outcome=="passed"` and `script_count < 1` → `passed_missing_script`
  - `final_outcome=="passed"` and `trace_count < 5` → `passed_trace_too_short`
  - Coverage matrix outcome mismatch → `matrix_outcome_mismatch:expected=...,got=...`
- CLI args added: `--phase2-results`, `--phase2-coverage-matrix`, `--phase2-json-output`, `--phase2-markdown-output`

### Task 3: Make demo readiness depend on Phase 2 acceptance

Extended `app/demo/run_demo.py` with:

- `assess_phase2_readiness(*, phase2_eval: dict, coverage_matrix: dict) -> dict`
- `overall_status = "ready"` only when:
  - `phase2_eval.total_cases == 20`
  - `phase2_eval.failed == 0`
  - `phase2_eval.unacceptable == 0`
  - `coverage_matrix.total_cases == 20`
  - `coverage_matrix.unresolved_data_gaps == []`
- Returns: `phase2_workflow_eval_status`, `phase2_coverage_matrix_status`, `phase2_total_cases`, `phase2_unacceptable_count`

## Commits

| Task | Hash | Description |
|------|------|-------------|
| RED | 72a5376 | test(02-07): add failing RED tests for Phase 2 acceptance runner, eval scoring, and demo readiness |
| GREEN | 2e58b24 | feat(02-07): implement Phase 2 acceptance runner, eval scoring, and demo readiness gate |

## Verification

```
python -m pytest tests/test_phase2_acceptance.py tests/test_eval_runner.py tests/test_demo_readiness.py -q
```

Results: 23 passed, 1 pre-existing failure.

The pre-existing failure (`test_demo_readiness_reports_gates_without_dense_success`) requires Phase 1 source-card artifact files that don't exist in the current worktree (missing: `source-cards-manifest.json`, `source-catalog-manifest.json`, etc.). This test was failing before this plan's changes and is out of scope.

## Deviations from Plan

### Auto-added

**1. [Rule 3 - Blocking] Added scripts/__init__.py for importability**
- **Found during:** Task 1 TDD RED phase
- **Issue:** `scripts/run_phase2_acceptance.py` was not importable via `import scripts.run_phase2_acceptance` in tests because `scripts/` lacked `__init__.py`
- **Fix:** Created `scripts/__init__.py` as a minimal package marker
- **Files modified:** `scripts/__init__.py`
- **Commit:** 2e58b24

## Known Stubs

None — the acceptance runner, eval scorer, and demo readiness gate are fully wired to real workflow service, eval, and readiness paths.

## TDD Gate Compliance

- RED gate (test commit): 72a5376 — `test(02-07): add failing RED tests...`
- GREEN gate (feat commit): 2e58b24 — `feat(02-07): implement Phase 2 acceptance runner...`

Both gates present in correct order. All 21 acceptance tests pass after GREEN commit.

## Self-Check

- `scripts/run_phase2_acceptance.py`: FOUND
- `scripts/__init__.py`: FOUND
- `tests/test_phase2_acceptance.py`: FOUND
- `app/evals/run_eval.py` contains `score_phase2_results`: VERIFIED
- `app/demo/run_demo.py` contains `assess_phase2_readiness`: VERIFIED
- RED commit 72a5376: FOUND
- GREEN commit 2e58b24: FOUND
