# Review Handoff: Remote Branch `codex/workflow-output-integrity`

You are reviewing the branch implemented on another machine.

## Hard Rules

- Do **not** use GSD commands or phase execution.
- `.planning` files may be read only as suspicious historical context, not as source of truth.
- The source of truth is runtime code, tests, and `docs/WORKFLOW-FIX-DIAGNOSIS.md`.
- Review as a bug/risk reviewer first. Lead with findings, not summaries.

## Repository

Base repository:

```bash
/Users/a/MAI/matmod
```

Expected remote branch:

```bash
codex/workflow-output-integrity
```

Fetch and inspect:

```bash
git fetch origin --prune
git checkout -B review-output-integrity origin/codex/workflow-output-integrity
git status --short --branch
git diff --stat origin/codex/phase-2-jury-mvp-planning...HEAD
git diff origin/codex/phase-2-jury-mvp-planning...HEAD
```

## Context

Highest-priority diagnosis:

```text
docs/WORKFLOW-FIX-DIAGNOSIS.md
```

Local handoff/distribution doc:

```text
docs/WORKFLOW-FIX-AGENT-HANDOFFS.md
```

Remote branch intended scope:

- Methodology Critic outcome mapping
- Final decision / repair route concepts
- Visualization/output builder integrity
- Narrator response composition
- User-facing trace/output layout
- Preventing output-stage failures from becoming `not_found`

This branch should **not** be doing major Source Scouts/Coverage/Planner refactors. Those are owned by local branch `codex/workflow-source-coverage-contract`.

## Files To Prioritize

Review these first:

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

Also inspect any unexpected changes outside this scope.

## What To Check

### 1. `not_found` Must Mean Data Absence

Flag as BLOCKER if:

- `needs_repair` maps to `not_found`;
- missing provenance maps to `not_found`;
- missing script maps to `not_found`;
- narrator failure maps to `not_found`;
- visualization failure maps to `not_found`;
- adapter/internal exception maps to `not_found`;
- LLM unavailable/timeout maps to `not_found`.

Correct behavior:

```text
not_found = trusted sources were checked and evidence shows requested slice is absent.
internal failure = gated/system_error/repair_needed or explicit failure artifact.
```

If public `WorkflowResponse.final_outcome` still only allows:

```text
passed | needs_clarification | not_found
```

then internal failure must still be visible in:

```text
component_statuses
trace_events
limitations
not_found_evidence.rejection_reasons
```

and must not pretend the data was simply absent.

### 2. Critic Must Be Selection-Aware

Flag as BLOCKER/P1 if:

- final pass requires *all* coverage reports to be `ok`, including rejected/unselected alternatives;
- rejected candidates block `passed` despite preserved rejection reasons;
- `passed` can happen without dataset rows/provenance/source-bound evidence;
- extracted dataset source does not match selected coverage/source candidate/plan;
- critic ignores extraction plan status.

Expected:

```text
selected/extraction-ready reports must pass;
unselected/rejected reports may be non-ok if reasons are preserved;
dataset rows must match selected source/coverage/plan.
```

### 3. Final Decision Contract

Look for a durable structure like:

```text
FinalOutcomeDecision
CriticToOutputHandoff
RepairRoute
WorkflowFailureArtifact
```

It does not need to be perfect, but there must be a clear boundary:

```text
Critic decides data quality.
Output/Narrator formats already-verified data.
Narrator does not re-decide final data quality.
```

Flag if final outcome is still just a loose string passed through service with no artifact trail.

### 4. Visualization / Output Builder

Flag if:

- only the first ok dataset is used for visualization when multiple selected datasets exist;
- visualization errors are swallowed as `None` with no trace/status;
- chart type and encoding can contradict each other;
- visualization failure changes `passed` into `not_found`;
- UI only renders visualization JSON and no user-visible chart/table when possible.

Expected:

```text
Visualization/output stage returns explicit ok/skipped/error.
Text-only passed answers are allowed.
Visualization errors are presentation failures, not data absence.
```

### 5. Narrator / Response Composer

Flag if:

- narrator reads broad raw mutable `state` instead of a constrained handoff/ledger;
- narrator can introduce unsupported numeric claims;
- unsupported narrator numbers downgrade final outcome to `not_found`;
- citations only include dataset artifact ids and omit source/coverage/plan/provenance chain;
- narrator prompt lacks final decision/output/visualization context;
- fallback response fabricates a clean answer when live LLM failed.

Expected:

```text
Narrator gets answer ledger + citations + final decision.
Narrator formats, but does not invent numbers or repair data.
Unsupported output claims are output failures.
```

### 6. User-Facing Trace

If branch touches UI/trace, check:

- user-facing trace is readable and source-bound;
- raw `TraceEvent` JSON/tool payloads are hidden under debug/collapsed UI;
- trace appears before final answer if that was implemented;
- no secrets/internal file paths/API payloads are shown by default.

## Tests To Run

Run targeted tests first:

```bash
PYTHONPATH=. pytest \
  tests/test_phase2_finalization.py \
  tests/test_web_frontend.py \
  tests/test_demo_readiness.py \
  -q
```

Then, if local runtime/source branches have been merged into an integration branch, run broader integration:

```bash
PYTHONPATH=. pytest \
  tests/test_phase2_acceptance.py \
  tests/test_phase2_workflow_service.py \
  tests/test_workflow_graph.py \
  tests/test_phase2_workflow_nodes.py \
  tests/test_phase2_finalization.py \
  tests/test_web_frontend.py \
  tests/test_demo_readiness.py \
  -q
```

## Anti-Regression Searches

Run:

```bash
rg "needs_repair.*not_found|not_found.*needs_repair" app/workflow
rg "narrator_error.*not_found|not_found.*narrator_error" app/workflow
rg "visualization.*None|except Exception.*visualization" app/workflow
rg "selected_sources" app/workflow/nodes/narrator.py app/workflow/service.py
rg "golden-coverage-matrix|golden-cases|matrix_hint|_case_id" app/workflow
```

Finding `selected_sources` is not automatically a blocker because compatibility fields may remain, but check whether narrator/output still depends on weak legacy fields instead of typed evidence.

## Review Output Format

Return review as:

```md
## Findings

### BLOCKER
- [file:line] Finding title
  Explanation, risk, and concrete fix.

### P1
- ...

### P2
- ...

## Can Commit As-Is

Short list of safe parts, if any.

## Must Fix Before Merge

Short checklist.

## Extra Tests Recommended

Commands or scenarios.

## Integration Notes

Mention likely conflicts with:
- `codex/workflow-runtime-boundary`
- `codex/workflow-source-coverage-contract`
```

## Review Bias

Be skeptical of any code path that makes the workflow look successful by hiding uncertainty. The product must prefer explicit `gated`, `repair_needed`, or internal failure evidence over a pretty but false `passed` or a lazy `not_found`.
