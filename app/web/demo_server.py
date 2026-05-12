"""Demo server with hardcoded fake cases for presentations.

Intercepts /api/stream and routes to scripted scenarios based on query keywords.
All other routes delegate to the real static file handler.

Usage:
    python -m app.web.demo_server
"""
from __future__ import annotations

import json
import time
import uuid
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

STATIC_DIR = Path(__file__).resolve().parent / "static"


# ---------------------------------------------------------------------------
# Fake scenario data
# ---------------------------------------------------------------------------

def _run_id() -> str:
    return "phase2-" + uuid.uuid4().hex[:12]


def _ts(offset_s: float = 0.0) -> str:
    import datetime
    t = datetime.datetime.utcnow() + datetime.timedelta(seconds=offset_s)
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


# --- Case 1: ВВП России ---

def _case_gdp_russia(run_id: str) -> list[dict]:
    """Yields (delay_s, event_type, payload) tuples."""
    steps = []

    # Step 1 — supervisor
    steps.append((0.35, "step", {
        "node": "supervisor",
        "description": "Супервизор анализирует запрос и выбирает маршрут исследования...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "supervisor", "agent": "Supervisor",
            "input_summary": "Какой ВВП России в 2022 году?",
            "tool_calls": ["triage_llm"],
            "output_artifact": None, "decision": "research",
            "warnings": [], "started_at": _ts(0), "duration_ms": 312, "payload": {},
        }],
    }))

    # Step 2 — intent_analyst
    steps.append((0.55, "step", {
        "node": "intent_analyst",
        "description": "Анализатор намерений разбирает запрос: показатель=ВВП, период=2022, география=Россия...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "intent_analyst", "agent": "Intent Analyst",
            "input_summary": "indicator=ВВП, period=2022, geo=Россия",
            "tool_calls": ["intent_llm"],
            "output_artifact": "IntentFrame", "decision": "ok",
            "warnings": [], "started_at": _ts(0.35), "duration_ms": 498, "payload": {},
        }],
    }))

    # Step 3 — research_designer
    steps.append((0.9, "step", {
        "node": "research_designer",
        "description": "Дизайнер исследования строит гипотезы: ВВП по ППС и номинальный, источники — Росстат и World Bank...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "research_designer", "agent": "Research Designer",
            "input_summary": "hypotheses=[nominal_gdp, ppp_gdp], dimensions=[fedstat, world_bank]",
            "tool_calls": ["research_llm"],
            "output_artifact": "research-design-57d48ec6", "decision": "ok",
            "warnings": [], "started_at": _ts(0.9), "duration_ms": 831, "payload": {},
        }],
    }))

    # Step 4 — source_scouts
    steps.append((1.2, "step", {
        "node": "source_scouts",
        "description": "Разведчики источников ищут данные в FedStat, World Bank, CKAN...",
        "run_id": run_id,
        "new_trace_events": [
            {
                "run_id": run_id, "state": "source_scouts", "agent": "FedStat Scout",
                "input_summary": "Найден: Федеральная служба государственной статистики — ВВП в текущих ценах",
                "tool_calls": ["hybrid_search"],
                "output_artifact": "EvidenceBundleArtifact", "decision": "ok",
                "warnings": [], "started_at": _ts(1.8), "duration_ms": 620, "payload": {},
            },
            {
                "run_id": run_id, "state": "source_scouts", "agent": "World Bank Scout",
                "input_summary": "Найден: World Bank — NY.GDP.MKTP.CD (Россия, 2022)",
                "tool_calls": ["hybrid_search"],
                "output_artifact": "EvidenceBundleArtifact", "decision": "ok",
                "warnings": [], "started_at": _ts(1.9), "duration_ms": 710, "payload": {},
            },
            {
                "run_id": run_id, "state": "source_scouts", "agent": "CKAN Scout",
                "input_summary": "Найден: data.gov.ru — ВВП субъектов РФ, агрегировано",
                "tool_calls": ["hybrid_search"],
                "output_artifact": "EvidenceBundleArtifact", "decision": "ok",
                "warnings": [], "started_at": _ts(2.0), "duration_ms": 590, "payload": {},
            },
        ],
    }))

    # Step 5 — coverage_schema
    steps.append((0.6, "step", {
        "node": "coverage_schema",
        "description": "Проверка покрытия: период 2022 есть, единицы — млрд руб. и USD, схема совместима...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "coverage_schema", "agent": "Coverage & Schema",
            "input_summary": "periods=[2022], units=[млрд руб, USD], status=covered",
            "tool_calls": ["coverage_check"],
            "output_artifact": "CoverageReport", "decision": "ok",
            "warnings": [], "started_at": _ts(3.1), "duration_ms": 403, "payload": {},
        }],
    }))

    # Step 6 — extraction_planner
    steps.append((0.75, "step", {
        "node": "extraction_planner",
        "description": "Планировщик извлечения строит SQL-запрос к FedStat (primary) и World Bank (secondary)...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "extraction_planner", "agent": "Extraction Planner",
            "input_summary": "plan: SELECT * FROM fedstat WHERE indicator='ВВП' AND year=2022",
            "tool_calls": ["plan_llm"],
            "output_artifact": "extraction-plan-f3423fff", "decision": "ok",
            "warnings": [], "started_at": _ts(3.5), "duration_ms": 669, "payload": {},
        }],
    }))

    # Step 7 — deterministic_tools
    steps.append((1.1, "step", {
        "node": "deterministic_tools",
        "description": "Детерминированные инструменты извлекают данные из FedStat и World Bank...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "deterministic_tools", "agent": "Deterministic Tools",
            "input_summary": "source_family=fedstat, plan=extraction-plan-f3423fff, rows=12",
            "tool_calls": ["duckdb_query", "worldbank_api"],
            "output_artifact": "dataset-gdp-russia-2022", "decision": "ok",
            "warnings": [], "started_at": _ts(4.2), "duration_ms": 980, "payload": {},
        }],
    }))

    # Step 8 — finalization
    steps.append((0.8, "step", {
        "node": "finalization_pending",
        "description": "Критик проверяет качество данных, нарратор пишет ответ...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "finalization_pending", "agent": "Supervisor",
            "input_summary": "critique=pass, narrative=ready",
            "tool_calls": ["critic_llm", "narrator_llm"],
            "output_artifact": None, "decision": "finalization_pending",
            "warnings": [], "started_at": _ts(5.3), "duration_ms": 712, "payload": {},
        }],
    }))

    # Done
    gdp_records = [
        {"geo_id": "643", "geo_name": "Россия", "indicator_name": "ВВП в текущих ценах",
         "period": "2017", "value": 92082.0, "unit": "млрд руб.", "quality_flags": ["official"]},
        {"geo_id": "643", "geo_name": "Россия", "indicator_name": "ВВП в текущих ценах",
         "period": "2018", "value": 103862.0, "unit": "млрд руб.", "quality_flags": ["official"]},
        {"geo_id": "643", "geo_name": "Россия", "indicator_name": "ВВП в текущих ценах",
         "period": "2019", "value": 109193.0, "unit": "млрд руб.", "quality_flags": ["official"]},
        {"geo_id": "643", "geo_name": "Россия", "indicator_name": "ВВП в текущих ценах",
         "period": "2020", "value": 106967.0, "unit": "млрд руб.", "quality_flags": ["official"]},
        {"geo_id": "643", "geo_name": "Россия", "indicator_name": "ВВП в текущих ценах",
         "period": "2021", "value": 130775.0, "unit": "млрд руб.", "quality_flags": ["official"]},
        {"geo_id": "643", "geo_name": "Россия", "indicator_name": "ВВП в текущих ценах",
         "period": "2022", "value": 151455.0, "unit": "млрд руб.", "quality_flags": ["official"]},
    ]

    done_payload = {
        "run_id": run_id,
        "final_outcome": "passed",
        "message": (
            "ВВП России в 2022 году составил 151 455 млрд рублей в текущих ценах "
            "(около 2,24 трлн USD по среднегодовому курсу). Это рост на +15,8% к 2021 году "
            "в номинальном выражении. Реальный рост ВВП в 2022 году составил −2,1% — "
            "сказалось давление санкций, введённых после февраля 2022 года: ограничения экспорта, "
            "уход западных компаний и сокращение инвестиций. Вместе с тем курсовая переоценка "
            "и сохранение внутреннего спроса поддержали номинальные показатели. "
            "Хотите сравнить динамику ВВП России с другими крупными экономиками за тот же период?"
        ),
        "answer_blocks": [
            {"type": "summary", "text": (
                "ВВП России в 2022 году: 151 455 млрд руб. (≈ 2,24 трлн USD). "
                "Реальный рост: −2,1% г/г — давление санкций компенсировалось "
                "курсовой переоценкой и поддержкой внутреннего потребления."
            )},
            {"type": "methodology", "text": (
                "Данные: Росстат (FedStat), методология СНС 2008. "
                "Перевод в USD — среднегодовой курс ЦБ РФ (68,5 руб/USD)."
            )},
            {"type": "how_found", "text": (
                "Агент обнаружил показатель в базе FedStat (indicator_id=31074). "
                "World Bank подтвердил значение по NY.GDP.MKTP.CD. CKAN предоставил региональную разбивку."
            )},
            {"type": "limitations", "items": [
                "Данные за 2022 год могут быть пересмотрены Росстатом в 2024–2025 гг.",
                "Перевод в USD чувствителен к методу расчёта среднегодового курса.",
                "Региональная разбивка доступна с лагом 6–9 месяцев.",
            ]},
        ],
        "dataset_artifacts": [{
            "artifact_id": "dataset-gdp-russia-2022",
            "source_id": "fedstat",
            "rows": len(gdp_records),
            "columns": ["geo_id", "geo_name", "indicator_name", "period", "value", "unit"],
            "csv_path": None,
            "parquet_path": None,
            "records": gdp_records,
        }],
        "selected_sources": [
            {
                "source_id": "fedstat",
                "title": "Росстат — ВВП в текущих ценах (31074)",
                "source_family": "fedstat",
                "provenance_url": "https://fedstat.ru/indicator/31074",
            },
            {
                "source_id": "worldbank",
                "title": "World Bank — NY.GDP.MKTP.CD (Россия)",
                "source_family": "worldbank",
                "provenance_url": "https://data.worldbank.org/indicator/NY.GDP.MKTP.CD?locations=RU",
            },
            {
                "source_id": "ckan",
                "title": "data.gov.ru — ВВП субъектов РФ",
                "source_family": "ckan",
                "provenance_url": "https://data.gov.ru/opendata/7708234383-vvp",
            },
        ],
        "visualization": {
            "status": "ok",
            "chart_type": "line",
            "dataset_artifact_id": "dataset-gdp-russia-2022",
            "encoding": {
                "spec": {
                    "datasets": {
                        "dataset-gdp-russia-2022": gdp_records,
                    }
                }
            },
        },
        "trace_events": [],
    }

    steps.append((0.0, "done", done_payload))
    return steps


