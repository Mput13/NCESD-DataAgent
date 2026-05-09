---
phase: 01-data-architecture-research
plan: 01
subsystem: eval-foundation
tags: [requirements-map, golden-cases, eval-rubric, source-bound, trace]

requires: []
provides:
  - Phase 1 requirement-to-evidence traceability for all v1 requirements
  - Twenty structured Russian golden cases for downstream evals
  - Deterministic scoring rubric for source-bound retrieval, embedding/indexing readiness, extraction, no-data, and trace behavior
affects: [01-data-architecture-research, evals, retrieval, data, workflow, ui]

tech-stack:
  added: []
  patterns:
    - Source-bound eval pack before downstream retrieval/extraction implementation
    - Hard-fail rule for unsupported numeric claims
    - Embedding provider and document/query split evidence required for dense retrieval

key-files:
  created:
    - .planning/phases/01-data-architecture-research/requirements-map.md
    - .planning/phases/01-data-architecture-research/golden-cases.yaml
    - .planning/phases/01-data-architecture-research/eval-rubric.md
  modified: []

key-decisions:
  - "Use one canonical Phase 1 evidence map for all v1 requirements; no deprecated phase directories or owner-specific workstreams."
  - "Treat CKAN as a bounded trusted catalog source in goldens and rubric, not as general web search."
  - "Make unsupported numeric claims a hard fail in evaluation before downstream implementation starts."
  - "Require dense retrieval to declare embedding provider/fallback, Yandex document/query modes, and source-card/chunk metadata inputs."

patterns-established:
  - "Golden cases include expected route, expected sources, clarification behavior, artifacts, no-data/rejection behavior, and trace expectations."
  - "Rubric scoring requires cited artifacts or trace/tool outputs for every point."
  - "Dense retrieval evidence embeds source metadata/card chunks only, not raw numeric data or generated answers."

requirements-completed: [NLU-01, NLU-02, NLU-03, NLU-04]

duration: 8min
completed: 2026-05-09T22:30:27Z
---

# Phase 01 Plan 01: Eval Foundation Summary

**Source-bound Phase 1 eval pack with requirement traceability, twenty Russian golden cases, embedding/indexing readiness checks, and deterministic no-unsupported-number scoring**

## Performance

- **Duration:** 8 min
- **Started:** 2026-05-09T22:22:24Z
- **Completed:** 2026-05-09T22:30:27Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- Created a Phase 1 requirements map covering all v1 groups: NLU, SRCH, DATA, ART, RBST, UI, and ENG.
- Added 20 golden cases covering simple, comparative, research, derived metric, ambiguous, no-data, FedStat, World Bank, CKAN-first discovery, rejection visibility, trace completeness, and embedding/indexing readiness.
- Defined a deterministic rubric that scores intent, research-definition fields, clarification behavior, candidate and embedding evidence, coverage preview, extraction evidence, no-data honesty, and trace completeness.

## Task Commits

Each task was committed atomically:

1. **Task 1: Write the Phase 1 requirements map** - `cce9191` (feat)
2. **Task 2: Author the 15-20 case golden set** - `ee90ec0` (feat)
3. **Task 3: Define the evaluation rubric** - `5ac60a2` (feat)
4. **Correction: Require embedding retrieval evidence** - `6bcf7c5` (fix)

**Plan metadata:** captured in the final docs commit for this plan.

## Files Created/Modified

- `.planning/phases/01-data-architecture-research/requirements-map.md` - Maps every v1 requirement to Phase 1 evidence artifacts, deterministic proof, locked decisions, and same-phase follow-up risks.
- `.planning/phases/01-data-architecture-research/golden-cases.yaml` - Defines 20 structured Russian evaluation cases with route, source, artifact, no-data/rejection, trace, and embedding/indexing expectations.
- `.planning/phases/01-data-architecture-research/eval-rubric.md` - Defines hard-fail rules and a 16-point deterministic rubric for every golden case, including provider/fallback and embedding input-format evidence.

## Decisions Made

- Kept all traceability inside the single canonical `.planning/phases/01-data-architecture-research` directory.
- Made CKAN a first-class trusted catalog source in the eval pack while preserving the bounded package/resource-search constraint.
- Required hard failure for any unsupported numeric claim, aligning downstream evals with D-12 before implementation begins.
- Required dense retrieval evidence to declare embedding provider/model family or credential-aware fallback, Yandex `text-search-doc`/`text-search-query` split when used, and source-card/chunk metadata input text.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Used `python3` for YAML verification**
- **Found during:** Task 2 (Author the 15-20 case golden set)
- **Issue:** The plan's acceptance command invokes `python`, but this shell has no `python` executable.
- **Fix:** Ran the identical YAML validation body with `python3`.
- **Files modified:** None.
- **Verification:** `python3` validation passed with 20 cases and all required categories/sources.
- **Committed in:** `ee90ec0` (task artifact commit)

---

**Total deviations:** 1 auto-fixed (1 blocking environment issue)
**Impact on plan:** Verification semantics were unchanged; only the interpreter executable name differed.

## Issues Encountered

- Concurrent Plan 01-02 work appeared in the worktree and git history while this executor was running. Unrelated 01-02 files and commits were left untouched.
- User/orchestrator correction required embedding/indexing readiness to be explicit in the 01-01 foundation pack. This was incorporated before final summary/state commit in `6bcf7c5`.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plans 01-02 through 01-05 can now target the shared eval pack. Downstream implementation should preserve the source-bound contract: every scoreable claim needs a cited artifact, trace event, or deterministic tool output, and dense retrieval must use source-card/chunk metadata rather than raw numeric data.

## Self-Check: PASSED

- Found created files: `requirements-map.md`, `golden-cases.yaml`, `eval-rubric.md`, and `01-01-SUMMARY.md`.
- Found task/correction commits: `cce9191`, `ee90ec0`, `5ac60a2`, and `6bcf7c5`.
- Summary markdown passed `git diff --check`.

---
*Phase: 01-data-architecture-research*
*Completed: 2026-05-09T22:30:27Z*
