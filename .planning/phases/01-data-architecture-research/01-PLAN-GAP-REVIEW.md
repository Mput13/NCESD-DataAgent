---
phase: 01-data-architecture-research
reviewed_at: 2026-05-10
review_type: source_bound_plan_gap_review
baseline:
  - .planning/ARCHITECTURE_STACK.md
  - .planning/phases/01-data-architecture-research/01-CONTEXT.md
  - .planning/phases/01-data-architecture-research/01-01-PLAN.md
  - .planning/phases/01-data-architecture-research/01-02-PLAN.md
  - .planning/phases/01-data-architecture-research/01-03-PLAN.md
  - .planning/phases/01-data-architecture-research/01-04-PLAN.md
  - .planning/phases/01-data-architecture-research/01-05-PLAN.md
standard: no_false_positives_direct_text_evidence_only
---

# Phase 1 Plan Gap Review

This review only records gaps where the plan text and the architecture/context text
directly support the finding. Absence of production-only components such as
PostgreSQL, S3/Object Storage, Docker sandbox, and FastAPI is not treated as a
gap because the architecture explicitly allows those to be deferred from the
first prototype.

## Replanning Status

Status after user clarification: addressed in plan updates.

- UI polish is explicitly deferred; Streamlit remains a minimal diagnostic
  trace/artifact/feedback surface.
- Qdrant is mandatory for the vector-store abstraction. Missing embedding
  credentials may gate vector population, but may not replace Qdrant with a
  custom vector path.
- Plans `01-02` through `01-05` now require executable gates for generated
  source-card/corpus/catalog manifests, Qdrant index readiness or credential
  gates, retrieval relevance, extraction probes, graph execution, data-relevance
  eval, and demo readiness.

## Findings

### 1. Plan 01-02 does not require materialized source-card/catalog/corpus outputs

Severity: HIGH

Evidence:

- `01-02-PLAN.md` promises materialization of source cards, coverage hints,
  embedding chunk ids, and rejection-ready metadata into a SQLite/DuckDB catalog
  in `must_haves` lines 20-27.
- The same plan's artifact list only names contracts, modules, and builder
  scripts at lines 28-44; it does not name a generated source-card corpus file,
  embedding-corpus manifest output, or local catalog artifact/path as a required
  deliverable.
- Task 2 says the embedding corpus generator emits chunks and a manifest at
  line 114 and says the scripts materialize cards/catalog/corpus at line 116,
  but acceptance only searches for strings/functions at lines 117-119.
- `01-CONTEXT.md` requires a materialized local source-card corpus and Qdrant
  collection as durable Phase 1 data products at lines 43-49.

Why this is a real gap:

Plan 01-03 depends on loading "the Plan 01-02 embedding corpus", but Plan 01-02
can pass without proving that any corpus/catalog was generated, persisted, or
queryable. That is weaker than the prepared-data boundary in the architecture
context.

Required plan repair:

- Add explicit generated artifact paths for source cards, embedding corpus,
  embedding corpus manifest, and catalog DB/manifest.
- Add verification commands that run `scripts/build_source_cards.py`,
  `scripts/build_source_catalog.py`, and `scripts/build_embedding_corpus.py`.
- Validate row/chunk counts, manifest hashes, metadata version, and catalog
  queryability.

### 2. Plan 01-03 can pass without building or validating the Qdrant index

Severity: HIGH

Evidence:

- `01-03-PLAN.md` says the phase materializes a durable Qdrant embedding/search
  collection at lines 25-30.
- Task 1 requires the build entrypoint to upsert vectors into Qdrant and write
  a manifest/build log at lines 92-97.
- Acceptance and automated verification only run `rg` marker checks over source
  files and docs at lines 98-100.
- `01-CONTEXT.md` requires Phase 1 to materialize a local source-card corpus and
  Qdrant collection, with later phases consuming the manifest and collection
  rather than reprocessing all sources, at lines 45-49.

Why this is a real gap:

The plan's success criteria say "durable prepared Qdrant embedding/search
collection path and executable evidence" at lines 137-138, but its verification
does not execute the index build, validate JSON manifest semantics, or query
Qdrant. A marker-only manifest could satisfy the plan without a usable prepared
index or an honest credential gate.

Required plan repair:

- Run `scripts/build_embedding_index.py` in verification.
- Validate manifest JSON fields and status values.
- If status is ready, verify Qdrant collection existence and vector count.
- If status is `gated_skip`, verify exact missing env vars and that retrieval
  reports dense/index gated status instead of ready.

### 3. Plan 01-04 declares runnable graph and extraction probes, but verifies only markers

Severity: HIGH

Evidence:

