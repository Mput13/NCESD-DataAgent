---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: human_verification_pending
stopped_at: Completed 02-08-PLAN.md; manual Streamlit UAT approval pending
last_updated: "2026-05-10T18:05:00.000Z"
progress:
  total_phases: 2
  completed_phases: 1
  total_plans: 15
  completed_plans: 15
---

# Project State: DataAgent

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** Опора на факты — каждая цифра со ссылкой, числа извлекает код, не LLM  
**Current focus:** Phase 02 — jury-mvp

## Current Phase

**Phase:** 2  
**Slug:** `02-jury-mvp`  
**Name:** Full Jury MVP  
**Status:** Phase 02 execution complete; verification/manual UAT checkpoint pending
**Canonical directory:** `.planning/phases/02-jury-mvp`  
**Next action:** run `$gsd-verify-work 2` and complete/approve the manual Streamlit UAT checkpoint in `.planning/phases/02-jury-mvp/manual-uat.md`.

## Phase Boundary

The roadmap now has two explicit phases in the current milestone: Phase 1 infrastructure acceptance and Phase 2 full jury MVP. Do not infer additional numbered phases unless `.planning/ROADMAP.md` is changed again.

Despite the historical slug, Phase 1 was implementation-oriented: it produced code, scripts, tests, prepared-data artifacts, embedding/search index manifests, data/retrieval/extraction evidence, and UI trace contracts where the plans required them.

Phase 1 is not a license to build an unverified full product in one jump. Each slice must follow its plan, produce its expected artifacts, run its verification commands, and write the corresponding `01-xx-SUMMARY.md`.

The corrected Phase 1 boundary is stronger than the original plan: by the end of Phase 1 the source-card corpus and embedding/search index should be ready for demo use. Reprocessing or re-embedding all sources after Phase 1 is an exceptional recovery path, not the default next step. Because embedding may be long-running, execution should start the embedding/index build as soon as the source-card corpus is ready and use that time to prepare orchestration, extraction, UI, and demo integration.

Current priority clarification: do not optimize for UI beauty or polished output yet. The priority is correctly deciding which data is relevant to a query, proving coverage, using Qdrant for the vector-store path, rejecting weak sources with reasons, and extracting numeric data through deterministic code. Streamlit remains a diagnostic surface for trace/artifacts/feedback, not a visual-design workstream.

## Current Phase 2 Boundary

Phase 2 is now explicitly added in `.planning/ROADMAP.md`. It is the full jury MVP phase, not a small demo subset. Acceptance target: all 20 golden cases must reach a correct terminal outcome (`passed`, `needs_clarification`, or `not_found`). `gated`, `stale`, `skipped_with_reason`, `no_candidate`, or `final_answer.status=ok` while coverage/extraction is gated are not acceptable final states.

The current UI and workflow are Phase 1 diagnostic infrastructure only. Phase 2 must expose a real evaluated workflow and a frontend-facing response contract suitable for a chat-like LLM UI. Streamlit remains a simple fast test surface rather than the polished frontend deliverable.

`User query → Supervisor → Intent Analyst → Research Designer / Direct path → FedStat/WB/CKAN Scouts → Coverage & Schema → Extraction Planner → Deterministic Tools → Methodology Critic → Visualization → Narrator → answer + dataset + script + sources + trace`.

## Phase History

- **2026-05-10 — Planning reset to one canonical Phase 1.**
  Removed the failed core/workflow skeleton, deprecated duplicate Phase 1 directory, forensic incident artifact, and three-person workstream documents from the active tree.
  At that time the active roadmap had one phase only: `.planning/phases/01-data-architecture-research`. This was superseded on 2026-05-10 by the explicit Phase 2 roadmap addition.

- **2026-05-10 — Phase 1 boundary corrected for prepared data and embeddings.**
  User clarified that Phase 1 must finish with prepared data and embedding/search index ready for demo use. Later reprocessing is exceptional. Plans `01-02` through `01-05` were revised so embedding corpus/indexing starts early and independent workflow/UI/extraction work proceeds while it runs.

