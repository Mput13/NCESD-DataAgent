from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from app.artifacts.source_cards import (
    AvailabilityFlags,
    CoverageHint,
    MatchMode,
    QualityFlags,
    SourceCandidateCard,
)


FEDSTAT_SOURCE = "fedstat"
WORLD_BANK_SOURCE = "world_bank"
CKAN_SOURCE = "ckan"


def build_fedstat(
    metadata_rows: Iterable[Mapping[str, Any]],
    *,
    local_zip_path: str,
    parquet_paths: set[str],
    clean_jsonl_paths: set[str],
    limit: int | None = None,
) -> list[SourceCandidateCard]:
    """Build FedStat candidate cards from verified metadata rows."""

    cards: list[SourceCandidateCard] = []
    for row in _take(metadata_rows, limit):
        code = _text(row.get("code"))
        if not code:
            continue
        parquet_path = f"fedstatru/data/parquet/{code}.parquet"
        clean_path = f"fedstatru/data/clean_jsonl/{code}.jsonl.gz"
        has_parquet = parquet_path in parquet_paths
        has_clean = clean_path in clean_jsonl_paths
        dimensions = _split_dimensions(
            _text(row.get("Признаки (перечень на базе классификаторов и справочников)"))
        )
        coverage = _coverage_from_range(
            _text(row.get("Длина временного ряда")),
            frequency=_text(row.get("Периодичность и характеристика временного ряда")) or None,
            geography=["Russian Federation"],
        )

        cards.append(
            SourceCandidateCard(
                source=FEDSTAT_SOURCE,
                builder_source="fedstat_metdata_csv",
                dataset_id=code,
                resource_id=parquet_path if has_parquet else None,
                title=_text(row.get("name")) or code,
                match_mode=MatchMode.LEXICAL,
                units=_text(row.get("Единицы измерения")) or None,
                geography=["Russian Federation"],
                period_coverage=coverage,
                provenance_url=_text(row.get("url")) or f"https://fedstat.ru/indicator/{code}",
                provenance_note="FedStat metadata row joined with local archive file presence.",
                local_paths=[local_zip_path],
                availability=AvailabilityFlags(
                    has_local_metadata=True,
                    has_local_data=has_parquet or has_clean,
                    has_live_api=False,
                ),
                quality=QualityFlags(
                    requires_normalization=has_parquet and not has_clean,
                    incomplete_metadata=False,
                    has_clean_jsonl=has_clean,
                    wide_parquet=has_parquet and not has_clean,
                    notes=[
                        "FedStat parquet tables commonly require first-row header normalization."
                    ]
                    if has_parquet and not has_clean
                    else [],
                ),
                dimensions=dimensions,
                frequency=_text(row.get("Периодичность и характеристика временного ряда"))
                or None,
                description=_text(row.get("Методологические пояснения")) or None,
                why_matched="FedStat catalog candidate built from local metadata.",
                metadata={
                    "rows": _text(row.get("rows")) or None,
                    "filesize": _text(row.get("filesize")) or None,
                    "agency": _text(row.get("Ведомство (субъект статистического учета)"))
                    or None,
                    "last_update": _text(row.get("Последнее обновление данных")) or None,
                    "metadata_source": "metdata.csv",
                    "clean_jsonl_path": clean_path if has_clean else None,
                },
            )
        )
    return cards


def build_world_bank(
    indicators: Iterable[Mapping[str, Any]],
    *,
    countries: Iterable[Mapping[str, Any]],
    parquet_paths: set[str],
    limit: int | None = None,
) -> list[SourceCandidateCard]:
    """Build World Bank candidate cards from indicator and country metadata."""

    country_rows = list(countries)
    country_names = [_text(row.get("name")) for row in country_rows if _text(row.get("name"))]
    aggregate_count = sum(1 for row in country_rows if _is_world_bank_aggregate(row))

    cards: list[SourceCandidateCard] = []
    for indicator in _take(indicators, limit):
        indicator_id = _text(indicator.get("id"))
        if not indicator_id:
            continue
        parquet_path = f"wb/parquet/{indicator_id}.parquet"
        has_parquet = parquet_path in parquet_paths
        source = indicator.get("source")
        source_name = source.get("value") if isinstance(source, Mapping) else None
        topics = _topic_values(indicator.get("topics"))

        cards.append(
            SourceCandidateCard(
                source=WORLD_BANK_SOURCE,
                builder_source="world_bank_indicators_json",
                dataset_id=indicator_id,
                resource_id=parquet_path if has_parquet else None,
                title=_text(indicator.get("name")) or indicator_id,
                match_mode=MatchMode.LEXICAL,
                units=_world_bank_units(indicator),
                geography=country_names,
                period_coverage=CoverageHint(
                    geography=country_names,
                    coverage_note="Year coverage is verified from parquet during extraction.",
                ),
                provenance_url=f"https://api.worldbank.org/v2/indicator/{indicator_id}",
                provenance_note="World Bank indicator metadata joined with local parquet presence.",
                local_paths=["/Users/a/Downloads/dumps/wb/data.zip"],
                availability=AvailabilityFlags(
                    has_local_metadata=True,
                    has_local_data=has_parquet,
                    has_live_api=True,
                ),
                quality=QualityFlags(
                    aggregate_geography=aggregate_count > 0,
                    notes=["World Bank unit metadata is often empty; units may be parsed from title."]
                    if not _text(indicator.get("unit"))
                    else [],
                ),
                dimensions=["country", "date", "indicator"],
                frequency="annual",
                description=_text(indicator.get("sourceNote")) or None,
                why_matched="World Bank catalog candidate built from indicator metadata.",
                metadata={
                    "source": source_name,
                    "source_organization": _text(indicator.get("sourceOrganization"))
                    or None,
                    "topics": topics,
                    "country_count": len(country_names),
                    "aggregate_count": aggregate_count,
                    "metadata_source": "indicators.json",
                },
            )
        )
    return cards


