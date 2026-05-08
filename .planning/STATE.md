# Project State: DataAgent

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-08)

**Core value:** Опора на факты — каждая цифра со ссылкой, числа извлекает код, не LLM
**Current focus:** Phase 1 — Ядро агента (NLU + RAG + поиск данных)

## Current Phase

**Phase:** 1 of 3
**Name:** Ядро агента — NLU + RAG + поиск данных
**Status:** Not started
**Plan:** Not created yet — run `/gsd-plan-phase 1`

## Phase History

(None yet)

## Decisions Log

| Date | Decision | Context |
|------|----------|---------|
| 2026-05-08 | Yandex AI Studio + OpenAI SDK | Обязательное требование ТЗ |
| 2026-05-08 | Streamlit для UI | Быстрый прототип, не мессенджер |
| 2026-05-08 | RAG по метаданным | Эффективный поиск по 29K+ индикаторов |
| 2026-05-08 | pandas для Parquet | Детерминированный код, требование ТЗ |
| 2026-05-08 | Coarse granularity (3 фазы) | Хакатон — 5 дней, максимальная скорость |

## Blockers

- [ ] Скачать данные с Yandex Disk (~3.5 GB)
- [ ] Получить API-ключ Yandex AI Studio
- [ ] Получить folder_id Yandex Cloud

---
*Last updated: 2026-05-08 after initialization*