- **2026-05-10 — Data relevance and Qdrant priority clarified.**
  User clarified that Phase 1 should prioritize relevant source selection and deterministic extraction over UI beauty. Qdrant must be used for the vector-store path. The revised plans must replace marker-only verification with executable build/eval gates for corpus/catalog, Qdrant index readiness or credential gates, retrieval relevance, extraction probes, graph execution, and demo readiness.

- **2026-05-10 — Plan 01 evaluation foundation completed.**
  `01-01-SUMMARY.md` accepted the requirements map, 20 golden cases, and deterministic eval rubric as the Phase 1 evaluation foundation.

- **2026-05-10 — Plan 02 prepared-data contracts completed.**
  `01-02-SUMMARY.md` accepted typed source-card/evidence/embedding contracts, deterministic FedStat/World Bank/CKAN builders, SQLite catalog materialization, and source-card/catalog/embedding-corpus manifests.

- **2026-05-10 — Plan 03 embedding/search index and retrieval eval completed.**
  `01-03-SUMMARY.md` accepted the Qdrant embedding index build path, credential-gated Yandex vector population evidence, hybrid lexical/dense/rerank retrieval interface, retrieval comparison, and retrieval eval CSV.

- **2026-05-10 — Plan 04 orchestration, extraction probes, and data relevance eval completed.**
  `01-04-SUMMARY.md` accepted the Qwen/Yandex structured-output gate, canonical workflow artifacts and TraceEvent ownership, runnable graph smoke output, DuckDB SQL-first extraction probe evidence, diagnostic trace UI models, and data relevance eval reports.

- **2026-05-10 — Plan 05 demo readiness and decision package completed.**
  `01-05-SUMMARY.md` accepted the demo readiness runner, minimal diagnostic Streamlit shell, prepared-data readiness report, final recommendation package, implementation decision brief, and architecture growth map. The current demo status is explicitly `gated`, not falsely ready: Qdrant/dense retrieval awaits embedding credentials and deterministic numeric output awaits promoted extraction cases.

- **2026-05-10 — Actual Phase 1 state verified after full-corpus recovery.**
  `.planning/phases/01-data-architecture-research/phase1-actual-state-verification.md` records the real runnable surface. Streamlit starts at `http://localhost:8501`, workflow smoke runs via `python3 -m app.workflow.run_graph` against the partial index, and demo readiness returns `blocked` / `qdrant_status=stale` because `embedding-index-manifest.json` still points at the old 11-card corpus while the rebuilt corpus has 36,321 chunks. Full embedding build PID `77528` was alive with cache progress 17,595 / 36,321 at 2026-05-10T09:08:39Z.

- **2026-05-10 — Phase 1 test acceptance recorded.**
  `.planning/phases/01-data-architecture-research/phase1-test-acceptance.md` freezes the current test and gate outputs. Pytest is 26 passed / 1 failed; demo readiness is `blocked` with `qdrant_status=stale`; retrieval eval over 20 golden cases has all dense rows `gated_skip`, 14 source-family matches, 6 no-candidate cases; extraction probes are coverage evidence only with `skipped_with_reason`; data relevance eval is 0 passed / 0 failed / 20 gated. Decision: Phase 1 is acceptable as infrastructure, not as a functional MVP or jury-demo agent.

- **2026-05-10 — Phase 2 explicitly added for full jury MVP.**
  Roadmap now has canonical Phase 2 at `.planning/phases/02-jury-mvp`. The next session should run `$gsd-discuss-phase 2`. The user explicitly rejected a low acceptance bar; all 20 golden cases are the target. Remote branch `origin/workstream-1/core-integration` was reviewed and is not directly mergeable because it deletes current Phase 1 artifacts/tests/scripts, rewinds `.planning`, keeps scout/extraction stubs, and regresses Yandex AI Studio endpoint/auth. Treat it as reference only.