# --- Case 2: Данные не найдены ---

def _case_not_found(run_id: str, query: str) -> list[dict]:
    steps = []

    steps.append((0.4, "step", {
        "node": "supervisor",
        "description": "Супервизор анализирует запрос и выбирает маршрут исследования...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "supervisor", "agent": "Supervisor",
            "input_summary": query,
            "tool_calls": ["triage_llm"],
            "output_artifact": None, "decision": "research",
            "warnings": [], "started_at": _ts(0), "duration_ms": 358, "payload": {},
        }],
    }))

    steps.append((0.5, "step", {
        "node": "intent_analyst",
        "description": "Анализатор намерений разбирает запрос: показатель определён, ищем источники...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "intent_analyst", "agent": "Intent Analyst",
            "input_summary": "indicator=определён, period=неизвестен, geo=определена",
            "tool_calls": ["intent_llm"],
            "output_artifact": "IntentFrame", "decision": "ok",
            "warnings": [], "started_at": _ts(0.4), "duration_ms": 441, "payload": {},
        }],
    }))

    steps.append((0.85, "step", {
        "node": "research_designer",
        "description": "Дизайнер исследования строит гипотезы и выбирает измерения...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "research_designer", "agent": "Research Designer",
            "input_summary": "hypotheses=[3 варианта], dimensions=[fedstat, worldbank, ckan, eurostat]",
            "tool_calls": ["research_llm"],
            "output_artifact": "research-design-aabb1234", "decision": "ok",
            "warnings": [], "started_at": _ts(0.9), "duration_ms": 778, "payload": {},
        }],
    }))

    steps.append((1.3, "step", {
        "node": "source_scouts",
        "description": "Разведчики источников ищут данные в FedStat, World Bank, CKAN... без результата",
        "run_id": run_id,
        "new_trace_events": [
            {
                "run_id": run_id, "state": "source_scouts", "agent": "FedStat Scout",
                "input_summary": "Поиск: 0 результатов по запросу в FedStat",
                "tool_calls": ["hybrid_search"],
                "output_artifact": None, "decision": "not_found",
                "warnings": ["fedstat: нет подходящих индикаторов для данного запроса"],
                "started_at": _ts(1.7), "duration_ms": 601, "payload": {},
            },
            {
                "run_id": run_id, "state": "source_scouts", "agent": "World Bank Scout",
                "input_summary": "Поиск: World Bank API вернул 0 совпадений",
                "tool_calls": ["hybrid_search"],
                "output_artifact": None, "decision": "not_found",
                "warnings": ["worldbank: indicator не найден в каталоге"],
                "started_at": _ts(1.8), "duration_ms": 730, "payload": {},
            },
            {
                "run_id": run_id, "state": "source_scouts", "agent": "CKAN Scout",
                "input_summary": "Поиск: CKAN data.gov.ru — 0 датасетов по запросу",
                "tool_calls": ["hybrid_search"],
                "output_artifact": None, "decision": "not_found",
                "warnings": ["ckan: релевантных открытых наборов данных не найдено"],
                "started_at": _ts(1.9), "duration_ms": 558, "payload": {},
            },
        ],
    }))

    steps.append((0.55, "step", {
        "node": "coverage_schema",
        "description": "Проверка покрытия: ни один источник не вернул данных по запросу...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "coverage_schema", "agent": "Coverage & Schema",
            "input_summary": "coverage=empty, selected_sources=0",
            "tool_calls": ["coverage_check"],
            "output_artifact": "CoverageReport", "decision": "not_found",
            "warnings": ["Все источники вернули пустой результат"],
            "started_at": _ts(3.1), "duration_ms": 321, "payload": {},
        }],
    }))

    steps.append((0.6, "step", {
        "node": "finalization_pending",
        "description": "Критик подтверждает: данные отсутствуют. Нарратор формирует объяснение...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "finalization_pending", "agent": "Supervisor",
            "input_summary": "outcome=not_found",
            "tool_calls": ["critic_llm"],
            "output_artifact": None, "decision": "not_found",
            "warnings": [], "started_at": _ts(3.65), "duration_ms": 480, "payload": {},
        }],
    }))

    done_payload = {
        "run_id": run_id,
        "final_outcome": "not_found",
        "message": (
            "По данному запросу информация не найдена. "
            "Агенты проверили три основных источника (FedStat, World Bank, data.gov.ru) — "
            "ни один не содержит релевантных данных. Показатель либо не публикуется в открытом доступе, "
            "либо выходит за рамки охвата подключённых баз данных."
        ),
        "answer_blocks": [
            {"type": "not_found", "summary": (
                "Данные не найдены ни в одном из подключённых источников. "
                "FedStat, World Bank и data.gov.ru вернули пустой результат по данному запросу."
            )},
        ],
        "dataset_artifacts": [],
        "selected_sources": [],
        "visualization": None,
        "trace_events": [],
    }

    steps.append((0.0, "done", done_payload))
    return steps


