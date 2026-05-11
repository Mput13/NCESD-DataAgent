---
phase: 01-data-architecture-research
plan: 03
subsystem: retrieval-index
tags: [qdrant, embeddings, yandex-ai-studio, bm25, retrieval-eval, source-bound]

requires:
  - phase: 01-data-architecture-research
    provides: Plan 01 golden cases/eval rubric and Plan 02 source-card embedding corpus manifest
provides:
  - Qdrant-backed embedding index abstraction for source-card chunks
  - Credential-aware Yandex document/query embedding build path with durable manifest/build log
  - Hybrid lexical BM25/FTS, dense Qdrant, and bge-reranker-compatible retrieval interface
  - Retrieval comparison report and per-case retrieval eval CSV over golden cases
affects: [qdrant-indexing, retrieval, orchestration, extraction, streamlit-demo, evals]

tech-stack:
  added: [qdrant-client, PyYAML]
  patterns:
    - Qdrant is the mandatory vector-store abstraction for dense retrieval
    - Missing Yandex embedding credentials gate vector population without replacing Qdrant
    - Retrieval eval rows always expose dense status, rerank status, source-family match, and rejection reasons

key-files:
  created:
    - app/retrieval/__init__.py
    - app/retrieval/embedding_index.py
    - app/retrieval/hybrid_retrieval.py
    - scripts/build_embedding_index.py
    - scripts/run_retrieval_spike.py
    - .planning/phases/01-data-architecture-research/embedding-index-build.md
    - .planning/phases/01-data-architecture-research/embedding-index-manifest.json
    - .planning/phases/01-data-architecture-research/retrieval-comparison.md
    - .planning/phases/01-data-architecture-research/retrieval-eval.csv
    - tests/test_embedding_index.py
    - tests/test_hybrid_retrieval.py
  modified:
    - requirements.txt

key-decisions:
  - "Use Qdrant local persistent mode by default (`QDRANT_MODE=local`, `QDRANT_PATH=.local/qdrant`) while keeping remote Qdrant configurable through `QDRANT_URL`."
  - "Treat absent Yandex embedding credentials as a gated vector-population status, not a reason to substitute a custom local vector index."
  - "Use a deterministic BM25/FTS-style lexical retrieval and bge-reranker-v2-m3-compatible fallback so retrieval eval remains executable without external credentials."

patterns-established:
  - "Embedding index manifests record provider/model URIs, dimensions, chunk count, corpus hash, metadata version, Qdrant config, local artifact paths, and rebuild command."
  - "Hybrid retrieval reads the prepared index manifest and preserves dense/rerank status on every eval row."

requirements-completed:
  - SRCH-01
  - SRCH-02
  - SRCH-03
  - SRCH-04
  - NLU-04

duration: 7 min
completed: 2026-05-10
---

# Phase 01 Plan 03: Materialized Embedding/Search Index Summary

**Qdrant-backed source-card embedding index path with credential-gated Yandex vectors and executable hybrid retrieval eval**

## Performance

- **Duration:** 7 min
- **Started:** 2026-05-10T00:57:10Z
- **Completed:** 2026-05-10T01:04:25Z
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments

- Added `app/retrieval/embedding_index.py` and `scripts/build_embedding_index.py` with Yandex `text-search-doc` / `text-search-query` split, `YANDEX_EMBEDDING_DIMENSIONS=256`, Qdrant local/remote configuration, collection creation/upsert/search wrappers, and explicit `gated_skip` status.
- Generated `.planning/phases/01-data-architecture-research/embedding-index-manifest.json` and `embedding-index-build.md`; current local status is `gated_skip` because `YANDEX_AI_STUDIO_API_KEY` or `YANDEX_EMBEDDING_API_KEY` is absent, while Qdrant config and collection name are preserved.
- Added `app/retrieval/hybrid_retrieval.py` and `scripts/run_retrieval_spike.py` with lexical BM25/FTS approximation, dense Qdrant seam, bge-reranker-v2-m3-compatible fallback, rejection reasons, and CSV evidence over eight bounded golden cases.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement the embedding provider and materialized index builder**
   - `7e3f369` test: add failing embedding index tests
   - `80a644f` feat: implement Qdrant embedding index builder
2. **Task 2: Implement hybrid retrieval over the prepared index and evaluate it**
   - `4f9a9b6` test: add failing hybrid retrieval tests
   - `e008d1a` feat: implement hybrid retrieval evaluation

Additional hardening:

- `91227ce` fix: keep index manifest rebuilds idempotent.

## Files Created/Modified

- `app/retrieval/embedding_index.py` - Yandex embedding provider, credential gate status, Qdrant client/collection wrapper, cosine distance, and corpus loader.
- `scripts/build_embedding_index.py` - Long-running index build entrypoint that writes ready or gated-skip manifests/logs.
- `app/retrieval/hybrid_retrieval.py` - Lexical BM25/FTS retriever, dense Qdrant retriever, bge-compatible reranker seam, and hybrid result model.
- `scripts/run_retrieval_spike.py` - Golden-case retrieval evaluator producing CSV and comparison report.
- `.planning/phases/01-data-architecture-research/embedding-index-manifest.json` - Durable prepared-index manifest.
- `.planning/phases/01-data-architecture-research/embedding-index-build.md` - Build log and credential-gate evidence.
- `.planning/phases/01-data-architecture-research/retrieval-comparison.md` - Retrieval stack comparison and skipped-evidence behavior.
- `.planning/phases/01-data-architecture-research/retrieval-eval.csv` - Per-case retrieval evidence.
- `tests/test_embedding_index.py`, `tests/test_hybrid_retrieval.py` - TDD coverage for index and retrieval contracts.
- `requirements.txt` - Added `qdrant-client` and `PyYAML`.