- **2026-05-10 — Phase 2 context captured and scope locked.**
  `.planning/phases/02-jury-mvp/02-CONTEXT.md` records the user decision that Phase 2 must implement the full functionality described in `.planning/ARCHITECTURE_STACK.md`. The architecture stack is the minimum jury-prototype baseline, not a future wishlist or a reduced MVP. Planning must target all 20 golden cases and the full source-bound workflow: user query through Supervisor, Intent Analyst, Research Designer/direct path, FedStat/WB/CKAN scouts, Coverage & Schema, Extraction Planner, Deterministic Tools, Methodology Critic, Visualization, Narrator, answer, dataset, script, sources, and trace.

- **2026-05-10 — Phase 2 discussion decisions expanded.**
  User delegated implementation wave ordering to the planner with preference for parallel work and fast delivery. Target path must use real Yandex/Qwen LLM calls and real embedding calls where specified by the architecture stack; request processing without live LLM is not a supported runtime mode. Minimum success includes full pipeline traversal and an answer. Manual testing and user feedback after implementation are required in addition to automatic tests.

- **2026-05-10 — Qdrant server mode chosen for Phase 2 runtime.**
  Local embedded Qdrant (`QdrantClient(path=".local/qdrant")`) is acceptable for small tests and isolated development only. Phase 2 should use Docker/server Qdrant through `QDRANT_URL` so parallel scouts, evals, workflow smoke runs, and Streamlit can safely query one shared collection without embedded storage locks. The 36,321-point corpus is above the local-mode 20,000-point warning threshold, so jury readiness should not depend on embedded local mode.

- **2026-05-10 — Phase 2 planning paused for branch isolation.**
  Plan-phase for Phase 2 created/revised 10 plan files and reached checker iteration 2. The latest revision resolved deterministic tools dispatch, `ScriptArtifact` propagation, and executable feedback/fix paths. Planning stopped before the third `gsd-plan-checker` pass because the worktree was on `codex/feat-openai-compatible-embeddings` and contained unrelated embedding-experiment changes. Correct planning branch: `codex/phase-2-jury-mvp-planning`. Resume by reading `.planning/phases/02-jury-mvp/02-PLAN-PAUSE.md` and rerunning the plan checker, not by restarting discussion or planning from scratch.

- **2026-05-10 — Phase 2 planning verified.**
  Third `gsd-plan-checker` pass on branch `codex/phase-2-jury-mvp-planning` returned `VERIFICATION PASSED` for all 10 plans. No blockers remain before `$gsd-execute-phase 2`. Requirements groups `NLU-01..04`, `SRCH-01..04`, `DATA-01..05`, `ART-01..06`, `RBST-01..04`, `UI-01..04`, and `ENG-01..04` are covered by plan frontmatter/tasks, and Revision 2 fixes for deterministic tool dispatch, `ScriptArtifact` propagation, Qdrant server mode, executable feedback/fix paths, and all-20 acceptance gates were confirmed present.

- **2026-05-10 — Phase 2 execution plan set completed.**
  `02-08-SUMMARY.md` completed the final execution plan: `run_user_query`, `continue_user_query`, and `apply_feedback` are the service entrypoints; feedback/fix-request artifacts persist by `run_id`; README/manual UAT docs exist; `python -m pytest -q` passed 188 tests; all-20 acceptance produced `total_cases=20` and `unacceptable=0`. Live Yandex/Qwen is required for runtime query processing.

- **2026-05-09 — Phase 1 context gathered.**
  Captured implementation decisions in `.planning/phases/01-data-architecture-research/01-CONTEXT.md`, based on `.planning/ARCHITECTURE_STACK.md`.
  Phase 1 should follow the architecture stack fully, include FedStat + World Bank + CKAN from the start, prepare 15-20 test cases, and prioritize visible multi-agent trace/UI impact while preserving source-bound deterministic extraction.

## Current Repository Surface

