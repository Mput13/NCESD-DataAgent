---
phase: 02-jury-mvp
plan: "09"
subsystem: retrieval-infra
tags: [qdrant, embeddings, readiness, docker, retrieval]
requires:
  - phase: 01-data-architecture-research
    provides: [embedding corpus, embedding cache, source-card manifests]
provides:
  - Shared Docker Qdrant server runtime for Phase 2
  - Cache-first promotion script for Phase 1 embeddings
  - Strict Phase 2 index readiness probe and server manifest evidence
affects: [retrieval, evals, workflow, streamlit, demo-readiness]
tech-stack:
  added: [docker-compose-qdrant]
  patterns: [server-manifest-readiness, cache-first-vector-promotion]
key-files:
  created: [docker-compose.qdrant.yml, app/retrieval/readiness.py, scripts/promote_qdrant_server.py, .planning/phases/02-jury-mvp/qdrant-server-manifest.json]
  modified: [.env.example, .planning/phases/01-data-architecture-research/embedding-index-manifest.json, tests/test_phase2_qdrant_server.py]
key-decisions:
  - "Phase 2 jury readiness is based on Qdrant server manifest evidence, not embedded local storage."
  - "Promotion reuses the Phase 1 embedding cache by default and requires --allow-reembed for missing cache coverage."
  - "The stale Phase 1 embedding-index manifest is refreshed after verified server promotion so downstream probes do not read gated metadata."
patterns-established:
  - "Readiness requires matching corpus hash, vector count, server URL, collection, and reproduce command."
  - "Server promotion writes reproducible evidence only after inspecting or populating the Qdrant collection."
requirements-completed: [SRCH-01, SRCH-02, SRCH-03, SRCH-04, ENG-01, ENG-03]
duration: 6min
completed: 2026-05-10
---

# Phase 02 Plan 09: Qdrant Server Runtime Summary

**Qdrant server mode is now runnable, populated from the 36,321-vector Phase 1 embedding cache, and guarded by strict server-manifest readiness checks.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-10T11:50:18Z
- **Completed:** 2026-05-10T11:56:12Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- Added `docker-compose.qdrant.yml` for a shared Qdrant server on ports `6333` and `6334`, with storage in `.local/qdrant-server`.
- Added `scripts/promote_qdrant_server.py` to start/validate the server, promote cached embeddings, skip ready collections, and write reproducible manifest evidence.
- Added `app/retrieval/readiness.py` so Phase 2 readiness rejects local embedded mode, stale corpus hashes, missing server evidence, and wrong vector counts.
- Produced `.planning/phases/02-jury-mvp/qdrant-server-manifest.json` with `status=ready`, `vector_count=36321`, current corpus hash, collection, URL, timestamp, and reproduce command.

## Task Commits

1. **Task 1: Configure Qdrant server as the Phase 2 runtime** - `ee5b011` (test), `11e4da4` (feat)
2. **Task 2: Promote the Phase 1 embedding cache into server Qdrant** - `346d2a3` (test), `9658228` (feat)
3. **Task 3: Verify and freeze server-mode readiness evidence** - `8394255` (test), `7e0a4bc` (feat)

## Files Created/Modified

- `docker-compose.qdrant.yml` - Shared Qdrant server definition.
- `.env.example` - Documents `QDRANT_URL=http://localhost:6333` and server-mode Phase 2 default.
- `app/retrieval/readiness.py` - Phase 2 index/server readiness assessment.
- `scripts/promote_qdrant_server.py` - Cache-first promotion and manifest writer.
- `.planning/phases/02-jury-mvp/qdrant-server-manifest.json` - Verified server collection evidence.
- `.planning/phases/01-data-architecture-research/embedding-index-manifest.json` - Refreshed to the promoted server collection.
- `tests/test_phase2_qdrant_server.py` - Server runtime, promotion, and readiness tests.

## Decisions Made

- Server-mode evidence is required before Phase 2 can claim dense retrieval readiness.
- Embedded local Qdrant with more than 20,000 vectors is treated as a warning and not a jury-ready runtime.
- Cache promotion is the default; re-embedding is an explicit opt-in through `--allow-reembed`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Refreshed stale index manifest after server promotion**
- **Found during:** Task 3 (Verify and freeze server-mode readiness evidence)
- **Issue:** The real server manifest was ready, but the existing Phase 1 `embedding-index-manifest.json` still said `gated_skip` with the stale 11-card corpus hash, causing readiness to reject the verified server collection.
- **Fix:** Updated `scripts/promote_qdrant_server.py` to refresh the index manifest from verified server evidence after successful promotion.
- **Files modified:** `scripts/promote_qdrant_server.py`, `.planning/phases/01-data-architecture-research/embedding-index-manifest.json`
- **Verification:** `assess_phase2_index_readiness(...)` returns `ready=True` with 36,321 vectors and no reasons.
- **Committed in:** `7e0a4bc`

---

**Total deviations:** 1 auto-fixed (Rule 2)
**Impact on plan:** Required for correctness; without it downstream retrieval/eval code would still see stale gated index metadata.

## Issues Encountered

Docker Desktop was installed but not running. It was started locally with `open -a Docker`, then the planned compose and promotion commands completed successfully.

## Verification

- `docker compose -f docker-compose.qdrant.yml up -d qdrant`
- `python3 scripts/promote_qdrant_server.py --start-server --manifest-output .planning/phases/02-jury-mvp/qdrant-server-manifest.json`
- `python3 -m pytest tests/test_phase2_qdrant_server.py tests/test_embedding_index.py -q`

Result: `8 passed`.

## Known Stubs

None.

## User Setup Required

None for this environment. Docker must be running before re-running the promotion command.

## Next Phase Readiness

Downstream Phase 2 retrieval, eval, workflow, and Streamlit work can use `QDRANT_URL=http://localhost:6333`, collection `phase1_source_cards`, and `.planning/phases/02-jury-mvp/qdrant-server-manifest.json` as readiness evidence.

## Self-Check: PASSED

- Required files exist.
- Task commits exist in git history.
- Verification commands passed.

---
*Phase: 02-jury-mvp*
*Completed: 2026-05-10*
