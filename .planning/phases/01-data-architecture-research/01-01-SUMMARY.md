---
phase: 01-data-architecture-research
plan: 01
subsystem: evaluation-foundation
tags: [requirements, golden-cases, eval-rubric, source-bound, traceability]

requires:
  - phase: project-planning
    provides: PROJECT, REQUIREMENTS, ROADMAP, STATE, architecture stack, and data report constraints
provides:
  - Requirement-to-artifact traceability for all v1 requirement IDs
  - Twenty source-bound golden cases spanning simple, comparative, research, derived metric, ambiguous, and no-data routes
  - Deterministic evaluation rubric for intent, evidence, extraction, rejection/no-data honesty, and trace completeness
affects: [01-data-architecture-research, retrieval, extraction, orchestration, streamlit-demo, evals]

tech-stack:
  added: []
  patterns:
    - Source-bound golden cases with expected artifacts and trace expectations
    - Hard-fail rubric for unsupported numeric claims
    - Credential-aware Yandex/Qwen skip handling without changing the target stack

key-files:
  created:
    - .planning/phases/01-data-architecture-research/requirements-map.md
    - .planning/phases/01-data-architecture-research/golden-cases.yaml
    - .planning/phases/01-data-architecture-research/eval-rubric.md
  modified:
    - .planning/phases/01-data-architecture-research/requirements-map.md
    - .planning/phases/01-data-architecture-research/golden-cases.yaml
    - .planning/phases/01-data-architecture-research/eval-rubric.md

key-decisions:
  - "Use the existing verified task commits as the atomic task commits for Plan 01; the working tree was clean and all acceptance gates passed."
  - "Evaluate Phase 1 outputs on structured artifacts and trace evidence, not final answer prose alone."
  - "Unsupported numeric claims are hard failures unless backed by deterministic tool, extraction, coverage, or trusted adapter provenance."

patterns-established:
  - "Golden cases define expected route, sources, artifacts, no-data/rejection behavior, and trace expectations."
  - "Evaluation requires source cards, coverage preview, deterministic extraction evidence, rejection/no-data honesty, and trace completeness."

requirements-completed:
  - NLU-01
  - NLU-02
  - NLU-03
  - NLU-04

duration: 1 min
completed: 2026-05-10
---

# Phase 01 Plan 01: Evaluation Foundation Summary

**Source-bound evaluation pack with full v1 traceability, twenty golden cases, and deterministic rubric gates for numeric evidence**

## Performance

- **Duration:** 1 min
- **Started:** 2026-05-10T00:45:22Z
- **Completed:** 2026-05-10T00:46:05Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- Mapped all v1 requirement IDs to Phase 1 evidence artifacts inside the single canonical phase directory.
- Added 20 golden cases covering simple, comparative, research, derived metric, ambiguous, no-data, FedStat, World Bank, CKAN-first discovery, rejection visibility, trace completeness, and embedding readiness.
- Defined a deterministic rubric that fails unsupported numeric claims, scores structured evidence, and records skipped Yandex-dependent checks as credential gates while preserving the Qwen/Yandex target.

## Task Commits

Each task artifact has an atomic commit in history:

1. **Task 1: Write the Phase 1 requirements map** - `cce9191` (`feat`)
2. **Task 2: Author the 15-20 case golden set** - `ee90ec0` (`feat`)
3. **Task 3: Define the evaluation rubric** - `5ac60a2` (`feat`)

Additional hardening affecting all three artifacts:

- `6bcf7c5` (`fix`) - require embedding retrieval evidence across the requirements map, golden cases, and rubric.

## Files Created/Modified

- `.planning/phases/01-data-architecture-research/requirements-map.md` - Requirement-to-evidence table covering all v1 requirements and locked decisions.
- `.planning/phases/01-data-architecture-research/golden-cases.yaml` - Twenty structured source-bound evaluation cases.
- `.planning/phases/01-data-architecture-research/eval-rubric.md` - Deterministic scoring and hard-fail rules for downstream eval runs.

## Verification

Commands run successfully:

