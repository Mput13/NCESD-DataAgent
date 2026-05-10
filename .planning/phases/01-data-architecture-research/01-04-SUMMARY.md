---
phase: 01-data-architecture-research
plan: 04
subsystem: orchestration-extraction-evaluation
tags: [qwen, yandex-ai-studio, langgraph, duckdb, trace, evals, streamlit-contract]

requires:
  - phase: 01-data-architecture-research
    provides: Plan 01 golden cases/rubric, Plan 02 source-card catalog/corpus, and Plan 03 Qdrant index manifest/retrieval eval
provides:
  - Hardened Qwen-targeted Yandex AI Studio client with structured-output helper and explicit credential gates
  - Canonical workflow artifact models and TraceEvent ownership for graph/UI reuse
  - Runnable narrow workflow graph CLI over prepared retrieval/index contracts
  - DuckDB SQL-first deterministic tool contracts and extraction probe evidence for FedStat, World Bank, and CKAN
  - Diagnostic trace UI view models and trace UI contract
  - Executable data relevance and extraction evaluation reports
affects: [01-05-demo-readiness, streamlit-demo, workflow, extraction, evals]

tech-stack:
  added: [openai, duckdb, pyarrow, polars, altair]
  patterns:
    - Qwen/Yandex live checks are credential-gated instead of silently mocked
    - Workflow-owned TraceEvent is reused by graph and UI adapters
    - Gated Qdrant/extraction states are recorded explicitly and do not count as success

key-files:
  created:
    - app/artifacts/workflow_artifacts.py
    - app/workflow/graph_contract.py
    - app/workflow/run_graph.py
    - app/data/deterministic_tools.py
    - app/ui/trace_models.py
    - app/evals/run_eval.py
    - scripts/run_extraction_probes.py
    - .planning/phases/01-data-architecture-research/yandex-qwen-spike.md
    - .planning/phases/01-data-architecture-research/langgraph-contract.md
    - .planning/phases/01-data-architecture-research/extraction-probes.md
    - .planning/phases/01-data-architecture-research/extraction-probes.json
    - .planning/phases/01-data-architecture-research/data-relevance-eval.json
    - .planning/phases/01-data-architecture-research/data-relevance-eval.md
    - .planning/phases/01-data-architecture-research/trace-ui-demo.md
  modified:
    - app/llm/yandex_ai_studio.py
    - app/artifacts/workflow_artifacts.py
    - requirements.txt

key-decisions:
  - "Use Qwen via the verified Yandex AI Studio OpenAI-compatible host with Api-Key auth as the target path; absent credentials produce gated evidence."
  - "Keep TraceEvent ownership in workflow artifacts and adapt it for UI view models instead of defining a UI-local trace schema."
  - "Treat gated dense retrieval and skipped extraction probes as explicit evaluation states, not passes."

patterns-established:
  - "Runnable graph outputs include selected/rejected sources, coverage/extraction planning, Qdrant status, final typed artifact, and trace events."
  - "Deterministic extraction probes write both markdown and JSON evidence, plus SQL artifacts, before data relevance eval runs."

requirements-completed:
  - NLU-01
  - NLU-02
  - NLU-03
  - NLU-04
  - SRCH-01
  - SRCH-02
  - SRCH-03
  - SRCH-04
  - DATA-01
  - DATA-02
  - DATA-03
  - DATA-04
  - DATA-05
  - RBST-04

duration: 8 min
completed: 2026-05-10
---

# Phase 01 Plan 04: Qwen, Workflow, Extraction, and Evaluation Summary

**Qwen/Yandex structured-output gate, runnable workflow trace slice, DuckDB extraction probes, and data relevance eval over prepared Qdrant status**

## Performance

- **Duration:** 8 min
- **Started:** 2026-05-10T01:07:54Z
- **Completed:** 2026-05-10T01:16:07Z
- **Tasks:** 4
- **Files modified:** 27

## Accomplishments