- `01-04-PLAN.md` requires a runnable narrow LangGraph path at lines 29-36.
- Task 2 explicitly says `app/workflow/run_graph.py` can run a representative
  golden case or return an explicit gated status at lines 161-167.
- The action says the graph must be executable and not a prose-only skeleton at
  line 168.
- Verification for the graph is only `rg` checks for names and symbols at
  lines 169-171.
- Task 3 says `scripts/run_extraction_probes.py` inspects representative
  FedStat, World Bank, and CKAN paths at lines 180-187, but verification again
  only checks section headers and marker strings at lines 188-190.
- `01-CONTEXT.md` says the narrow slice must be runnable and verified on
  representative golden cases or explicit gates at lines 15-19.

Why this is a real gap:

The plan can pass with typed classes, graph names, and markdown sections while
never proving that a request moves through triage, retrieval, coverage,
extraction planning, deterministic tools/gated evidence, critic/narrator, and
trace emission. It can also pass without proving that DuckDB SQL-first probes
actually touch the local data/API paths.

Required plan repair:

- Add a `python -m app.workflow.run_graph ...` or equivalent command against at
  least one golden case.
- Assert the output includes typed trace events and a final/gated artifact.
- Run `scripts/run_extraction_probes.py` and validate generated probe evidence,
  not just markdown markers.

### 4. Plan 01-05 can produce a Streamlit shell instead of a runnable product loop

Severity: HIGH

Evidence:

- `01-05-PLAN.md` must-haves say Phase 1 demonstrates the product loop over
  prepared corpus/index or explicit gated evidence at lines 25-31.
- Task 1 behavior only requires the UI shell surfaces and readiness checks at
  lines 103-107.
- The action explicitly calls `app/ui/streamlit_app.py` a "Streamlit demo shell"
  at line 109.
- Acceptance only checks for Streamlit strings and UI terms with `rg` at
  lines 110-112.
- `01-CONTEXT.md` says the Streamlit deliverable must be runnable, not only a
  shell; it must execute the demo path and support feedback/fix-request capture
  for representative golden cases at lines 77-80.
- `ARCHITECTURE_STACK.md` says the UI must support the full cycle from question
  to trace, answer/artifacts, feedback, fix request, and recalculated result at
  lines 675-696.

Why this is a real gap:

The current plan can pass with static UI scaffolding and text markers. It does
not require the chat input to call `run_demo.py` or `run_graph.py`, does not
require representative golden cases to execute through Streamlit, and does not
require feedback/fix requests to produce a graph rewind or recalculated result.

Required plan repair:

- Add a Streamlit smoke/integration command or browser verification path.
- Require `streamlit_app.py` to call the demo/graph runner for at least
  representative golden cases or display explicit gated status from the runner.
- Verify feedback/fix-request capture creates `FeedbackArtifact`/`FixRequest`
  and routes to a target state or recorded gated limitation.

### 5. Phase 1 lacks an executable pytest/golden evaluation harness

Severity: MEDIUM

Evidence:

- `ARCHITECTURE_STACK.md` defines quality evaluation as `pytest + golden eval
  cases` and says it should check retrieval, coverage, refusal, SQL, and final
  answers at line 410.
- `01-CONTEXT.md` D-21 says evaluation must measure retrieval quality, coverage
  preview, source rejection, deterministic extraction, and trace completeness at
  lines 69-72.
- `01-01-PLAN.md` creates golden cases and an eval rubric at lines 40-44, and
  its verification only validates YAML/rubric structure at lines 82-109.
- Later plans create retrieval CSV/probe/demo artifacts, but none of the five
  plan file lists includes a committed `tests/`, `app/evals/run_eval.py`, or
  `pytest` execution gate.

Why this is a real gap:

The architecture asks for executable golden evaluation, while the plans mostly
define cases, rubrics, CSVs, and manual/prose evidence. This leaves no single
phase-level command proving that representative cases satisfy retrieval,
coverage, extraction, no-data, trace, and final-answer rules.

Required plan repair:

- Add a small committed eval runner and/or pytest suite.
- Wire it to `golden-cases.yaml`, retrieval eval, extraction probes, graph
  runner, and demo readiness.
- Make Phase 1 completion depend on that command passing or on explicit
  credential/data gated skips.

## Non-Findings

- The plans do not incorrectly drop FedStat, World Bank, or CKAN. All three are
  present in the source-card, retrieval, extraction, and UI/demo plans.
- The plans do not need to implement PostgreSQL, S3/Object Storage, FastAPI,
  Docker sandbox, or full production session replay in Phase 1. The architecture
  allows those as later production/maximum-mode capabilities.
- The use of a narrow slice is not itself a problem. The gap is that the current
  verification does not prove the narrow slice is runnable and integrated.