def build_ckan(
    packages: Iterable[Mapping[str, Any]],
    *,
    query: str,
    api_endpoint: str,
    inspected_resource_limit: int,
    limit: int | None = None,
) -> list[SourceCandidateCard]:
    """Build CKAN source cards from bounded package_search or package_show payloads."""

    cards: list[SourceCandidateCard] = []
    for package in _take(packages, limit):
        package_name = _text(package.get("name")) or _text(package.get("id"))
        if not package_name:
            continue
        resources = list(package.get("resources") or [])
        resource_total = len(resources)
        inspected_resources = resources[: max(inspected_resource_limit, 0)]
        inspection_skipped = inspected_resource_limit <= 0
        inspection_truncated = resource_total > len(inspected_resources)
        resource_identity = None
        if inspected_resources:
            first = inspected_resources[0]
            if isinstance(first, Mapping):
                resource_identity = _text(first.get("id")) or _text(first.get("name"))

        cards.append(
            SourceCandidateCard(
                source=CKAN_SOURCE,
                builder_source="ckan_package_search",
                dataset_id=package_name,
                resource_id=resource_identity,
                title=_text(package.get("title")) or package_name,
                match_mode=MatchMode.CKAN_DISCOVERY,
                units=None,
                geography=[],
                period_coverage=CoverageHint(
                    coverage_note="CKAN package metadata does not guarantee data coverage."
                ),
                provenance_url=_text(package.get("url")) or None,
                provenance_note="NSED CKAN package metadata from bounded API call.",
                api_endpoint=api_endpoint,
                availability=AvailabilityFlags(
                    has_local_metadata=False,
                    has_local_data=False,
                    has_live_api=True,
                    api_checked=True,
                    resource_inspection_skipped=inspection_skipped,
                    resource_inspection_truncated=inspection_truncated,
                ),
                quality=QualityFlags(
                    incomplete_metadata=not bool(resources),
                    notes=["Resource inspection skipped by configured bound."]
                    if inspection_skipped
                    else [],
                ),
                dimensions=[],
                description=_text(package.get("notes")) or None,
                why_matched=f"CKAN package_search discovery for query: {query}",
                metadata={
                    "organization": _organization_title(package.get("organization")),
                    "license": _text(package.get("license_title"))
                    or _text(package.get("license_id"))
                    or None,
                    "metadata_modified": _text(package.get("metadata_modified")) or None,
                    "resources_total": resource_total,
                    "resources_inspected": len(inspected_resources),
                    "resources": [_resource_summary(resource) for resource in inspected_resources],
                    "query": query,
                },
            )
        )
    return cards


def _take(
    rows: Iterable[Mapping[str, Any]], limit: int | None
) -> Iterable[Mapping[str, Any]]:
    if limit is None:
        yield from rows
        return
    for index, row in enumerate(rows):
        if index >= limit:
            break
        yield row


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _coverage_from_range(
    raw_range: str, *, frequency: str | None, geography: list[str]
) -> CoverageHint:
    years = re.findall(r"\b(?:19|20)\d{2}\b", raw_range)
    return CoverageHint(
        start_period=years[0] if years else None,
        end_period=years[-1] if years else None,
        frequency=frequency,
        geography=geography,
        coverage_note=raw_range or None,
    )


def _split_dimensions(raw: str) -> list[str]:
    if not raw:
        return []
    parts = re.split(r";|\n|,", raw)
    return [part.strip() for part in parts if part.strip()]


def _world_bank_units(indicator: Mapping[str, Any]) -> str | None:
    explicit_unit = _text(indicator.get("unit"))
    if explicit_unit:
        return explicit_unit
    name = _text(indicator.get("name"))
    match = re.search(r"\(([^)]+)\)", name)
    if match:
        return match.group(1).strip()
    if "%" in name:
        return "%"
    return None


def _topic_values(raw_topics: Any) -> list[str]:
    if not isinstance(raw_topics, list):
        return []
    values: list[str] = []
    for topic in raw_topics:
        if isinstance(topic, Mapping):
            value = _text(topic.get("value"))
            if value:
                values.append(value)
    return values


def _is_world_bank_aggregate(country: Mapping[str, Any]) -> bool:
    region = country.get("region")
    if isinstance(region, Mapping) and _text(region.get("value")).lower() == "aggregates":
        return True
    return _text(country.get("id")) in {"WLD", "EUU", "EMU", "HIC", "LIC", "LMC", "LMY", "MIC", "UMC"}


def _organization_title(raw_org: Any) -> str | None:
    if isinstance(raw_org, Mapping):
        return _text(raw_org.get("title")) or _text(raw_org.get("name")) or None
    return _text(raw_org) or None


def _resource_summary(resource: Any) -> dict[str, str | None]:
    if not isinstance(resource, Mapping):
        return {"id": None, "name": _text(resource) or None, "format": None, "url": None}
    return {
        "id": _text(resource.get("id")) or None,
        "name": _text(resource.get("name")) or None,
        "format": _text(resource.get("format")) or None,
        "url": _text(resource.get("url")) or None,
    }
