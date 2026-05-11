from __future__ import annotations

import re
from dataclasses import dataclass, field


_TOKEN_RE = re.compile(r"[\wА-Яа-яЁё]+", re.UNICODE)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


@dataclass(frozen=True)
class ConceptSpec:
    key: str
    label: str
    aliases: tuple[str, ...]
    indicator_hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class QueryIntent:
    concepts: list[str] = field(default_factory=list)
    geographies: list[str] = field(default_factory=list)
    years: list[int] = field(default_factory=list)
    source_families: list[str] = field(default_factory=list)
    raw_tokens: list[str] = field(default_factory=list)

    @property
    def has_graph_entry(self) -> bool:
        return bool(self.concepts or self.geographies or self.years or self.source_families)


CONCEPTS: tuple[ConceptSpec, ...] = (
    ConceptSpec(
        key="gdp",
        label="GDP",
        aliases=(
            "gdp",
            "gross domestic product",
            "ввп",
            "валовой внутренний продукт",
            "валового внутреннего продукта",
        ),
        indicator_hints=("ny.gdp.mktp.cd", "ny.gdp.mktp.kd", "ny.gdp.pcap.cd"),
    ),
    ConceptSpec(
        key="inflation",
        label="Inflation",
        aliases=(
            "inflation",
            "consumer price index",
            "cpi",
            "инфляция",
            "инфляции",
            "ипц",
            "индекс потребительских цен",
            "рост цен",
        ),
        indicator_hints=("fp.cpi.totl.zg", "fp.cpi.totl"),
    ),
    ConceptSpec(
        key="population",
        label="Population",
        aliases=("population", "население", "численность населения"),
        indicator_hints=("sp.pop.totl",),
    ),
    ConceptSpec(
        key="unemployment",
        label="Unemployment",
        aliases=("unemployment", "безработица", "уровень безработицы"),
        indicator_hints=("sl.uem.totl.zs",),
    ),
    ConceptSpec(
        key="fertility",
        label="Fertility",
        aliases=("fertility", "birth rate", "рождаемость", "коэффициент рождаемости"),
        indicator_hints=("sp.dyn.tfrt.in",),
    ),
    ConceptSpec(
        key="urbanization",
        label="Urbanization",
        aliases=("urbanization", "urban population", "урбанизация", "городское население"),
        indicator_hints=("sp.urb.totl.in.zs",),
    ),
)

_SOURCE_ALIASES: dict[str, tuple[str, ...]] = {
    "fedstat": ("fedstat", "fed stat", "росстат", "емисс", "федстат"),
    "world_bank": ("world bank", "worldbank", "всемирный банк", "wb"),
    "ckan": ("ckan", "нцсэд", "nsed"),
}

_GEO_ALIASES: dict[str, tuple[str, ...]] = {
    "russia": ("russia", "russian federation", "россия", "рф", "российская федерация"),
    "kazakhstan": ("kazakhstan", "казахстан"),
    "north_korea": ("north korea", "dprk", "кндр", "северная корея"),
    "world": ("world", "мир", "мировой"),
}


def parse_query_intent(query: str) -> QueryIntent:
    text = query.casefold()
    tokens = _tokens(text)
    return QueryIntent(
        concepts=_match_concepts(text),
        geographies=_match_alias_map(text, _GEO_ALIASES),
        years=sorted({int(year) for year in _YEAR_RE.findall(text)}),
        source_families=_match_alias_map(text, _SOURCE_ALIASES),
        raw_tokens=tokens,
    )


def concept_keys_for_text(text: str) -> list[str]:
    folded = text.casefold()
    matches = set(_match_concepts(folded))
    normalized = _normalize_identifier(folded)
    for spec in CONCEPTS:
        if any(hint in normalized for hint in spec.indicator_hints):
            matches.add(spec.key)
    return sorted(matches)


def concept_spec(key: str) -> ConceptSpec | None:
    for spec in CONCEPTS:
        if spec.key == key:
            return spec
    return None


def normalize_query_value(value: str) -> str:
    return _normalize_identifier(value)


def _match_concepts(text: str) -> list[str]:
    return [
        spec.key
        for spec in CONCEPTS
        if any(_phrase_in_text(alias.casefold(), text) for alias in spec.aliases)
    ]


def _match_alias_map(text: str, aliases_by_key: dict[str, tuple[str, ...]]) -> list[str]:
    return [
        key
        for key, aliases in aliases_by_key.items()
        if any(_phrase_in_text(alias.casefold(), text) for alias in aliases)
    ]


def _phrase_in_text(phrase: str, text: str) -> bool:
    if " " in phrase:
        return phrase in text
    return phrase in _tokens(text)


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in _TOKEN_RE.findall(text) if token.strip()]


def _normalize_identifier(value: str) -> str:
    value = value.strip().casefold()
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"[/\\._\-\s]+", ".", value)
    value = re.sub(r"[^a-z0-9а-яё.]+", ".", value)
    return re.sub(r"\.+", ".", value).strip(".")
