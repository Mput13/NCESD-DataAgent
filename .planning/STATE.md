# Project State: DataAgent

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** Опора на факты — каждая цифра со ссылкой, числа извлекает код, не LLM  
**Current focus:** Phase 1 Data Architecture Implementation

## Current Phase

**Phase:** 1  
**Slug:** `01-data-architecture-research`  
**Name:** Data Architecture Implementation  
**Status:** Planned, not executed  
**Canonical directory:** `.planning/phases/01-data-architecture-research`  
**Next action:** execute `01-01-PLAN.md` first, then continue through `01-05-PLAN.md` in dependency order.

## Phase Boundary

The current milestone has exactly one active phase. Despite the historical slug, Phase 1 is implementation-oriented: it should produce code, scripts, tests, data/retrieval/extraction evidence, and UI trace contracts where the plans require them.

Phase 1 is not a license to build an unverified full product in one jump. Each slice must follow its plan, produce its expected artifacts, run its verification commands, and write the corresponding `01-xx-SUMMARY.md`.

## Phase History

- **2026-05-10 — Planning reset to one canonical phase.**
  Removed the failed core/workflow skeleton, deprecated duplicate Phase 1 directory, forensic incident artifact, and three-person workstream documents from the active tree.
  The active roadmap now has one phase only: `.planning/phases/01-data-architecture-research`.

- **2026-05-09 — Phase 1 context gathered.**
  Captured implementation decisions in `.planning/phases/01-data-architecture-research/01-CONTEXT.md`, based on `.planning/ARCHITECTURE_STACK.md`.
  Phase 1 should follow the architecture stack fully, include FedStat + World Bank + CKAN from the start, prepare 15-20 test cases, and prioritize visible multi-agent trace/UI impact while preserving source-bound deterministic extraction.

## Current Repository Surface

- `app/llm/yandex_ai_studio.py` — existing minimal Yandex AI Studio chat-completions client.
- `docs/PROJECT_WORKFLOW.md` — GSD workflow explanation for the project.
- `requirements.txt` — currently only `python-dotenv` and `requests`; plans must update it when adding dependencies.
- No accepted data adapters, retrieval modules, LangGraph workflow, Streamlit UI, tests, or eval cases are currently implemented.

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
- [ ] Create the 15-20 case golden set in `01-01-PLAN.md`
- [ ] Compare and implement the first retrieval/extraction slices through `01-02` and `01-03`
- [ ] Define and verify the orchestration/UI trace contract through `01-04` and `01-05`

## Recommended Next Action

Run the existing Phase 1 plans in order:

1. Execute `.planning/phases/01-data-architecture-research/01-01-PLAN.md`.
2. Create `.planning/phases/01-data-architecture-research/01-01-SUMMARY.md`.
3. Continue with `01-02`, `01-03`, `01-04`, and `01-05` only after dependencies and verification commands pass.
4. Run `$gsd-verify-work 1` after all five summaries exist.

---
*Last updated: 2026-05-10 after single-phase cleanup*
