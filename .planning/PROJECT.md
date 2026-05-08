# DataAgent — ИИ-ассистент для экономистов

## What This Is

ИИ-ассистент, который принимает запрос экономиста на естественном языке (от абстрактного «изучить торговлю между Россией и Казахстаном» до конкретного «динамика ВВП стран БРИКС за 2015–2024») и выполняет полный цикл работы data-специалиста: формализует исследование, проектирует целевой датасет, находит подходящие источники в реестре, генерирует скрипт сборки и собирает итоговый датасет. Целевая аудитория — экономисты, социологи, маркетологи, журналисты: люди, которым нужна информация, а не навыки работы с данными.

## Core Value

**Опора на факты из реальных данных, а не на «память» LLM.** Каждая цифра — со ссылкой на источник; если данных нет — честное сообщение, а не галлюцинация. Требование ТЗ: числа из датасетов должен извлекать детерминированный код, а не LLM.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Приём NL-запросов 6 типов: простые, сравнительные, исследовательские, производные метрики, неоднозначные, «нет данных»
- [ ] Формализация запроса в определение исследования (география, временные рамки, ракурс, вопросы)
- [ ] Уточняющий диалог для неоднозначных запросов
- [ ] Проектирование исследования (гипотезы, измерения, индикаторы, группировки)
- [ ] Определение структуры целевого датасета (зернистость, измерения, единицы)
- [ ] Поиск по реестру метаданных Росстата и World Bank (конкретный механизм не выбран)
- [ ] Детерминированное извлечение данных через код (SQL/pandas/DuckDB), не LLM
- [ ] Генерация Python-скрипта сборки датасета
- [ ] Сборка итогового датасета с метаданными и ссылками на источники
- [ ] Каждая цифра в ответе сопровождается ссылкой на источник
- [ ] Честное сообщение «данных нет» при отсутствии информации
- [ ] Промежуточные артефакты на каждом шаге (определение, дизайн, структура, скрипт, файл)
- [ ] Прозрачный «след» работы ассистента (какие шаги, какие источники, какие отверг)
- [ ] UI — Streamlit/Gradio/web UI/CLI (НЕ мессенджер-бот; конкретный вариант не выбран)
- [ ] Воспроизводимость: README, requirements.txt, инструкция по запуску

### Out of Scope

- Мессенджер-бот (Telegram, WhatsApp) — явный запрет ТЗ, требуется независимость от платформ
- Fine-tuning LLM — дополнительное направление на будущее, не MVP
- Платные/закрытые базы данных — запрет ТЗ
- Проприетарные библиотеки — запрет ТЗ
- Авторизация/мультитенантность — прототип-демонстратор, не production
- Развёрнутая визуализация (графики, дашборды) — nice-to-have, не core

## Context

**Хакатон:** VI Весенняя школа ИТ и ИИ, 8–13 мая 2026
**Кейс:** НЦСЭД (nsedc.ru) + Yandex Cloud
**Контакт:** Дмитрий Сошников @shwars

**Данные (основные, ~3.5 GB):**
- Росстат (ЕМИСС): metadata.jsonl, parquet/{code}.parquet, clean_jsonl
- World Bank: parquet/{indicator_id}.parquet, indicators.json (29K+), countries.json (296)
- Скачать: https://disk.yandex.ru/d/M4FR84WYcuF4TA

**Данные (бонус):**
- НЦСЭД API (CKAN): https://repository.nsedc.ru/api/3/action/package_search

**Тест-кейсы:** 15–20 пар «запрос → ожидаемый результат» разной сложности

**Референсная реализация:** Agent.py в репо — обёртка над Yandex Cloud Responses API с function calling, web_search, file_search, MCP

**Оценка (100 баллов):**
- Качество на тест-кейсах: 35
- Устойчивость и честность: 25
- Качество инженерии: 20
- Продуктовое качество: 20

## Constraints

### Жёсткие / явно заданные в ТЗ

- **LLM / AI-инструменты**: использовать возможности, доступные через Yandex Cloud / Yandex AI Studio; точная модель и SDK-обвязка пока исследуются
- **Числа из данных**: Только детерминированный код — LLM не читает таблицы, не интерпретирует значения
- **Источники**: Каждая цифра — со ссылкой; «цифра без источника» = ошибка
- **Библиотеки**: Только open-source
- **Данные**: Основной реестр + открытые верифицированные источники (не платные, не блоги)
- **UI**: НЕ мессенджер-бот; Streamlit / Gradio / web UI / CLI — на выбор команды
- **Воспроизводимость**: README + requirements.txt + инструкция по запуску
- **Дедлайн**: 13 мая 2026

### Открытые вопросы (решаются в фазе исследования)

- **Поиск по метаданным**: FAISS локально vs File Search Yandex AI Studio vs DuckDB FTS
- **Извлечение данных**: DuckDB SQL vs pandas vs оба
- **Стратегия индексации**: Векторный поиск vs keyword search vs гибрид
- **Модель**: YandexGPT vs Qwen3 vs DeepSeek — зависит от качества на тест-кейсах
- **Оркестрация**: OpenAI Agents SDK vs LangChain vs голый loop
- **UI фреймворк**: Streamlit vs Gradio vs CLI + thin web layer
- **Источники данных**: Приоритет локальных дампов vs live API — зависит от покрытия

## Decision Candidates

> Решений пока нет. Ниже — варианты и ограничения из ТЗ, которые нужно проверить экспериментами.

| Area | Candidates / constraint | Status |
|------|-------------------------|--------|
| LLM/API | YandexGPT / Qwen / DeepSeek через Yandex AI Studio или совместимый API | Open |
| Agent loop | OpenAI Responses-style loop / OpenAI Agents SDK / LangChain / custom loop | Open |
| Поиск по метаданным | Keyword/BM25/FTS / vector search / hybrid / AI Studio File Search | Open |
| Чтение Parquet | pandas / DuckDB / pyarrow / комбинация | Open |
| Источники | локальные дампы / CKAN API / World Bank API / комбинация | Open |
| UI | Streamlit / Gradio / web UI / CLI | Open |
| Numeric extraction | Должен выполняться детерминированным кодом | Constraint |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-08 after correcting discovery state — decisions not made*
