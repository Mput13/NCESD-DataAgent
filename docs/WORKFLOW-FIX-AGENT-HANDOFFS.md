# Workflow Fix Agent Handoffs

Created: 2026-05-11

GSD workflow is explicitly not in use. Planning artifacts may be read only as historical context. The source of truth is the runtime code, tests, and `docs/WORKFLOW-FIX-DIAGNOSIS.md`.

## Shared Diagnosis

The highest-risk bugs are implementation bugs, not planning bugs:

- Golden acceptance fixtures leak into runtime: `case_id` reaches workflow state, `graph.py` reads `golden-coverage-matrix.json`, and `design_research()` receives a matrix hint.
- Acceptance scoring treats `not_found` as acceptable for expected `passed` cases.
- Clarification continuation can become a fresh standalone query when pending state is missing or corrupt.
- Retrieval candidates are loose dicts named `selected_sources`, then coverage and extraction planner over-trust them.
- Coverage status is too optimistic: graph node status can be `ok` even when all reports are gated/skipped.
- Extraction planner uses `status == "ok"` instead of extraction readiness and deterministic tools infer source family from source id strings.
- Post-extraction failures and narrator/critic failures are often collapsed into `not_found`, which hides internal errors as data absence.

The correct workflow boundary is:

```text
RequestEnvelope
-> Supervisor
-> Intent Analyst
-> Research Designer
-> Source Scouts
-> Coverage & Schema
-> Extraction Planner
-> Deterministic Tools
-> Methodology Critic
-> Data Analyst / Output Planner
-> Narrator / Response Composer
```

Golden fixtures may wrap this path only from outside.

## Local Agent 1 - Runtime Boundary

Worktree: `/Users/a/MAI/matmod-worktrees/workflow-runtime-boundary`

Branch: `codex/workflow-runtime-boundary`

Scope:

- Remove golden matrix/runtime coupling.
- Tighten acceptance scoring.
- Make clarification continuation fail closed.
- Remove no-live fallback behavior from product service paths where possible.

Primary files:

- `app/workflow/graph.py`
- `app/workflow/state.py`
- `app/workflow/service.py`
- `scripts/run_phase2_acceptance.py`
- `tests/test_phase2_acceptance.py`
- `tests/test_phase2_workflow_service.py`
- `tests/test_workflow_graph.py`

Definition of done:

- No `app/workflow/**` runtime code reads `golden-coverage-matrix.json` or `golden-cases.yaml`.
- `design_research()` has no `matrix_hint`.
- `case_id` is eval metadata only, not workflow state.
- Expected `passed` cases fail if runtime returns `not_found`/`needs_clarification` without explicit allowed alternative.
- Empty `not_found` fails acceptance.
- `continue_user_query()` no longer starts a fresh query when clarification state is missing/corrupt.
- LLM re-analysis failure during clarification is explicit, not manually merged.

## Local Agent 2 - Source/Coverage/Planner Contract

Worktree: `/Users/a/MAI/matmod-worktrees/workflow-source-coverage-contract`

Branch: `codex/workflow-source-coverage-contract`

Scope:

- Introduce typed candidate and retrieval channel contracts.
- Preserve graph/RRF provenance into coverage.
- Make coverage aggregate status honest.
- Make extraction planner consume extraction-ready coverage, not any `ok` report.
- Make deterministic tools dispatch from typed plan fields before compatibility guessing.

Primary files:

- `app/artifacts/workflow_artifacts.py`
- `app/workflow/nodes/scouts.py`
- `app/workflow/nodes/coverage.py`
- `app/workflow/nodes/extraction_planner.py`
- `app/workflow/nodes/deterministic_tools.py`
- `app/workflow/graph.py`
- `tests/test_phase2_workflow_nodes.py`
- `tests/test_workflow_graph.py`

Definition of done:

- `EvidenceBundleArtifact` supports `selected_for_coverage`, `rejected_candidates`, `channel_statuses`, and `subgraph_context` while preserving old fields temporarily.
- Source Scouts output includes retrieval paths, fusion ranks/raw scores, evidence terms, graph context reference, and per-channel status.
- Dense gated plus lexical candidates yields `partial`, not plain `ok`.
- CKAN required failures become visible channel errors.
- Coverage consumes typed candidates and records source candidate id/retrieval provenance.
- Coverage graph status is aggregate truth, not unconditional `ok`.
- `ExtractionPlan` carries source family, adapter name, source candidate ids, and coverage report ids.
- Planner refuses non-extraction-ready reports.
- Deterministic tools use plan fields first and source-id guessing only as compatibility fallback.