- `app/llm/yandex_ai_studio.py` — Qwen-targeted Yandex AI Studio chat-completions client with structured-output helper and gated credential evidence.
- `app/workflow/run_graph.py` — runnable narrow workflow graph entrypoint emitting trace/source/coverage/extraction/Qdrant evidence.
- `app/data/deterministic_tools.py` and `scripts/run_extraction_probes.py` — DuckDB SQL-first deterministic tool contracts and source-family extraction probes.
- `app/evals/run_eval.py` — data relevance and extraction evaluation gate over golden cases.
- `app/demo/run_demo.py` — prepared-data demo readiness runner that consumes corpus/catalog/index/eval/probe artifacts and refuses false dense readiness.
- `app/ui/streamlit_app.py` — minimal diagnostic Streamlit shell exposing chat input, examples, state machine, trace, artifacts, rejection details, index readiness, and feedback/fix requests; Phase 2 should keep Streamlit as quick test surface while producing a chat-like frontend response contract.
- `.planning/phases/01-data-architecture-research/phase1-actual-state-verification.md` — actual-state verification report for the Phase 1 runnable surface, test results, interface, and incomplete/gated pieces.
- `.planning/phases/01-data-architecture-research/phase1-test-acceptance.md` — full current acceptance report covering all pytest tests and Phase 1 gates.
- `.planning/phases/02-jury-mvp/02-CONTEXT.md` — canonical Phase 2 context; locks full `.planning/ARCHITECTURE_STACK.md` functionality as the jury MVP minimum.
- `.planning/phases/02-jury-mvp/02-SEED-CONTEXT.md` — seed context that fed the Phase 2 discussion; superseded by `02-CONTEXT.md` for planning.
- `.planning/phases/02-jury-mvp/remote-workstream-review.md` — review of `origin/workstream-1/core-integration`; records why it is not directly mergeable and which ideas may be ported selectively.
- `docs/PROJECT_WORKFLOW.md` — GSD workflow explanation for the project.
- `requirements.txt` — includes Yandex/OpenAI client, Pydantic, Qdrant, DuckDB/PyArrow/Polars/Altair, Streamlit, and HTTP/runtime dependencies.
- Accepted Phase 1 artifacts now include golden eval cases, source-card contracts, deterministic source-card builders, a SQLite source catalog, generated source-card/catalog/embedding-corpus manifests, Qdrant embedding-index manifest/build log, hybrid retrieval eval artifacts, and tests for those contracts.

## Verified Local Data Locations

- `/Users/a/Downloads/dumps/fedstatru/fedstatru.zip`
- `/Users/a/Downloads/dumps/wb/data.zip`
- `/Users/a/Downloads/dumps.zip`
- Dumps are intentionally not committed; repo `.gitignore` excludes dumps, zip/parquet/jsonl/pdf and keeps `.planning/`.

## Current Research Baseline

- `.planning/DATA_REPORT.md` maps FedStat, World Bank, and NSED CKAN API.
- `.planning/ARCHITECTURE_STACK.md` describes the target architecture: Qwen/Yandex AI Studio, LangGraph hierarchical supervisor, source scouts, deterministic DuckDB/PyArrow extraction, Streamlit trace/artifacts UI, and pytest golden evals.
- `.planning/YANDEX_AI_STUDIO_RESEARCH.md` records the existing DeepSeek 3.2 smoke-test history. Qwen remains the target model path for Phase 1 unless a plan records a blocker.

## Decisions Log

- **2026-05-11 — Offline/no-response LLM fallbacks are a Phase 2 bug.**
  Phase 2 must not keep product workflow running by pretending the LLM works without network, credentials, or a response. Runtime LLM failures should become explicit gated/error artifacts (`llm_unavailable`, `llm_timeout`, `llm_error`) and must fail acceptance/readiness, not fall back to keyword, rule-based, manual-merge, or fake narrator behavior. Unit tests may mock `YandexAIStudioClient.structured_chat`, but product code should not contain an offline/no-response LLM substitute path.

- **2026-05-11 — Live LLM owns request understanding and reasoning.**
  Do not add code paths that try to replace LLM work with handwritten request-understanding, research-design, critic, or narrator logic. Deterministic code is for source-bound retrieval, extraction, validation, and numeric/provenance checks; user-query interpretation and final reasoning must go through live Yandex/Qwen.