```bash
rg -n "NLU-01|SRCH-01|DATA-01|ART-01|RBST-01|UI-01|ENG-01" .planning/phases/01-data-architecture-research/requirements-map.md
rg -n "Single active Phase 1 — implementation evidence required" .planning/phases/01-data-architecture-research/requirements-map.md
PATH="$PWD/.local/bin:$PATH" python - <<'PY'
import yaml, pathlib
p = pathlib.Path('.planning/phases/01-data-architecture-research/golden-cases.yaml')
data = yaml.safe_load(p.read_text())
assert isinstance(data, list)
assert 15 <= len(data) <= 20
cats = {item['category'] for item in data}
need = {'simple','comparative','research','derived_metric','ambiguous','no_data'}
assert need.issubset(cats)
assert any('CKAN' in str(item.get('expected_sources')) for item in data)
assert any('FedStat' in str(item.get('expected_sources')) for item in data)
assert any('World Bank' in str(item.get('expected_sources')) for item in data)
print(len(data), sorted(cats))
PY
rg -n "unsupported numeric claim|trace completeness|coverage-preview evidence|skipped Yandex-dependent checks" .planning/phases/01-data-architecture-research/eval-rubric.md
PATH="$PWD/.local/bin:$PATH" python - <<'PY'
from pathlib import Path
import re
req = Path('.planning/REQUIREMENTS.md').read_text()
ids = []
for prefix in ['NLU','SRCH','DATA','ART','RBST','UI','ENG']:
    ids.extend(re.findall(rf'\b{prefix}-\d{{2}}\b', req))
ids = sorted(set(ids))
text = Path('.planning/phases/01-data-architecture-research/requirements-map.md').read_text()
missing = [i for i in ids if i not in text]
assert not missing, missing
print(f'all {len(ids)} v1 requirement IDs mapped')
PY
rg -n "=\[\]|=\{\}|=null|=\"\"|not available|coming soon|placeholder|TODO|FIXME|mock data" .planning/phases/01-data-architecture-research/requirements-map.md .planning/phases/01-data-architecture-research/golden-cases.yaml .planning/phases/01-data-architecture-research/eval-rubric.md || true
```

## Decisions Made

- Existing clean-tree artifacts were verified and recorded instead of rewriting equivalent content for artificial churn.
- The evaluation foundation treats artifact evidence and trace completeness as first-class outputs.
- Numeric claims remain source-bound: any unsupported numeric claim fails the case.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Manually updated GSD state fields not handled by project-specific STATE format**
- **Found during:** Metadata update after Task 3
- **Issue:** `state advance-plan` could not parse the custom narrative `STATE.md`, and `state record-metric` reported that no Performance Metrics section existed.
- **Fix:** Updated `STATE.md`, `ROADMAP.md`, and `REQUIREMENTS.md` directly after successful `state update-progress`, `roadmap update-plan-progress`, `requirements mark-complete`, and `state record-session` tool runs.
- **Files modified:** `.planning/STATE.md`, `.planning/ROADMAP.md`, `.planning/REQUIREMENTS.md`
- **Verification:** `git diff` and targeted `rg` checks confirmed completed plan count, next action, roadmap checkbox, requirement completion, and session continuity.
- **Committed in:** final metadata commit

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Metadata state was brought into sync without changing implementation scope.

## Issues Encountered

- `state advance-plan` and `state record-metric` did not support the current `STATE.md` layout. Resolved by direct metadata edits and documented above.

## Known Stubs

None found in the created/modified plan artifacts.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for `01-02-PLAN.md`. Downstream source-card builders, retrieval work, extraction probes, orchestration, and Streamlit diagnostics can now target the golden cases and deterministic rubric directly.

## Self-Check: PASSED

- Found created artifacts: `requirements-map.md`, `golden-cases.yaml`, `eval-rubric.md`, and `01-01-SUMMARY.md`.
- Found task commits: `cce9191`, `ee90ec0`, `5ac60a2`.
- Found supplemental hardening commit: `6bcf7c5`.

---
*Phase: 01-data-architecture-research*
*Completed: 2026-05-10*
