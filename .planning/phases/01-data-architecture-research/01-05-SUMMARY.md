---
phase: 01-data-architecture-research
plan: 05
subsystem: demo-readiness-decision-package
tags: [demo, streamlit, qdrant, readiness, trace, recommendations]

requires:
  - phase: 01-data-architecture-research
    provides: Plans 01-04 golden cases, prepared corpus/catalog, Qdrant manifest, retrieval eval, extraction probes, graph trace artifacts, and data relevance eval
provides:
  - Demo readiness runner over prepared source-card, catalog, corpus, Qdrant, retrieval, extraction, and data relevance artifacts
  - Minimal diagnostic Streamlit shell for chat input, example prompts, state machine, trace, artifacts, rejection details, index readiness, and feedback/fix requests
  - Prepared-data readiness report and generated demo-readiness JSON
  - Final recommendation package, implementation decision brief, and architecture growth map
affects: [phase-01-verification, streamlit-demo, qdrant-readiness, deterministic-extraction]

tech-stack:
  added: [streamlit]
  patterns:
    - Demo readiness is evidence-driven and reports gated states instead of silent success
    - Dense retrieval is ready only when Qdrant manifest, corpus hash, collection, and vector evidence agree
    - Streamlit consumes the demo/readiness path and WorkflowTraceViewModel rather than duplicating product logic

key-files:
  created:
    - app/demo/__init__.py
    - app/demo/run_demo.py
    - app/ui/streamlit_app.py
    - tests/test_demo_readiness.py
    - .planning/phases/01-data-architecture-research/demo-readiness.json
    - .planning/phases/01-data-architecture-research/prepared-data-readiness.md
    - .planning/phases/01-data-architecture-research/final-recommendation.md
    - .planning/phases/01-data-architecture-research/implementation-decision-brief.md
    - .planning/phases/01-data-architecture-research/architecture-growth-map.md
  modified:
    - requirements.txt
    - .planning/phases/01-data-architecture-research/trace-ui-demo.md
    - .planning/ROADMAP.md
    - .planning/STATE.md

key-decisions:
  - "Report the current integrated demo path as gated, not ready, because dense Qdrant vectors and numeric extraction outputs are not yet available."
  - "Use the prepared manifests as the source of demo readiness truth; rebuilding and re-embedding are exceptional recovery paths."
  - "Defer UI polish until data relevance, Qdrant readiness, and deterministic extraction are correct."

patterns-established:
  - "app.demo.run_demo assesses prepared data, index, retrieval, extraction, and data relevance artifacts before UI presentation."
  - "app.ui.streamlit_app imports the demo/readiness runner and WorkflowTraceViewModel, preserving trace ownership."
  - "Final decision docs rank recommendations by data relevance, Qdrant readiness, deterministic reliability, implementation risk, and demo readiness."

requirements-completed:
  - NLU-02
  - NLU-03
  - NLU-04
  - SRCH-04

duration: 9 min
completed: 2026-05-10
---

# Phase 01 Plan 05: Demo Readiness and Decision Package Summary

**Prepared-data demo readiness runner, diagnostic Streamlit trace shell, and final recommendation package with explicit Qdrant/extraction gates**

## Performance

- **Duration:** 9 min
- **Started:** 2026-05-10T04:28:38Z
- **Completed:** 2026-05-10T04:37:04Z
- **Tasks:** 2
- **Files modified:** 14

## Accomplishments

- Added `app/demo/run_demo.py`, which consumes source-card, catalog, embedding corpus, Qdrant index, retrieval eval, extraction probes, and data relevance eval artifacts and writes `demo-readiness.json`.
- Added `app/ui/streamlit_app.py`, a minimal diagnostic Streamlit shell with chat input, 6 example prompts, state machine, live trace, answer/artifact area, selected/rejected source details, index readiness, and feedback/fix request payloads.
- Wrote prepared-data readiness, final recommendation, implementation decision, and architecture growth documents that preserve the source-bound, Qdrant-backed, deterministic extraction priorities.
- Updated project state and roadmap so Phase 1 is ready for `$gsd-verify-work 1`.

## Task Commits

1. **Task 1: Integrate demo readiness over the prepared corpus/index** - `95aab09` (feat)
2. **Task 2: Assemble final recommendation package and close Plan 05** - this summary/docs commit

## Files Created/Modified