- **2026-05-10 — Plan 02-01 constrains final user outcomes.**
  Phase 2 final user outcomes are limited to `passed`, `needs_clarification`, and `not_found`; internal gated/stale/skipped/no_candidate states stay visible only as component-level status.

- **2026-05-10 — Plan 02-01 defines one guarded workflow service entrypoint.**
  `run_user_query` is the shared frontend/eval/CLI import path and deliberately raises until plan `02-06` implements real final `WorkflowResponse` assembly.

- **2026-05-10 — Plan 02-03 normalizes FedStat wide Parquet deterministically.**
  FedStat technical-column Parquet tables are converted by treating the first row as logical headers, then extracting canonical source-bound long rows through code.

- **2026-05-10 — Plan 02-03 keeps World Bank geographies deterministic.**
  Russia/Kazakhstan/China aliases and BRICS/EAEU sets resolve to ISO3 country lists; aggregate rows are excluded unless explicitly requested.

- **2026-05-10 — Plan 02-03 exports typed reproducibility scripts.**
  Dataset exports now pair `DatasetArtifact` output with downloadable `ScriptArtifact` objects carrying path, checksum, and source dataset metadata.

- **2026-05-10 — Plan 02-09 requires Qdrant server manifest evidence.**
  Dense retrieval readiness for Phase 2 now depends on `.planning/phases/02-jury-mvp/qdrant-server-manifest.json` with matching corpus hash, server URL, collection, vector count, and reproduce command.

- **2026-05-10 — Plan 02-09 promotes cached embeddings by default.**
  `scripts/promote_qdrant_server.py` reuses `.local/dataagent/phase1/embedding-cache.jsonl`; missing cache coverage fails unless `--allow-reembed` is explicitly passed.

- **2026-05-10 — Plan 04 keeps Qwen as the target with explicit credential gates.**
  The verified AI Studio host is `https://llm.api.cloud.yandex.net/v1` with `Api-Key` auth. Missing Qwen credentials produce `gated_skip` evidence instead of silent success; DeepSeek remains historical fallback evidence only.

- **2026-05-10 — Plan 04 makes workflow artifacts the trace source of truth.**
  `TraceEvent` is owned by `app/artifacts/workflow_artifacts.py`; graph and UI modules import it rather than duplicating trace schemas.

- **2026-05-10 — Plan 04 evaluates gated states explicitly.**
  Data relevance eval records dense/Qdrant and extraction probe gates without counting them as retrieval or extraction success.

- **2026-05-10 — Plan 03 uses Qdrant as the vector-store abstraction even when credentials are absent.**
  Missing Yandex embedding credentials gate vector population as `gated_skip`; they do not permit a custom local vector index. Retrieval code reads the prepared manifest and preserves dense/rerank status in eval output.

- **2026-05-10 — Plan 01 evaluates structured evidence, not prose alone.**
  Downstream Phase 1 work should target `golden-cases.yaml` and `eval-rubric.md`; unsupported numeric claims are hard failures without deterministic provenance.

- **2026-05-10 — Plan 02 embeds source-card metadata only.**
  Raw numeric observations and generated answer text are excluded from embedding input; later Qdrant indexing should consume `EmbeddingDocument` chunks and join back through `card_id`.

- **2026-05-10 — Plan 02 uses SQLite as the local catalog interface.**
  The catalog stores source cards, coverage hints, embedding chunks, and rejection-ready metadata while remaining DuckDB-compatible for later deterministic extraction and catalog queries.

- **2026-05-10 — Single-track execution.**
  The project no longer uses a three-person Core/Data/UI workstream split. Future agents should execute the canonical Phase 1 plans directly and should not recreate owner-specific onboarding docs.

- **2026-05-10 — Single active phase.**
  The roadmap intentionally contains no numbered follow-up phases for the current milestone. If future phases are needed, they must be added explicitly after Phase 1 verification.

- **2026-05-09 — GSD adopted as the primary Codex project workflow.**
  Use GSD for phase discussion, planning, execution, and verification; keep `.planning/*` as durable project memory.

