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

No decisions yet. Current work is exploratory: understand the task, data formats, evaluation criteria, and possible implementation paths.

## Known Inputs From Task

- Yandex AI Studio / Yandex Cloud is recommended by the case materials; exact model and SDK usage still need validation.
- UI must not be a messenger bot; Streamlit, Gradio, web UI, or CLI are possible options.
- Numeric values must come from deterministic code, not from LLM table reading.
- Main data candidates: local Rosstat/EMISS and World Bank dumps, plus optional NSED CKAN API.

## Open Questions

- [ ] Скачать данные с Yandex Disk (~3.5 GB)
- [ ] Получить API-ключ Yandex AI Studio
- [ ] Получить folder_id Yandex Cloud
- [ ] Понять фактическую структуру локального дампа после скачивания
- [ ] Выбрать несколько тестовых запросов для первичного анализа
- [ ] Сравнить варианты поиска по метаданным и извлечения данных

---
*Last updated: 2026-05-08 after correcting discovery state*
