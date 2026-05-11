---
phase: 02-jury-mvp
plan: "02"
status: complete
completed_at: "2026-05-10"
---

# Plan 02-02 Summary: Retrieval Hardening

## What Was Built

### Task 1: Domain-Aware Retrieval Reranking
Added domain-aware reranking logic to `app/retrieval/hybrid_retrieval.py`:
- **Exact indicator match bonus** (+2.5): rewards cards whose indicator code or title closely matches the query.
- **Direct keyword bonus** (+1.0): boosts cards sharing direct economic indicator keywords (ВВП, GDP, ИПЦ, CPI, population) with the query.
- **Contextual share penalty** (−1.5): penalises cards with titles containing share/percent phrases (удельный вес, доля, percent of GDP, etc.) when the query asks for an absolute value.
- **Source family bonus** (upgraded to +0.75 from +0.5): rewards candidates matching the caller's expected sources.
- `split_rejections` now attaches concrete rejection reasons: `contextual_match_not_direct_indicator` and `source_preference_mismatch`.

### Task 2: Phase 2 Retrieval Evidence Fields
Updated `scripts/run_retrieval_spike.py`:
- **Expanded CSV fieldnames** to include `expected_route`, `top_title`, `qdrant_url`, `server_manifest_status`, `selected_count`, and `rejected_count` alongside existing fields.
- **`--phase2-output-json` CLI flag**: writes a JSON file with `total_cases`, `ready_index`, `server_manifest_status`, `cases`, and `unacceptable_no_candidate_cases`.
- **`build_phase2_output_json` function**: exported for direct use in tests and downstream eval scripts.
- **`--server-manifest` CLI flag**: optional path to the Qdrant server manifest for server status tracking.
- Cases with no candidate are only acceptable when the golden case's `expected_terminal_behavior` is `not_found`; all others are counted in `unacceptable_no_candidate_cases`.

## Artifacts Changed
- `app/retrieval/hybrid_retrieval.py` — domain-aware reranking, rejection reasons
- `scripts/run_retrieval_spike.py` — Phase 2 evidence fields, `--phase2-output-json`, `build_phase2_output_json`
- `tests/test_phase2_retrieval.py` — regression tests for direct-indicator ranking and evidence field output

## Verification
All 14 tests pass:
```
python3 -m pytest tests/test_phase2_retrieval.py tests/test_hybrid_retrieval.py -q
14 passed in 4.27s
```

## Key Decisions
- Contextual penalty is skipped when the query itself asks for a share (e.g., "доля ВВП"), preserving correct ranking for share queries.
- `server_manifest_status` is sourced from the Qdrant server manifest at `.planning/phases/02-jury-mvp/qdrant-server-manifest.json` when present, falling back to `"not_loaded"`.
- CSV fieldnames list is the single source of truth; `build_phase2_output_json` mirrors the same fields into JSON cases.

## Requirements Addressed
- SRCH-01, SRCH-02, SRCH-03, SRCH-04: direct-indicator ranking above contextual matches.
- RBST-03: rejected candidates carry concrete rejection reasons.
- ENG-03: Phase 2 evidence fields feed the all-20 coverage matrix in plan 02-10 and eval gate in plan 02-07.