## Remote Agent 3 - Post-Extraction Output Integrity

Suggested branch on the other machine: `codex/workflow-output-integrity`

Start from the same base commit as the local worktrees if possible. Before coding, review local Agent 1 and Agent 2 diffs if they are already pushed or shared. Do not use GSD commands or phase execution.

Remote sync prerequisite:

```bash
git fetch origin --prune
git checkout codex/phase-2-jury-mvp-planning
git pull --ff-only origin codex/phase-2-jury-mvp-planning
git log --oneline -5
```

The remote agent needs the branch tip that contains:

```text
2ff7556 feat: add external workflow audit layer
441e6cb wip: phase 2 paused at audit handoff
```

If `git log --oneline -5` on the other machine does not show `2ff7556`, the remote branch is behind the local machine. Push the local base branch first:

```bash
git push origin codex/phase-2-jury-mvp-planning
```

Then on the other machine:

```bash
git fetch origin --prune
git checkout -B codex/workflow-output-integrity origin/codex/phase-2-jury-mvp-planning
```

If Local Agent 1 or Local Agent 2 branches have already been pushed, the remote agent should also fetch them for reference but should not merge them blindly:

```bash
git fetch origin codex/workflow-runtime-boundary codex/workflow-source-coverage-contract
git diff --stat origin/codex/phase-2-jury-mvp-planning..origin/codex/workflow-runtime-boundary
git diff --stat origin/codex/phase-2-jury-mvp-planning..origin/codex/workflow-source-coverage-contract
```

Scope:

- Fix Methodology Critic outcome mapping.
- Introduce durable final decision / repair route concepts.
- Prevent narrator/output errors from becoming `not_found`.
- Turn visualization/output builder into an explicit post-critic stage.
- Improve user-facing trace and response composition without touching retrieval internals.

Primary files:

- `app/workflow/nodes/critic.py`
- `app/workflow/service.py`
- `app/workflow/nodes/visualization.py`
- `app/workflow/nodes/narrator.py`
- `app/artifacts/workflow_artifacts.py`
- `app/ui/streamlit_app.py`
- `tests/test_phase2_finalization.py`
- `tests/test_demo_readiness.py`
- `tests/test_web_frontend.py`

Implementation tasks:

1. Add an internal `FinalOutcomeDecision` model with at least:
   - `terminal_outcome`
   - dataset ids used
   - coverage report ids used
   - extraction plan id
   - warnings
   - blocking failures
   - optional repair route.
2. Stop mapping `needs_repair`, missing provenance, missing script, narrator failure, adapter failure, or unknown errors to `not_found`.
3. Make `not_found` possible only when trusted sources were actually checked and evidence shows the requested slice is absent.
4. Make successful extraction selection-aware:
   - selected/extraction-ready coverage must pass;
   - rejected/unselected candidate reports should not block a passed outcome if rejection reasons are preserved.
5. Introduce a stronger output handoff:
   - critic decision
   - selected datasets/scripts
   - selected coverage/source evidence
   - answer ledger/citations.
6. Visualization/output builder should:
   - process all selected datasets, not only the first;
   - return explicit `ok`, `skipped`, or `error`;
   - never change a valid data decision into `not_found`.
7. Narrator should:
   - receive the output handoff/ledger rather than raw mutable state;
   - not introduce unsupported numbers;
   - report output-stage failures as output failures, not data absence.
8. Add public trace projection:
   - user-facing search/analysis trace first;
   - raw `TraceEvent` JSON only in debug/collapsed UI.

Recommended tests:

- `test_final_pass_allows_rejected_unselected_candidates`
- `test_critic_needs_repair_does_not_become_not_found`
- `test_missing_provenance_is_system_error_not_not_found`
- `test_narrator_error_does_not_become_not_found`
- `test_visualization_error_does_not_change_final_decision`
- `test_agent8_visualizes_all_selected_datasets_not_only_first`
- `test_public_trace_hides_raw_tool_payloads`
- `test_streamlit_renders_user_trace_before_debug_trace`

Do not refactor Source Scouts or acceptance scoring in this branch unless required for integration. Those are owned by the two local branches.