- **2026-05-09 — Yandex AI Studio API smoke test passed.**
  DeepSeek 3.2 responded through the OpenAI-compatible Chat Completions endpoint with model URI `gpt://b1gbntotj1b57karq6qm/deepseek-v32/latest` and endpoint `https://llm.api.cloud.yandex.net/v1/chat/completions`.
  The API key itself must stay outside git in environment variables or local `.env`.
  Important gotcha: the folder id inside `gpt://<folder_id>/...` must match the service account folder. A mismatched folder returns `permission_error`.

## Known Inputs From Task

- Yandex AI Studio / Yandex Cloud is recommended by the case materials.
- UI must not be a messenger bot; Streamlit is the first demo UI target unless changed by a plan.
- Numeric values must come from deterministic code, not from LLM table reading.
- Main data candidates: local Rosstat/EMISS and World Bank dumps, plus NSED CKAN API.

## Open Questions

- [x] Скачать данные с Yandex Disk (~3.5 GB) — verified at `/Users/a/Downloads/dumps`
- [x] Получить API-ключ Yandex AI Studio для smoke test
- [x] Получить рабочий folder_id Yandex Cloud for DeepSeek 3.2 smoke test: `b1gbntotj1b57karq6qm`
- [x] Понять фактическую структуру локального дампа после скачивания — summarized in `.planning/DATA_REPORT.md`
- [x] Create the 15-20 case golden set in `01-01-PLAN.md`
- [x] Finish revised prepared-data, source-card catalog, and embedding-corpus contract in `01-02-PLAN.md` with executable builder verification
- [x] Materialize Qdrant embedding/search index and retrieval relevance eval in revised `01-03-PLAN.md`
- [x] Define and verify orchestration, deterministic extraction, data-relevance eval, and diagnostic UI trace contract through revised `01-04`
- [x] Package the integrated demo path through revised `01-05`

## Recommended Next Action

Phase 1 plans are complete and accepted only as infrastructure. Phase 2 execution now has summaries for all 10 accepted plans. Next:

1. Stay on `codex/phase-2-jury-mvp-planning`.
2. Keep unrelated embedding-experiment dirty files isolated from Phase 2 planning commits.
3. Run `$gsd-verify-work 2`.
4. Complete or approve the manual Streamlit UAT checkpoint recorded in `.planning/phases/02-jury-mvp/manual-uat.md`.
5. Preserve the all-20 golden acceptance target and do not accept stale/gated/skipped/no_candidate final states.

## Session Continuity

Last session: 2026-05-11T00:00:00Z
Stopped at: Committed external workflow audit layer (e99bfbb); next: fix workflow defects exposed by audit evidence
Resume file: None

---
## Performance Metrics

- 2026-05-10 — Phase `02-jury-mvp`, Plan `01`: 3 min, 3 tasks, 4 artifact/code/test files.
- 2026-05-10 — Phase `02-jury-mvp`, Plan `03`: 6 min, 3 tasks, 6 artifact/code/test files.
- 2026-05-10 — Phase `02-jury-mvp`, Plan `09`: 6 min, 3 tasks, 7 artifact/code/test files.
- 2026-05-10 — Phase `02-jury-mvp`, Plan `08`: 65 min, 3 tasks, 13 artifact/code/test files.
- 2026-05-10 — Phase `01-data-architecture-research`, Plan `01`: 1 min, 3 tasks, 3 artifact files.
- 2026-05-10 — Phase `01-data-architecture-research`, Plan `02`: 5 min, 2 tasks, 15 artifact/code/test files.
- 2026-05-10 — Phase `01-data-architecture-research`, Plan `03`: 7 min, 2 tasks, 12 artifact/code/test files.
- 2026-05-10 — Phase `01-data-architecture-research`, Plan `04`: 8 min, 4 tasks, 27 artifact/code/test files.
- 2026-05-10 — Phase `01-data-architecture-research`, Plan `05`: 9 min, 2 tasks, 14 artifact/code/test files.

---
*Last updated: 2026-05-10 after Phase 2 plan 02-08 execution*
