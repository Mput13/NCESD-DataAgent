# Integrated Review Handoff: Output Integrity On Top Of Ready Workflow Fixes

Use this when reviewing the remote `codex/workflow-output-integrity` work **after** the two local workflow-fix branches are already available.

## Hard Rules

- Do not use GSD commands or phase execution.
- `.planning` files are historical/suspicious context only.
- Source of truth: runtime code, tests, `docs/WORKFLOW-FIX-DIAGNOSIS.md`, and the already-reviewed workflow fix branches.
- Review as a bug/risk reviewer: false `passed`, lazy `not_found`, hidden gated/error states, and broken handoffs are the priority.

## Branches

Base:

```text
origin/codex/phase-2-jury-mvp-planning
```

Already completed local branches:

```text
origin/codex/workflow-runtime-boundary
origin/codex/workflow-source-coverage-contract
```

Remote output branch to review:

```text
origin/codex/workflow-output-integrity
```

Important dependency:

```text
workflow-source-coverage-contract is built on top of workflow-runtime-boundary.
```

So the clean integration order is:

```text
base
-> workflow-runtime-boundary
-> workflow-source-coverage-contract
-> workflow-output-integrity
```

## Prepare Integration Review Branch

Run on the other machine:

```bash
git fetch origin --prune
git checkout -B codex/workflow-fix-integration-review origin/codex/phase-2-jury-mvp-planning
git merge --no-ff origin/codex/workflow-runtime-boundary
git merge --no-ff origin/codex/workflow-source-coverage-contract
git branch codex/workflow-fix-before-output-review
git merge --no-ff origin/codex/workflow-output-integrity
```

If conflicts appear, resolve them in favor of these principles:

- runtime must not read golden fixtures or use matrix hints;
- Source Scouts output candidates selected for coverage, not verified data;
- Coverage status must aggregate actual report status;
- Planner must require extraction-ready coverage;
- Critic/output must not turn internal failures into `not_found`;
- Narrator formats verified data, it does not re-decide data quality.

## Review The Output Branch Delta

After merging `origin/codex/workflow-output-integrity`, inspect only what it added on top of the ready workflow fixes:

```bash
git diff --stat codex/workflow-fix-before-output-review..HEAD
git diff codex/workflow-fix-before-output-review..HEAD
```

Also inspect final integrated state for cross-branch regressions:

```bash
git diff --stat origin/codex/phase-2-jury-mvp-planning..HEAD
```

## Files To Prioritize

```text
app/workflow/nodes/critic.py
app/workflow/service.py
app/workflow/nodes/visualization.py
app/workflow/nodes/narrator.py
app/artifacts/workflow_artifacts.py
app/ui/streamlit_app.py
tests/test_phase2_finalization.py
tests/test_demo_readiness.py
tests/test_web_frontend.py
```

Also inspect conflict resolutions in:

```text
app/workflow/graph.py
app/workflow/run_graph.py
app/workflow/state.py
tests/test_workflow_graph.py
tests/test_phase2_workflow_service.py
tests/test_phase2_workflow_nodes.py
```

## What To Block

Block the merge if any of these remain:

- `app/workflow/**` reads `golden-coverage-matrix.json`, `golden-cases.yaml`, `matrix_hint`, or `_case_id`.
- Expected `passed` can be accepted as empty `not_found`.
- Missing/corrupt clarification state starts a fresh query.
- LLM unavailable/no-response path produces a normal product answer.
- Source candidates are treated as verified data before coverage/extraction.
- Coverage component status is `ok` with zero ok/extraction-ready reports.
- Planner builds an ok plan from reports that are not extraction-ready.
- Deterministic tools ignore typed `source_family`/`adapter_name` and guess first.
- Critic maps `needs_repair`, missing provenance/script, adapter errors, or LLM errors to `not_found`.
- Narrator or visualization failure changes valid extracted data into `not_found`.
- Narrator can introduce unsupported numeric claims without an output failure.

## Tests

First run the tests known to have passed in the local branches:

```bash
PYTHONPATH=. pytest \
  tests/test_phase2_acceptance.py \
  tests/test_phase2_workflow_service.py \
  tests/test_workflow_graph.py \
  tests/test_phase2_contracts.py \
  tests/test_web_frontend.py \
  tests/test_phase2_workflow_nodes.py \
  -q
```

Then run output/finalization focused tests:

```bash
PYTHONPATH=. pytest \
  tests/test_phase2_finalization.py \
  tests/test_demo_readiness.py \
  tests/test_web_frontend.py \
  -q
```

Then run the combined smoke suite:

```bash
PYTHONPATH=. pytest \
  tests/test_phase2_acceptance.py \
  tests/test_phase2_workflow_service.py \
  tests/test_workflow_graph.py \
  tests/test_phase2_workflow_nodes.py \
  tests/test_phase2_finalization.py \
  tests/test_demo_readiness.py \
  tests/test_web_frontend.py \
  -q
```

## Anti-Regression Searches

Run:

```bash
rg "golden-coverage-matrix|golden-cases|matrix_hint|_case_id" app/workflow
rg "clarification_merged_no_llm|triage_llm_failed_using_research_default" app/workflow app/web tests
rg "needs_repair.*not_found|not_found.*needs_repair" app/workflow
rg "narrator_error.*not_found|not_found.*narrator_error" app/workflow
rg "visualization.*None|except Exception.*visualization" app/workflow
rg "selected_sources" app/workflow/nodes/narrator.py app/workflow/service.py
```

`selected_sources` may exist as a compatibility field, but output/narrator should not rely on weak legacy selected-source dicts when typed candidate/coverage/plan evidence is available.

## Review Output Format

Return:

```md
## Findings

### BLOCKER
- [file:line] Finding title
  Why this can produce false passed, lazy not_found, hidden gated/error, or broken handoff.

### P1
- ...

### P2
- ...

## Safe To Merge

List what is safe, if anything.

## Must Fix Before Merge

Checklist.

## Tests Run

Commands and results.

## Integration Notes

Conflicts resolved, suspicious areas, and whether output branch respects runtime/source contracts.
```

## Desired Final State

After this review, the integrated branch should have:

- no golden fixture leakage in runtime;
- strict acceptance scoring;
- fail-closed clarification;
- typed retrieval/coverage/planner handoffs;
- extraction-ready planning;
- critic/output stages that distinguish data absence from internal workflow failure;
- narrator and visualization that cannot convert output-stage errors into `not_found`.