- Hardened `app/llm/yandex_ai_studio.py` for Qwen using `https://llm.api.cloud.yandex.net/v1`, `Authorization: Api-Key ...`, schema-driven Pydantic structured output, tool payload passthrough, and explicit `gated_skip` evidence when credentials are absent.
- Added canonical workflow artifacts, `TraceEvent`, graph budgets/tool scopes, and `app/workflow/run_graph.py`, which emits machine-readable selected/rejected source, coverage/extraction, Qdrant, final artifact, and trace evidence.
- Added DuckDB SQL-first deterministic tools and extraction probes for FedStat, World Bank, and CKAN, plus diagnostic UI trace view models that reuse the workflow trace model.
- Added `app/evals/run_eval.py` and generated `data-relevance-eval.json/.md`, recording gated dense/extraction states without treating them as successful retrieval or extraction.

## Task Commits

Each TDD task was committed with RED and GREEN commits:

1. **Task 1: Harden the Yandex AI Studio client for Qwen structured output**
   - `752188b` test: add failing tests for Yandex Qwen client
   - `44f0745` feat: harden Yandex Qwen client
2. **Task 2: Define typed workflow artifacts and implement the runnable narrow LangGraph flow**
   - `4331b55` test: add failing workflow graph tests
   - `0975e89` feat: implement narrow workflow graph slice
3. **Task 3: Prepare deterministic extraction tools/probes and Streamlit trace payloads while indexing runs**
   - `3b2a2ca` test: add failing extraction and trace tests
   - `7f60aa5` feat: add deterministic extraction probes and trace models
4. **Task 4: Add executable data relevance and extraction evaluation**
   - `36bbe2b` test: add failing data relevance eval test
   - `715e902` feat: add data relevance evaluation gate

## Files Created/Modified

- `app/llm/yandex_ai_studio.py` - Qwen-targeted Yandex AI Studio client with structured-output and gated credential checks.
- `app/artifacts/workflow_artifacts.py` - Typed workflow artifacts and canonical `TraceEvent`.
- `app/workflow/graph_contract.py`, `app/workflow/run_graph.py` - Role contracts, budgets/tool scopes, and runnable graph CLI.
- `app/data/deterministic_tools.py`, `scripts/run_extraction_probes.py` - Deterministic DuckDB/source probe contracts and generated probe evidence.
- `app/ui/trace_models.py` - Diagnostic Streamlit-facing trace, feedback, fix, and index-status view models.
- `app/evals/run_eval.py` - Executable data relevance/extraction quality gate.
- `.planning/phases/01-data-architecture-research/*` artifacts - Qwen spike, graph contract, extraction probes, graph smoke, trace UI demo, and eval reports.
- `requirements.txt` - Added required open-source dependencies for client, DuckDB/PyArrow/Polars/Altair paths.

## Verification

Commands run successfully:

```bash
PATH="$PWD/.local/bin:$PATH" python3 -m pytest tests/test_yandex_ai_studio.py
rg -n "llm\\.api\\.cloud\\.yandex\\.net|Api-Key|Qwen|DeepSeek historical fallback only" app/llm/yandex_ai_studio.py .planning/phases/01-data-architecture-research/yandex-qwen-spike.md
PATH="$PWD/.local/bin:$PATH" python3 -m pytest tests/test_workflow_graph.py
PATH="$PWD/.local/bin:$PATH" python -m app.workflow.run_graph --goldens .planning/phases/01-data-architecture-research/golden-cases.yaml --case-index 0 --index-manifest .planning/phases/01-data-architecture-research/embedding-index-manifest.json --json-output .planning/phases/01-data-architecture-research/run-graph-smoke.json
PATH="$PWD/.local/bin:$PATH" python3 -m pytest tests/test_deterministic_tools_and_trace.py
PATH="$PWD/.local/bin:$PATH" python scripts/run_extraction_probes.py --source-catalog-manifest .planning/phases/01-data-architecture-research/source-catalog-manifest.json --report .planning/phases/01-data-architecture-research/extraction-probes.md --json-output .planning/phases/01-data-architecture-research/extraction-probes.json
PATH="$PWD/.local/bin:$PATH" python3 -m pytest tests/test_eval_runner.py
PATH="$PWD/.local/bin:$PATH" python -m app.evals.run_eval --goldens .planning/phases/01-data-architecture-research/golden-cases.yaml --retrieval-eval .planning/phases/01-data-architecture-research/retrieval-eval.csv --extraction-probes .planning/phases/01-data-architecture-research/extraction-probes.json --index-manifest .planning/phases/01-data-architecture-research/embedding-index-manifest.json --json-output .planning/phases/01-data-architecture-research/data-relevance-eval.json --markdown-output .planning/phases/01-data-architecture-research/data-relevance-eval.md
PATH="$PWD/.local/bin:$PATH" python3 -m pytest
```