## Verification

Commands run successfully:

```bash
PATH="$PWD/.local/bin:$PATH" python3 -m pip install -r requirements.txt
PATH="$PWD/.local/bin:$PATH" python3 -m pytest tests/test_embedding_index.py
PATH="$PWD/.local/bin:$PATH" python3 -m pytest tests/test_hybrid_retrieval.py
PATH="$PWD/.local/bin:$PATH" python scripts/build_embedding_index.py --corpus-manifest .planning/phases/01-data-architecture-research/embedding-corpus-manifest.json --manifest .planning/phases/01-data-architecture-research/embedding-index-manifest.json --build-log .planning/phases/01-data-architecture-research/embedding-index-build.md
PATH="$PWD/.local/bin:$PATH" python scripts/run_retrieval_spike.py --goldens .planning/phases/01-data-architecture-research/golden-cases.yaml --index-manifest .planning/phases/01-data-architecture-research/embedding-index-manifest.json --output .planning/phases/01-data-architecture-research/retrieval-eval.csv
PATH="$PWD/.local/bin:$PATH" python3 -m pytest
```

Full test suite result: `14 passed`.

Manifest validation confirmed `vector_store=qdrant`, `collection_name=phase1_source_cards`, `qdrant_mode=local`, `chunk_count=11`, corpus hash present, and `dense_status=gated_skip` with missing credential evidence. Retrieval validation confirmed eight eval rows with `relevance_score`, `source_family_match`, `rejection_reasons`, `dense_status`, `rerank_status`, `index_manifest_status`, and `qdrant_collection`.

## Decisions Made

- Qdrant local persistent mode is the default Phase 1 mode, with server/remote Qdrant supported by environment configuration rather than retrieval code changes.
- Missing Yandex embedding credentials gate only vector population and query embedding; the Qdrant manifest, collection abstraction, dense status, and rebuild command remain materialized.
- The reranker path exposes a bge-reranker-v2-m3-compatible seam and deterministic keyword-overlap fallback until an endpoint is configured.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Made embedding-index manifest rebuilds idempotent**
- **Found during:** Overall verification after Task 2
- **Issue:** Re-running `scripts/build_embedding_index.py` rewrote `created_at`, leaving a dirty manifest after verification despite unchanged index inputs.
- **Fix:** Preserve the existing manifest `created_at` on rebuilds and added regression coverage.
- **Files modified:** `scripts/build_embedding_index.py`, `tests/test_embedding_index.py`
- **Verification:** `python3 -m pytest tests/test_embedding_index.py`; reran index builder and confirmed no manifest diff.
- **Committed in:** `91227ce`

**2. [Rule 3 - Blocking] Updated custom GSD state fields directly**
- **Found during:** Metadata update after summary creation
- **Issue:** `state advance-plan` could not parse the custom narrative `STATE.md`, and `state record-metric` reported that no Performance Metrics section existed.
- **Fix:** Applied durable metadata updates directly to `STATE.md`, `ROADMAP.md`, and `REQUIREMENTS.md` after successful `state update-progress`, `roadmap update-plan-progress`, `requirements mark-complete`, and `state record-session` tool runs.
- **Files modified:** `.planning/STATE.md`, `.planning/ROADMAP.md`, `.planning/REQUIREMENTS.md`
- **Verification:** Targeted file reads and diffs confirmed completed plan count, next action, roadmap checkbox, requirement completion, traceability status, and performance metric.
- **Committed in:** final metadata commit

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** The fixes keep verification reproducible and metadata state synchronized. No architectural scope change.

## Issues Encountered

- Yandex embedding credentials are absent in the local environment, so vector population is recorded as `gated_skip`. This is the credential-aware path required by the plan, not a failure.
- GSD state tooling still does not fully support the project-specific `STATE.md` layout; direct metadata updates were applied and documented as a blocking auto-fix.

## Known Stubs

None found. Stub scan matched only benign empty-list/default-writing code (`evidence_keywords=[]`, `newline=""`) that does not feed UI rendering or mock data.

## User Setup Required

Optional for dense vector population: set `YANDEX_AI_STUDIO_API_KEY` or `YANDEX_EMBEDDING_API_KEY`, plus concrete `YANDEX_EMBEDDING_DOC_MODEL`, `YANDEX_EMBEDDING_QUERY_MODEL`, and `YANDEX_EMBEDDING_DIMENSIONS=256`, then rerun the build command recorded in `embedding-index-manifest.json`.

## Next Phase Readiness

Ready for `01-04-PLAN.md`. Downstream orchestration, extraction, and diagnostic UI work can consume the prepared index manifest, retrieval comparison, eval CSV, Qdrant config/status, and explicit dense credential gate without replacing the vector-store path.

## Self-Check: PASSED

- Found created artifacts: `embedding_index.py`, `hybrid_retrieval.py`, `build_embedding_index.py`, `run_retrieval_spike.py`, `embedding-index-build.md`, `embedding-index-manifest.json`, `retrieval-comparison.md`, `retrieval-eval.csv`, and `01-03-SUMMARY.md`.
- Found task commits: `7e3f369`, `80a644f`, `4f9a9b6`, `e008d1a`.
- Found hardening commit: `91227ce`.

---
*Phase: 01-data-architecture-research*
*Completed: 2026-05-10*
