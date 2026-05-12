from __future__ import annotations

import re

from app.contracts import IntentFrame, QueryKind


_COMPARISON_WORDS = ("compare", "сравни", "сравнить", "against", "между")
_RESEARCH_WORDS = ("исслед", "оцен", "связ", "влия", "hypothesis", "research")
_DERIVED_WORDS = ("индекс", "реальн", "поправк", "per capita", "на душу", "отношени")
_AMBIGUOUS_WORDS = ("инфляци", "ввп", "безработиц", "доход")


def build_intent(query: str) -> IntentFrame:
    clean = " ".join(query.split())
    lower = clean.lower()
    missing: list[str] = []
    questions: list[str] = []

    if not _has_period(clean):
        missing.append("period")
        questions.append("За какой период нужны данные?")
    if not _has_geography(clean):
        missing.append("geography")
        questions.append("Для какой страны, региона или группы стран нужны данные?")

    query_kind = _query_kind(lower, missing)
    return IntentFrame(
        original_query=clean,
        query_kind=query_kind,
        geography=_rough_geography(clean),
        indicators=_rough_indicators(lower),
        period=_rough_period(clean),
        missing_fields=missing,
        clarification_questions=questions,
    )


def _query_kind(lower: str, missing: list[str]) -> QueryKind:
    if missing and any(word in lower for word in _AMBIGUOUS_WORDS):
        return QueryKind.AMBIGUOUS
    if any(word in lower for word in _DERIVED_WORDS):
        return QueryKind.DERIVED_METRIC
    if any(word in lower for word in _RESEARCH_WORDS):
        return QueryKind.RESEARCH
    if any(word in lower for word in _COMPARISON_WORDS):
        return QueryKind.COMPARISON
    return QueryKind.DIRECT_LOOKUP


def _has_period(query: str) -> bool:
    return bool(re.search(r"\b(19|20)\d{2}\b", query))


def _has_geography(query: str) -> bool:
    return bool(re.search(r"\b[A-ZА-ЯЁ][a-zа-яё]+(?:ская|стан|ия|land|stan|sia)?\b", query))


def _rough_period(query: str) -> str | None:
    years = re.findall(r"\b(?:19|20)\d{2}\b", query)
    if not years:
        return None
    return "-".join([years[0], years[-1]]) if len(years) > 1 else years[0]


def _rough_geography(query: str) -> list[str]:
    blocked = {"Покажи", "Дай", "Найди", "Сравни", "Что", "Как", "Какая", "Какой"}
    found = re.findall(r"\b[A-ZА-ЯЁ][a-zа-яё]+(?:ская|стан|ия|land|stan|sia)?\b", query)
    return [item for item in found if item not in blocked]


def _rough_indicators(lower: str) -> list[str]:
    indicators: list[str] = []
    for token in ("ввп", "gdp", "инфляц", "inflation", "безработиц", "unemployment", "доход", "income"):
        if token in lower:
            indicators.append(token)
    return indicators