Full suite result: `24 passed`.

## Decisions Made

- Qwen remains the Phase 1 target even when local credentials are absent; DeepSeek is documented only as historical fallback evidence.
- `TraceEvent` is workflow-owned and consumed by UI view models through import, preventing schema drift between graph and Streamlit.
- Data relevance eval reports `gated` for missing dense embeddings and skipped extraction probes; these states are visible and do not inflate pass counts.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Made extraction probe script runnable by direct plan command**
- **Found during:** Task 3 acceptance verification
- **Issue:** `python scripts/run_extraction_probes.py ...` failed with `ModuleNotFoundError: No module named 'app'` because direct script execution did not put the repo root on `sys.path`.
- **Fix:** Added a small root-path bootstrap at the top of `scripts/run_extraction_probes.py`.
- **Files modified:** `scripts/run_extraction_probes.py`
- **Verification:** Re-ran the full Task 3 acceptance command and `tests/test_deterministic_tools_and_trace.py`.
- **Committed in:** `7f60aa5`

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** The fix was required for the plan’s exact CLI command. It did not change architecture or scope.

## Issues Encountered

- Yandex/Qwen credentials are absent locally, so live Qwen structured-output smoke calls are recorded as `gated_skip`. This is expected gate evidence, not a silent pass.
- Yandex embedding credentials are absent from the prepared index manifest, so data relevance eval records Qdrant/dense status as `gated_skip` and does not count dense retrieval as success.
- Extraction probes currently prove DuckDB SQL-first contracts and source-family evidence, but full numeric extraction remains skipped until later source-specific filters are selected.

## Known Stubs

No goal-blocking stubs found. Stub scan matched intentional gated/no-source defaults (`operations=[]`) and documentation wording around gated placeholders; these do not prevent this plan’s workflow, extraction-probe, or eval goals.

## User Setup Required

Optional for live Qwen validation: set `YANDEX_AI_STUDIO_QWEN_API_KEY` or `YANDEX_AI_STUDIO_API_KEY`, plus `YANDEX_AI_STUDIO_QWEN_MODEL` or `YANDEX_QWEN_MODEL`, then run:

```bash
PATH="$PWD/.local/bin:$PATH" python -m app.llm.yandex_ai_studio
```

Optional for dense vector population: set the Yandex embedding credentials recorded in `embedding-index-manifest.json`, then rerun its `rebuild_command`.

## Next Phase Readiness

Ready for `01-05-PLAN.md`. It can consume the Qwen gate, workflow artifacts, graph smoke output, deterministic extraction probes, trace UI view models, and data relevance eval without reopening architecture choices.

## Self-Check: PASSED

- Found created artifacts: `yandex-qwen-spike.md`, `langgraph-contract.md`, `extraction-probes.md`, `extraction-probes.json`, `trace-ui-demo.md`, `data-relevance-eval.json`, `data-relevance-eval.md`, and `01-04-SUMMARY.md`.
- Found code files: `workflow_artifacts.py`, `graph_contract.py`, `run_graph.py`, `deterministic_tools.py`, `trace_models.py`, `run_eval.py`, and `run_extraction_probes.py`.
- Found task commits: `752188b`, `44f0745`, `4331b55`, `0975e89`, `3b2a2ca`, `7f60aa5`, `36bbe2b`, `715e902`.

---
*Phase: 01-data-architecture-research*
*Completed: 2026-05-10*
