---
phase: "02-jury-mvp"
plan: "04"
subsystem: "workflow-nodes"
tags: ["ckan", "scouts", "coverage", "extraction-planner", "deterministic"]
dependency_graph:
  requires: ["02-01", "02-02", "02-03"]
  provides: ["ckan_adapter", "workflow_nodes_scouts_coverage_planner"]
  affects: ["app/workflow/run_graph.py", "app/evals/run_eval.py"]
tech_stack:
  added:
    - "app/data/ckan_adapter.py - bounded CKAN promotion and deterministic CSV/Parquet extraction"
    - "app/workflow/nodes/ - workflow node package (scouts, coverage, extraction_planner)"
  patterns:
    - "source_family dispatch routing (fedstat/world_bank/ckan) in coverage and planner"
    - "ALLOWED_OPERATIONS frozenset for SQL-injection-safe extraction planning"
    - "NoDataExplanationArtifact for unsupported CKAN resource formats"
key_files:
  created:
    - "app/data/ckan_adapter.py"
    - "app/workflow/nodes/__init__.py"
    - "app/workflow/nodes/scouts.py"
    - "app/workflow/nodes/coverage.py"
    - "app/workflow/nodes/extraction_planner.py"
    - "tests/test_phase2_workflow_nodes.py"
  modified: []
decisions:
  - "CKAN rows hard-capped at 5 and promoted resources at 20 per plan spec"
  - "extract_ckan_dataset returns NoDataExplanationArtifact with ckan_resource_format_not_supported_for_deterministic_extraction for xls/pdf/html"
  - "CoverageReport always includes source_specific_risks in evidence dict"
  - "ExtractionPlan.duckdb_sql is never set by the planner; adapters compile SQL internally"
  - "ALLOWED_OPERATIONS frozenset prevents arbitrary SQL from appearing in plan operations"
metrics:
  duration_minutes: 7
  completed_date: "2026-05-10"
  tasks_completed: 3
  files_created: 6
---

# Phase 2 Plan 04: Source Scouts, CKAN Adapter, Coverage, and Extraction Planner Summary

**One-liner:** Bounded CKAN adapter with CSV/Parquet deterministic extraction plus modular workflow nodes for scouts, coverage routing, and safe allowlist-based extraction planning.

## Objective

Implement source scout, CKAN promotion, coverage, and extraction-planning nodes that the graph can call. Honor D-16, D-17, D-21, D-22, D-23, and D-25 with reusable node functions instead of UI/eval-specific code.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | CKAN adapter (bounded promotion + CSV/Parquet extraction) | 2e0c6c6 | app/data/ckan_adapter.py |
| 2 | Source scout and coverage nodes | cbc931a | app/workflow/nodes/{__init__,scouts,coverage}.py |
| 3 | Safe extraction planner node | 5d65e77 | app/workflow/nodes/extraction_planner.py |

## Implementation Details

### Task 1: CKAN Adapter (`app/data/ckan_adapter.py`)

- `search_ckan_source_cards(query, *, rows=5)` — bounded to `min(rows, 5)`, calls `ckan_package_search`, returns compressed source-card dicts with `source_family`, `dataset_id`, `resource_id`, `title`, `formats`, `resource_count`, `provenance_url`, `why_matched`, `risk_flags`
- `promote_ckan_package(package_id)` — calls `ckan_package_show`, caps resources at 20, caches raw JSON under `.local/dataagent/phase2/ckan-cache/`
- `preview_ckan_coverage(promoted)` — metadata-only inspection, always includes `source_specific_risks` in evidence
- `extract_ckan_dataset(promoted, *, resource_id, filters, output_dir, artifact_id)` — deterministic extraction for `csv`, `csv.gz`, `parquet`; returns `NoDataExplanationArtifact` with `ckan_resource_format_not_supported_for_deterministic_extraction` for `xls`, `zip`, `pdf`, `html`
- Exports canonical rows matching `CANONICAL_DATASET_COLUMNS` from `fedstat_adapter`

### Task 2: Scout and Coverage Nodes (`app/workflow/nodes/`)

- `run_source_scouts(query, *, expected_sources, index_manifest_path)` — uses `HybridRetriever.search`; triggers CKAN discovery for `expected_sources=['ckan']` or when query contains 5-digit codes (`57319`), ЕМИСС, НЦСЭД, or CKAN keywords; returns `EvidenceBundleArtifact` with both `selected_sources` and `rejected_sources` populated
- `run_coverage_preview(evidence, *, intent_fields)` — routes `source_family` to `fedstat_adapter`, `world_bank_adapter`, or `ckan_adapter`; all `CoverageReport.evidence` dicts include `source_specific_risks` key; gated parquet-not-found cases return `status="gated"` rather than raising

### Task 3: Extraction Planner (`app/workflow/nodes/extraction_planner.py`)

- `ALLOWED_OPERATIONS = frozenset({"coverage_preview", "filter_rows", "join_indicators", "normalize_index", "export_dataset"})` — no free-form SQL
- `build_extraction_plan(intent, coverage_reports)` — selects ops from allowlist, derives typed filters from `IntentFrame.known_fields` only (periods validated as date-like/digit, geography bounded to 100 chars), returns `ExtractionPlan`
- `duckdb_sql` is never set; SQL is compiled by individual adapters
- Gated/skipped coverage produces `status="gated"/"skipped_with_reason"` with `skip_reason`
- `get_extractor_for_source(family)` dispatch: `fedstat->extract_fedstat_dataset`, `world_bank->extract_world_bank_dataset`, `ckan->extract_ckan_dataset`

## Verification

```
python -m pytest tests/test_phase2_workflow_nodes.py tests/test_hybrid_retrieval.py -q
# Result: 16 passed in 1.37s
```

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. All data paths return real types (DatasetArtifact, NoDataExplanationArtifact, CoverageReport, ExtractionPlan). CKAN download test uses monkeypatched `requests.get` since live API calls are integration-tested separately.

## Threat Flags

None. No new network endpoints added; CKAN calls go through bounded existing `ckan_package_search` / `ckan_package_show` wrappers. No new auth surface.

## Self-Check: PASSED

- `app/data/ckan_adapter.py` exists and contains `rows = min(rows, _MAX_SEARCH_ROWS)`, `def extract_ckan_dataset`, `ckan_resource_format_not_supported_for_deterministic_extraction`
- `app/workflow/nodes/scouts.py` contains `def run_source_scouts`
- `app/workflow/nodes/coverage.py` contains `source_specific_risks`
- `app/workflow/nodes/extraction_planner.py` contains `ALLOWED_OPERATIONS` and `extract_ckan_dataset` dispatch reference
- `tests/test_phase2_workflow_nodes.py` exists with 14 tests
- Commits `2e0c6c6`, `cbc931a`, `5d65e77` present in git log