# --- Case 3: Сравнение Китай vs Россия ---

def _case_comparison(run_id: str) -> list[dict]:
    steps = []

    steps.append((0.38, "step", {
        "node": "supervisor",
        "description": "Супервизор анализирует запрос: сравнение двух стран → маршрут полного исследования...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "supervisor", "agent": "Supervisor",
            "input_summary": "Сравните ВВП России и Китая за 2015–2023",
            "tool_calls": ["triage_llm"],
            "output_artifact": None, "decision": "research",
            "warnings": [], "started_at": _ts(0), "duration_ms": 341, "payload": {},
        }],
    }))

    steps.append((0.62, "step", {
        "node": "intent_analyst",
        "description": "Анализатор намерений: indicator=ВВП, geo=[Россия, Китай], period=2015–2023, mode=compare...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "intent_analyst", "agent": "Intent Analyst",
            "input_summary": "indicator=ВВП, geo=[RU,CN], period=[2015..2023], compare=True",
            "tool_calls": ["intent_llm"],
            "output_artifact": "IntentFrame", "decision": "ok",
            "warnings": [], "started_at": _ts(0.38), "duration_ms": 561, "payload": {},
        }],
    }))

    steps.append((1.05, "step", {
        "node": "research_designer",
        "description": "Дизайнер исследования: строим сравнительный план — номинальный ВВП USD, общий и на душу населения...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "research_designer", "agent": "Research Designer",
            "input_summary": "hypotheses=[nominal_usd, per_capita], dimensions=[worldbank, fedstat]",
            "tool_calls": ["research_llm"],
            "output_artifact": "research-design-comp-8fa2", "decision": "ok",
            "warnings": [], "started_at": _ts(1.0), "duration_ms": 921, "payload": {},
        }],
    }))

    steps.append((1.4, "step", {
        "node": "source_scouts",
        "description": "Разведчики источников: World Bank — NY.GDP.MKTP.CD для RU и CN, 2015–2023 — данные есть...",
        "run_id": run_id,
        "new_trace_events": [
            {
                "run_id": run_id, "state": "source_scouts", "agent": "World Bank Scout",
                "input_summary": "Найден: NY.GDP.MKTP.CD, страны=[RU,CN], годы=2015–2023 (9 точек × 2)",
                "tool_calls": ["hybrid_search", "worldbank_api"],
                "output_artifact": "EvidenceBundleArtifact", "decision": "ok",
                "warnings": [], "started_at": _ts(2.05), "duration_ms": 820, "payload": {},
            },
            {
                "run_id": run_id, "state": "source_scouts", "agent": "FedStat Scout",
                "input_summary": "Найден: FedStat — ВВП РФ в руб., конвертация по курсу ЦБ",
                "tool_calls": ["hybrid_search"],
                "output_artifact": "EvidenceBundleArtifact", "decision": "ok",
                "warnings": [], "started_at": _ts(2.1), "duration_ms": 690, "payload": {},
            },
        ],
    }))

    steps.append((0.65, "step", {
        "node": "coverage_schema",
        "description": "Проверка покрытия: оба ряда данных полны, единицы — трлн USD, схема совместима...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "coverage_schema", "agent": "Coverage & Schema",
            "input_summary": "coverage=full, periods=[2015..2023], units=[трлн USD], status=ok",
            "tool_calls": ["coverage_check"],
            "output_artifact": "CoverageReport", "decision": "ok",
            "warnings": [], "started_at": _ts(3.45), "duration_ms": 412, "payload": {},
        }],
    }))

    steps.append((0.8, "step", {
        "node": "extraction_planner",
        "description": "Планировщик извлечения: объединяем ряды RU и CN в единый датасет для графика сравнения...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "extraction_planner", "agent": "Extraction Planner",
            "input_summary": "plan: JOIN worldbank_RU + worldbank_CN ON year, pivot geo_name",
            "tool_calls": ["plan_llm"],
            "output_artifact": "extraction-plan-comp-9de1", "decision": "ok",
            "warnings": [], "started_at": _ts(4.1), "duration_ms": 723, "payload": {},
        }],
    }))

    steps.append((1.25, "step", {
        "node": "deterministic_tools",
        "description": "Детерминированные инструменты извлекают 18 строк данных (9 лет × 2 страны)...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "deterministic_tools", "agent": "Deterministic Tools",
            "input_summary": "rows=18, source_family=worldbank, plan=extraction-plan-comp-9de1",
            "tool_calls": ["worldbank_api", "duckdb_query"],
            "output_artifact": "dataset-gdp-comparison", "decision": "ok",
            "warnings": [], "started_at": _ts(4.9), "duration_ms": 1102, "payload": {},
        }],
    }))

    steps.append((0.9, "step", {
        "node": "finalization_pending",
        "description": "Критик проверяет ряды, нарратор строит сравнительный нарратив, визуализатор создаёт график...",
        "run_id": run_id,
        "new_trace_events": [{
            "run_id": run_id, "state": "finalization_pending", "agent": "Supervisor",
            "input_summary": "critique=pass, chart_type=grouped_line, narrative=ready",
            "tool_calls": ["critic_llm", "narrator_llm", "viz_agent"],
            "output_artifact": None, "decision": "finalization_pending",
            "warnings": [], "started_at": _ts(6.15), "duration_ms": 834, "payload": {},
        }],
    }))

    # Records for comparison chart
    years = list(range(2015, 2024))
    russia_gdp_trn = [1.363, 1.282, 1.578, 1.658, 1.700, 1.483, 1.779, 2.241, 2.009]
    china_gdp_trn  = [11.06, 11.23, 12.31, 13.89, 14.34, 14.73, 17.73, 17.96, 17.79]

    comp_records = []
    for i, yr in enumerate(years):
        comp_records.append({
            "geo_id": "643", "geo_name": "Россия",
            "indicator_name": "ВВП (трлн USD, номинальный)",
            "period": str(yr), "value": russia_gdp_trn[i],
            "unit": "трлн USD", "quality_flags": ["official"],
        })
        comp_records.append({
            "geo_id": "156", "geo_name": "Китай",
            "indicator_name": "ВВП (трлн USD, номинальный)",
            "period": str(yr), "value": china_gdp_trn[i],
            "unit": "трлн USD", "quality_flags": ["official"],
        })

    # For the sidebar mini-chart we need flat records grouped by Russia first then China
    russia_records = [r for r in comp_records if r["geo_name"] == "Россия"]

    done_payload = {
        "run_id": run_id,
        "final_outcome": "passed",
        "message": (
            "ВВП Китая в 2023 году составил 17,79 трлн USD — это в 8,8 раза больше ВВП России (2,01 трлн USD). "
            "За 2015–2023 годы Китай вырос на 61%, Россия — на 47% (с коррекцией в 2022–2023 из-за санкций). "
            "Разрыв между экономиками не сокращается: пик роста Китая пришёлся на 2021 год (+17,7 трлн), "
            "тогда как Россия в 2022 году показала снижение в долларовом выражении. "
            "График сравнения доступен для скачивания в панели артефактов."
        ),
        "answer_blocks": [
            {"type": "summary", "text": (
                "ВВП Китая (2023): 17,79 трлн USD. ВВП России (2023): 2,01 трлн USD. "
                "Разрыв — ×8,8. Китай стабильно растёт, Россия показала спад в реальном выражении в 2022 г."
            )},
            {"type": "methodology", "text": (
                "Источник: World Bank (NY.GDP.MKTP.CD), номинальный ВВП в текущих долларах США. "
                "Данные за 2023 год — предварительные оценки World Bank (апрель 2024)."
            )},
            {"type": "how_found", "text": (
                "Агент объединил ряды World Bank для RU и CN, проверил согласованность с FedStat (рублёвые данные), "
                "пересчитал по курсу ЦБ РФ для верификации."
            )},
            {"type": "limitations", "items": [
                "Данные 2023 года — предварительные, возможен пересмотр.",
                "Сравнение в USD чувствительно к курсовой динамике (девальвация рубля в 2022–2023).",
                "Для корректного сравнения продуктивности рекомендуется ВВП по ППС.",
            ]},
        ],
        "dataset_artifacts": [{
            "artifact_id": "dataset-gdp-comparison",
            "source_id": "worldbank",
            "rows": len(comp_records),
            "columns": ["geo_id", "geo_name", "indicator_name", "period", "value", "unit"],
            "csv_path": None,
            "parquet_path": None,
            "records": comp_records,
        }],
        "selected_sources": [
            {
                "source_id": "worldbank",
                "title": "World Bank — NY.GDP.MKTP.CD (RU + CN, 2015–2023)",
                "source_family": "worldbank",
                "provenance_url": "https://data.worldbank.org/indicator/NY.GDP.MKTP.CD?locations=RU-CN",
            },
            {
                "source_id": "fedstat",
                "title": "Росстат — ВВП РФ в текущих ценах (верификация)",
                "source_family": "fedstat",
                "provenance_url": "https://fedstat.ru/indicator/31074",
            },
        ],
        "visualization": {
            "status": "ok",
            "chart_type": "grouped_line",
            "dataset_artifact_id": "dataset-gdp-comparison",
            "encoding": {
                "spec": {
                    "datasets": {
                        "dataset-gdp-comparison": russia_records,  # mini chart shows Russia line
                    }
                }
            },
        },
        "trace_events": [],
    }

    steps.append((0.0, "done", done_payload))
    return steps


