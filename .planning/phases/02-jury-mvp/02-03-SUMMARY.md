---
phase: 02-jury-mvp
plan: "03"
subsystem: data
tags: [fedstat, world-bank, parquet, duckdb, pyarrow, deterministic-extraction]
requires:
  - phase: 01-data-architecture-research
    provides: source-card contracts, workflow artifacts, deterministic tool seeds, golden cases
provides:
  - FedStat wide Parquet coverage preview and canonical extraction adapter
  - World Bank long Parquet coverage preview, country/group aliases, and canonical extraction adapter
  - Dataset export helper returning typed ScriptArtifact reproducibility scripts
affects: [02-jury-mvp, workflow, evals, artifacts, deterministic-tools]
tech-stack:
  added: []
  patterns:
    - Source-bound adapters read Parquet through PyArrow metadata and DuckDB row scans
    - DatasetArtifact records use one canonical long-row schema across source families
    - ScriptArtifact objects carry downloadable reproducibility script metadata
key-files:
  created:
    - app/data/fedstat_adapter.py
    - app/data/world_bank_adapter.py
    - tests/test_phase2_extraction_adapters.py
  modified:
    - app/artifacts/workflow_artifacts.py
    - app/data/deterministic_tools.py
    - tests/test_deterministic_tools_and_trace.py
key-decisions:
  - "FedStat wide tables normalize technical column Parquet by treating the first row as logical headers."
  - "World Bank group aliases expand to country ISO3 lists while aggregate rows are excluded unless explicitly requested."
  - "Dataset reproducibility scripts are typed ScriptArtifact objects, not ad hoc metadata dictionaries."
patterns-established:
  - "Canonical dataset columns are shared by FedStat and World Bank adapters."
  - "Derived metrics such as first-available normalization are computed in adapter code."
requirements-completed: [DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, ART-04, ART-05, ART-06, RBST-04, ENG-02]
duration: 6min
completed: 2026-05-10T11:55:38Z
---

# Phase 2 Plan 03: Deterministic Extraction Adapters Summary

**FedStat and World Bank Parquet adapters now produce source-bound DatasetArtifact rows, exports, and typed reproducibility scripts without an LLM numeric path.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-10T11:50:02Z
- **Completed:** 2026-05-10T11:55:38Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- Added `preview_fedstat_coverage` and `extract_fedstat_dataset` for first-row-header FedStat wide Parquet normalization into canonical long rows.
- Added `preview_world_bank_coverage`, `extract_world_bank_dataset`, and `normalize_first_available_to_100` for long-format World Bank data, aliases, BRICS/EAEU expansion, and code-computed derived metrics.
- Added `export_dataset_with_script` so downstream workflow plans can carry `ScriptArtifact` objects directly into Phase 2 state and final responses.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement FedStat wide Parquet adapter** - `55c5be5` (feat)
2. **Task 2: Implement World Bank long Parquet adapter** - `7946358` (feat)
3. **Task 3: Route deterministic exports through shared helpers** - `46e6f82` (feat)

## Files Created/Modified

- `app/data/fedstat_adapter.py` - FedStat coverage preview and deterministic extraction from wide Parquet into canonical rows.
- `app/data/world_bank_adapter.py` - World Bank coverage preview, alias/group expansion, aggregate exclusion, extraction, and normalization.
- `app/data/deterministic_tools.py` - Adds `export_dataset_with_script` returning typed `ScriptArtifact`.
- `app/artifacts/workflow_artifacts.py` - Extends `ScriptArtifact` with downloadable path, source dataset, checksum, and display metadata fields.
- `tests/test_phase2_extraction_adapters.py` - Synthetic Parquet tests for FedStat and World Bank adapters.
- `tests/test_deterministic_tools_and_trace.py` - Script artifact validation for deterministic exports.

## Decisions Made

- FedStat technical columns matching `column0*` are interpreted as first-row-header tables, because this reflects the known FedStat dump pattern.
- World Bank named sets are expanded into country ISO3 lists (`BRICS`, `EAEU`) and aggregates such as `EUU` are filtered out unless the request names that aggregate directly.
- Script export metadata lives in `ScriptArtifact` so later graph/finalization code can pass typed artifacts without lossy dict conversion.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Extended ScriptArtifact fields required by deterministic export**
- **Found during:** Task 3 (Route deterministic exports through shared helpers)
- **Issue:** Parallel response-contract work had introduced `ScriptArtifact`, but it did not yet expose `path`, `source_dataset_artifact_id`, `sha256`, or downloadable display metadata required by this plan.
- **Fix:** Added backward-compatible optional fields to `ScriptArtifact` and populated them in `export_dataset_with_script`.
- **Files modified:** `app/artifacts/workflow_artifacts.py`, `app/data/deterministic_tools.py`
- **Verification:** `python3 -m pytest tests/test_phase2_extraction_adapters.py tests/test_deterministic_tools_and_trace.py -q`
- **Committed in:** `46e6f82`

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Required for the typed script artifact contract; no scope expansion beyond the plan.

## Issues Encountered

- PyArrow does not infer a single Parquet column with mixed header strings and numeric values. The FedStat fixture uses string-like technical columns and the adapter coerces extracted period values to numbers, matching the first-row-header dump pattern.
- Concurrent Phase 2 changes were present in `app/retrieval/readiness.py`, `scripts/promote_qdrant_server.py`, and `qdrant-server-manifest.json`; they were left unstaged.

## Known Stubs

None. Optional `None` fields in artifact models are schema defaults, not placeholder UI/data stubs.

## User Setup Required

None - no external service configuration required.

## Verification

- `python3 -m pytest tests/test_phase2_extraction_adapters.py tests/test_deterministic_tools_and_trace.py -q` - 5 passed

## Next Phase Readiness

Plans 02-05 and 02-06 can dispatch source-family extraction to these adapters and carry both `DatasetArtifact` and `ScriptArtifact` objects through `Phase2State` and `WorkflowResponse`.

## Self-Check: PASSED

- Created/modified files listed in this summary exist.
- Task commits `55c5be5`, `7946358`, and `46e6f82` exist in git history.
- Plan verification command passed with 5 tests.

---
*Phase: 02-jury-mvp*
*Completed: 2026-05-10*
