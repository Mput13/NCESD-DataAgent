# Project State: DataAgent

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-08)

**Core value:** Опора на факты — каждая цифра со ссылкой, числа извлекает код, не LLM
**Current focus:** Изучение требований, данных и вариантов реализации

## Current Phase

**Phase:** Discovery
**Name:** Разбор ТЗ, доступных данных и возможного MVP
**Status:** In progress
**Plan:** Не создан — Phase 1 пока не обсуждалась/планировалась через GSD

## Phase History

(None yet)

## Resume Snapshot

**Refreshed:** 2026-05-09 14:24 MSK
**Git:** `main` clean, aligned with `origin/main` at `2eedf5c`
**GSD init:** planning/project/roadmap/state exist; no interrupted agents
**Incomplete work:** no `.planning/HANDOFF.json`, no `.continue-here` files, no phase `PLAN` files without `SUMMARY`
**Phase artifacts:** `.planning/phases/` does not exist yet; Phase 1 has not been discussed/planned/executed in GSD

**Repository implementation surface:**
- `app/llm/yandex_ai_studio.py` — small OpenAI-compatible Yandex AI Studio chat completions client with model profiles
- `docs/PROJECT_WORKFLOW.md` — GSD workflow explanation for the project
- `requirements.txt` — currently only `python-dotenv` and `requests`
- No data catalog builders, extractors, retrieval tools, Streamlit UI, LangGraph graph, tests, or eval cases are implemented yet

**Verified local data locations:**
- `/Users/a/Downloads/dumps/fedstatru/fedstatru.zip`
- `/Users/a/Downloads/dumps/wb/data.zip`
- `/Users/a/Downloads/dumps.zip`
- Dumps are intentionally not committed; repo `.gitignore` excludes dumps, zip/parquet/jsonl/pdf and keeps `.planning/`

**Current research baseline:**
- `.planning/DATA_REPORT.md` maps FedStat, World Bank, and NSED CKAN API. It identifies World Bank as the easiest reliable first extractor and FedStat as requiring a wide-to-long normalizer.
- `.planning/ARCHITECTURE_STACK.md` describes the preferred target architecture: Qwen/Yandex AI Studio, LangGraph hierarchical supervisor, source scouts, deterministic DuckDB/PyArrow extraction, Streamlit trace/artifacts UI, and pytest golden evals.
- `.planning/YANDEX_AI_STUDIO_RESEARCH.md` records that DeepSeek 3.2 was smoke-tested through Yandex AI Studio. Runtime environment variables are not currently exported in this shell.

**Important alignment note:** PROJECT/ROADMAP still frame Phase 1 as research before implementation. ARCHITECTURE_STACK contains a strong recommended stack, but Phase 1 GSD discussion should explicitly confirm the MVP slice before code work.

## Decisions Log

- **2026-05-09 — GSD adopted as the primary Codex project workflow.**
  Installed GSD v1.41.1 globally for Codex into `C:\Users\HONOR\.codex` with 66 skills, 33 agent roles, hooks, and `gsd-sdk`.
  Project config now sets `runtime: "codex"` and `resolve_model_ids: "omit"` so GSD does not force Anthropic model identifiers.
  Use GSD for phase discussion, planning, execution, and verification; keep `.planning/*` as durable project memory.

- **2026-05-09 — Yandex AI Studio API smoke test passed.**
  DeepSeek 3.2 responds through the OpenAI-compatible Chat Completions endpoint with model URI `gpt://b1gbntotj1b57karq6qm/deepseek-v32/latest` and endpoint `https://llm.api.cloud.yandex.net/v1/chat/completions`.
  The API key itself must stay outside git in environment variables or local `.env`.
  Important gotcha: the folder id inside `gpt://<folder_id>/...` must match the service account folder. A mismatched folder returns `permission_error`.

- **2026-05-09 — Context rebuilt from repository state, not stale handoff.**
  Resume workflow found no active handoff/checkpoint/incomplete plan. Durable context now points to Phase 1 as the next workflow step, with local dumps verified under `/Users/a/Downloads/dumps`.

## Known Inputs From Task

- Yandex AI Studio / Yandex Cloud is recommended by the case materials; exact model and SDK usage still need validation.
- UI must not be a messenger bot; Streamlit, Gradio, web UI, or CLI are possible options.
- Numeric values must come from deterministic code, not from LLM table reading.
- Main data candidates: local Rosstat/EMISS and World Bank dumps, plus optional NSED CKAN API.

## Open Questions

- [x] Скачать данные с Yandex Disk (~3.5 GB) — verified at `/Users/a/Downloads/dumps`
- [x] Получить API-ключ Yandex AI Studio для smoke test
- [x] Получить рабочий folder_id Yandex Cloud для DeepSeek 3.2 smoke test: `b1gbntotj1b57karq6qm`
- [x] Понять фактическую структуру локального дампа после скачивания — summarized in `.planning/DATA_REPORT.md`
- [ ] Выбрать несколько тестовых запросов для первичного анализа
- [ ] Сравнить варианты поиска по метаданным и извлечения данных

## Recommended Next Action

Run Phase 1 through GSD from fresh context:

1. `$gsd-discuss-phase 1` — confirm MVP slice and stack decisions from the research notes.
2. `$gsd-plan-phase 1` — split into small verifiable plans, likely starting with catalog/extractor spikes.
3. `$gsd-execute-phase 1` — implement only after the plan exists.

---
*Last updated: 2026-05-09 after rebuilding project context from current repository state*
