# Project State: DataAgent

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-08)

**Core value:** Опора на факты — каждая цифра со ссылкой, числа извлекает код, не LLM
**Current focus:** Изучение требований, данных и вариантов реализации

## Current Phase

**Phase:** Discovery
**Name:** Разбор ТЗ, доступных данных и возможного MVP
**Status:** In progress
**Plan:** Не создан — решений по стеку и скоупу пока нет

## Phase History

(None yet)

## Decisions Log

- **2026-05-09 — GSD adopted as the primary Codex project workflow.**
  Installed GSD v1.41.1 globally for Codex into `C:\Users\HONOR\.codex` with 66 skills, 33 agent roles, hooks, and `gsd-sdk`.
  Project config now sets `runtime: "codex"` and `resolve_model_ids: "omit"` so GSD does not force Anthropic model identifiers.
  Use GSD for phase discussion, planning, execution, and verification; keep `.planning/*` as durable project memory.

- **2026-05-09 — Yandex AI Studio API smoke test passed.**
  DeepSeek 3.2 responds through the OpenAI-compatible Chat Completions endpoint with model URI `gpt://b1gbntotj1b57karq6qm/deepseek-v32/latest` and endpoint `https://llm.api.cloud.yandex.net/v1/chat/completions`.
  The API key itself must stay outside git in environment variables or local `.env`.
  Important gotcha: the folder id inside `gpt://<folder_id>/...` must match the service account folder. A mismatched folder returns `permission_error`.

## Known Inputs From Task

- Yandex AI Studio / Yandex Cloud is recommended by the case materials; exact model and SDK usage still need validation.
- UI must not be a messenger bot; Streamlit, Gradio, web UI, or CLI are possible options.
- Numeric values must come from deterministic code, not from LLM table reading.
- Main data candidates: local Rosstat/EMISS and World Bank dumps, plus optional NSED CKAN API.

## Open Questions

- [ ] Скачать данные с Yandex Disk (~3.5 GB)
- [x] Получить API-ключ Yandex AI Studio для smoke test
- [x] Получить рабочий folder_id Yandex Cloud для DeepSeek 3.2 smoke test: `b1gbntotj1b57karq6qm`
- [ ] Понять фактическую структуру локального дампа после скачивания
- [ ] Выбрать несколько тестовых запросов для первичного анализа
- [ ] Сравнить варианты поиска по метаданным и извлечения данных

---
*Last updated: 2026-05-09 after Yandex AI Studio DeepSeek smoke test*