# ---------------------------------------------------------------------------
# Query routing
# ---------------------------------------------------------------------------

def _select_scenario(query: str, run_id: str) -> list[dict]:
    q = query.lower()

    # Case 3: comparison keywords
    if any(k in q for k in ["китай", "сравни", "сравнение", "china", "compare", "россия и китай", "китай и россия"]):
        return _case_comparison(run_id)

    # Case 2: no-data keywords (tricky / unknown stats)
    if any(k in q for k in [
        "уровень счастья", "индекс доверия", "цифровой суверенитет",
        "расход на ии", "ai расход", "расходы на ии", "смертность лосей",
        "нет данных", "not found", "nodata",
    ]):
        return _case_not_found(run_id, query)

    # Case 1: GDP Russia (default)
    return _case_gdp_russia(run_id)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class DemoHandler(SimpleHTTPRequestHandler):
    server_version = "DataAgentDemo/0.1"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass  # silence access log

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json({"status": "ok", "mode": "demo"})
            return
        if parsed.path == "/api/download":
            self._json({"error": "no files in demo mode"}, status=HTTPStatus.NOT_FOUND)
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/stream":
            try:
                body = self._body()
            except Exception as exc:
                self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._handle_demo_stream(body)
            return
        if parsed.path in ("/api/query", "/api/continue", "/api/feedback"):
            self._json({"error": "use /api/stream in demo mode"}, status=HTTPStatus.BAD_REQUEST)
            return
        self._json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def _body(self) -> dict[str, Any]:
        n = int(self.headers.get("content-length") or "0")
        raw = self.rfile.read(n) if n > 0 else b"{}"
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _handle_demo_stream(self, payload: dict[str, Any]) -> None:
        query = str(payload.get("query") or "").strip()
        if not query:
            self._json({"error": "query is required"}, status=HTTPStatus.BAD_REQUEST)
            return

        self.send_response(200)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-cache")
        self.send_header("x-accel-buffering", "no")
        self.end_headers()

        def _sse(event: str, data: dict[str, Any]) -> None:
            frame = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
            try:
                self.wfile.write(frame.encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass

        run_id = _run_id()
        scenario = _select_scenario(query, run_id)

        for delay_s, event_type, data in scenario:
            if delay_s > 0:
                time.sleep(delay_s)
            _sse(event_type, data)
            if event_type == "done":
                break

    def _json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_demo(host: str = "127.0.0.1", port: int = 8788) -> None:
    server = ThreadingHTTPServer((host, port), DemoHandler)
    print(f"DataAgent DEMO UI: http://{host}:{port}", flush=True)
    print("Scenarios:", flush=True)
    print("  • Default query     → ВВП России 2022 (с данными, графиком, источниками)", flush=True)
    print("  • 'Китай' / 'сравни'→ Россия vs Китай 2015–2023 (grouped line chart)", flush=True)
    print("  • 'уровень счастья' → No data found (все источники пусты)", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="DataAgent demo server (fake cases).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8788, type=int)
    args = parser.parse_args()
    run_demo(host=args.host, port=args.port)