- `app/demo/run_demo.py` - Demo readiness CLI and payload builder that refuses false dense readiness.
- `app/ui/streamlit_app.py` - Diagnostic Streamlit shell consuming the readiness runner and trace view model.
- `tests/test_demo_readiness.py` - Regression tests for readiness gates and UI import smoke.
- `.planning/phases/01-data-architecture-research/demo-readiness.json` - Generated machine-readable readiness output.
- `.planning/phases/01-data-architecture-research/prepared-data-readiness.md` - Corpus/catalog/Qdrant/retrieval/extraction/UI readiness report.
- `.planning/phases/01-data-architecture-research/final-recommendation.md` - Ranked recommendation package.
- `.planning/phases/01-data-architecture-research/implementation-decision-brief.md` - Accepted decisions, rejected options, risks, verification, and rebuild policy.
- `.planning/phases/01-data-architecture-research/architecture-growth-map.md` - Growth path from Phase 1 slice to the full architecture stack.
- `.planning/phases/01-data-architecture-research/trace-ui-demo.md` - Expanded trace UI contract for prepared index, Qdrant, data relevance, and fix requests.
- `.planning/ROADMAP.md`, `.planning/STATE.md` - Mark Plan 05 complete and Phase 1 ready for verification.
- `requirements.txt` - Adds Streamlit for the diagnostic UI target.

## Verification

Commands run successfully:

```bash
rg -n "embedding-index-manifest|source-cards-manifest|data-relevance-eval|qdrant|gated_skip|prepared|rebuild" app/demo/run_demo.py .planning/phases/01-data-architecture-research/prepared-data-readiness.md
rg -n "streamlit|st\\.chat_input|example prompts|state machine|live trace|artifacts|rejected|FeedbackRequest|FixRequest|diagnostic|run_demo" app/ui/streamlit_app.py
rg -n "State machine|Trace timeline|Artifacts panel|Feedback and fix requests|index readiness|prepared index|Qdrant|data relevance" .planning/phases/01-data-architecture-research/trace-ui-demo.md
python3 -m app.demo.run_demo --source-cards-manifest .planning/phases/01-data-architecture-research/source-cards-manifest.json --source-catalog-manifest .planning/phases/01-data-architecture-research/source-catalog-manifest.json --embedding-corpus-manifest .planning/phases/01-data-architecture-research/embedding-corpus-manifest.json --index-manifest .planning/phases/01-data-architecture-research/embedding-index-manifest.json --retrieval-eval .planning/phases/01-data-architecture-research/retrieval-eval.csv --extraction-probes .planning/phases/01-data-architecture-research/extraction-probes.json --data-relevance-eval .planning/phases/01-data-architecture-research/data-relevance-eval.json --json-output .planning/phases/01-data-architecture-research/demo-readiness.json
python3 -m pytest -q
```

Full suite result: `26 passed`.

Note: this shell has `python3` but no `python` executable, so the plan's `python -m app.demo.run_demo ...` command was verified with `python3 -m app.demo.run_demo ...`.

## Decisions Made

- The integrated demo is currently `gated`: it can show prepared data, Qdrant contract, retrieval/eval gates, extraction probes, trace, artifacts, and feedback, but it cannot honestly claim dense Qdrant readiness or numeric answer readiness yet.
- Rebuild/reprocess is not the default next action; manifests and the Qdrant contract are preserved unless they become missing or stale.
- UI polish remains secondary to source relevance, Qdrant readiness, and deterministic extraction evidence.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The local shell lacks a `python` executable. Verification used `python3`; all Python module behavior passed.
- Existing evidence still records Yandex embedding credentials as missing, so Qdrant dense retrieval remains `gated_skip`.
- Extraction remains probe-level for numeric output; deterministic DatasetArtifact rows still need promoted cases.

## User Setup Required

Optional for Streamlit UI:

```bash
python3 -m streamlit run app/ui/streamlit_app.py
```

Optional for dense vector population: set the Yandex embedding credentials listed in `embedding-index-manifest.json`, then run that manifest's `rebuild_command`.

## Next Phase Readiness

Phase 1 is ready for `$gsd-verify-work 1`. Verification should focus on whether the whole milestone honestly demonstrates source relevance, Qdrant status, deterministic extraction boundaries, trace/artifact visibility, and remaining demo gates.

## Self-Check: PASSED

- Found created code files: `app/demo/run_demo.py`, `app/ui/streamlit_app.py`, and `tests/test_demo_readiness.py`.
- Found created artifacts: `demo-readiness.json`, `prepared-data-readiness.md`, `final-recommendation.md`, `implementation-decision-brief.md`, `architecture-growth-map.md`, and `01-05-SUMMARY.md`.
- Acceptance greps passed for readiness markers, Streamlit diagnostics, trace UI contract, recommendation scoring dimensions, decision brief sections, and growth map sections.
- Full pytest suite passed: `26 passed`.

---
*Phase: 01-data-architecture-research*
*Completed: 2026-05-10*
