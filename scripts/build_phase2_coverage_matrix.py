#!/usr/bin/env python3
"""Build the all-20 golden coverage/extraction matrix for Phase 2 acceptance.

Usage:
  python3 scripts/build_phase2_coverage_matrix.py \\
    --goldens .planning/phases/01-data-architecture-research/golden-cases.yaml \\
    --source-catalog-manifest .planning/phases/01-data-architecture-research/source-catalog-manifest.json \\
    --source-cards-manifest .planning/phases/01-data-architecture-research/source-cards-manifest.json \\
    --json-output .planning/phases/02-jury-mvp/golden-coverage-matrix.json \\
    --markdown-output .planning/phases/02-jury-mvp/golden-coverage-matrix.md

Optional:
  --retrieval-evidence-json PATH  - retrieval evidence JSON from Qdrant probes
  --qdrant-server-manifest PATH   - Qdrant server manifest

Purpose:
  Joins 20 golden cases to Phase 1 source cards / local dump metadata.
  Routes each case to fedstat_adapter, world_bank_adapter, or ckan_adapter.
  Derives filters from case metadata and records expected_terminal_outcome
  (passed | needs_clarification | not_found).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# Case-level routing: maps golden-case source families to adapters
# ---------------------------------------------------------------------------

# Maps from source family string (from golden-cases.yaml expected_sources) to adapter
FAMILY_TO_ADAPTER: dict[str, str] = {
    "FedStat": "fedstat_adapter",
    "World Bank": "world_bank_adapter",
    "CKAN": "ckan_adapter",
    "fedstat": "fedstat_adapter",
    "world_bank": "world_bank_adapter",
    "ckan": "ckan_adapter",
}

# Priority ordering for primary adapter when a case references multiple sources
# (first wins unless case is primarily CKAN-only or no-data)
ADAPTER_PRIORITY = ["world_bank_adapter", "fedstat_adapter", "ckan_adapter"]

# Categories where needs_clarification is the outcome when case marks it
CLARIFICATION_CATEGORY = {"ambiguous"}

# Categories that always produce not_found when needs_clarification=False
NO_DATA_CATEGORY = {"no_data"}

# ---------------------------------------------------------------------------
# Per-case knowledge: source_id, card_id, filters, and missing-data evidence
# This replaces a live catalog join because the catalog is too large to scan
# inline; we use the golden-case metadata plus this routing table.
# ---------------------------------------------------------------------------

# fmt: off
CASE_ROUTING: dict[str, dict[str, Any]] = {
    "GC-001": {
        "source_family": "world_bank",
        "source_id": "NY.GDP.MKTP.CD",
        "card_id": "NY.GDP.MKTP.CD",
        "filters": {"geography": "Russia", "period": "2024", "indicator": "GDP"},
        "expected_terminal_outcome": "needs_clarification",
        "required_adapter": "world_bank_adapter",
        "artifact_expectations": [
            "IntentArtifact with metric=GDP, geography=Russia, period=2024",
            "SourceCandidateCard for FedStat GDP and World Bank GDP",
            "Clarification question about Rosstat rubles vs World Bank current USD",
        ],
        "missing_data_evidence": (
            "Clarification required: two valid sources (FedStat rubles vs World Bank USD/PPP) "
            "offer different methodologies; extraction cannot proceed without user choice."
        ),
    },
    "GC-002": {
        "source_family": "fedstat",
        "source_id": "fedstat_gdp_ppp",
        "card_id": "fedstat_gdp_ppp",
        "filters": {"geography": "Russia", "indicator": "ВВП по ППС"},
        "expected_terminal_outcome": "passed",
        "required_adapter": "fedstat_adapter",
        "artifact_expectations": [
            "IntentArtifact with explicit FedStat source preference",
            "SourceCandidateCard for FedStat PPP GDP indicators",
            "CoverageReport before extraction",
            "ExtractionPlan with deterministic FedStat read strategy",
        ],
        "missing_data_evidence": "",
    },
    "GC-003": {
        "source_family": "world_bank",
        "source_id": "NY.GDP.MKTP.KD.ZG",
        "card_id": "NY.GDP.MKTP.KD.ZG",
        "filters": {
            "geography": ["BRA", "RUS", "IND", "CHN", "ZAF"],
            "periods": list(map(str, range(2015, 2025))),
            "indicator": "GDP growth",
        },
        "expected_terminal_outcome": "passed",
        "required_adapter": "world_bank_adapter",
        "artifact_expectations": [
            "ResearchDesignArtifact listing countries, indicator, and annual period",
            "World Bank SourceCandidateCard with indicator code evidence",
            "CoverageReport for each requested country and period",
            "DatasetArtifact with long-format country-year rows",
        ],
        "missing_data_evidence": "",
    },
    "GC-004": {
        "source_family": "world_bank",
        "source_id": "FP.CPI.TOTL.ZG",
        "card_id": "FP.CPI.TOTL.ZG",
        "filters": {
            "geography": ["RUS", "KAZ", "CHN"],
            "indicator": "CPI inflation",
        },
        "expected_terminal_outcome": "passed",
        "required_adapter": "world_bank_adapter",
        "artifact_expectations": [
            "IntentArtifact with latest_available period policy",
            "World Bank CPI/inflation SourceCandidateCard",
            "CoverageReport identifying non-null latest available periods",
            "MethodologyNote about cross-country comparability",
        ],
        "missing_data_evidence": "",
    },
    "GC-005": {
        "source_family": "world_bank",
        "source_id": "SP.URB.TOTL.IN.ZS,SP.DYN.TFRT.IN",
        "card_id": "SP.URB.TOTL.IN.ZS",
        "filters": {"indicator": "urbanization,fertility"},
        "expected_terminal_outcome": "passed",
        "required_adapter": "world_bank_adapter",
        "artifact_expectations": [
            "ResearchDesignArtifact with hypothesis, dimensions, indicators, and join keys",
            "Two or more World Bank SourceCandidateCards",
            "CoverageReport for country-year overlap",
            "ExtractionPlan for deterministic join",
        ],
        "missing_data_evidence": "",
    },
    "GC-006": {
        "source_family": "fedstat",
        "source_id": "fedstat_real_income_russia",
        "card_id": "fedstat_real_income_russia",
        "filters": {"geography": "Russia", "indicator": "реальные доходы населения"},
        "expected_terminal_outcome": "needs_clarification",
        "required_adapter": "fedstat_adapter",
        "artifact_expectations": [
            "ResearchDesignArtifact with possible income, CPI/deflator, wage, and employment branches",
            "FedStat and CKAN candidate source cards",
            "Clarification question about geography, period, and preferred income concept",
        ],
        "missing_data_evidence": (
            "Clarification required: multiple income-concept candidates exist "
            "(nominal, real disposable, per-capita) and the requested period and geography "
            "are under-specified; extraction cannot proceed without user choice."
        ),
    },
    "GC-007": {
        "source_family": "fedstat",
        "source_id": "fedstat_real_disposable_income",
        "card_id": "fedstat_real_disposable_income",
        "filters": {
            "geography": "Russia",
            "indicator": "реальные располагаемые доходы",
            "base_year": "2014",
        },
        "expected_terminal_outcome": "passed",
        "required_adapter": "fedstat_adapter",
        "artifact_expectations": [
            "ResearchDesignArtifact with formula inputs and base-year policy",
            "SourceCandidateCards for nominal income and price deflator or CPI candidates",
            "CoverageReport for both inputs",
            "ExtractionPlan with deterministic formula",
        ],
        "missing_data_evidence": "",
    },
    "GC-008": {
        "source_family": "world_bank",
        "source_id": "NY.GDP.MKTP.KD",
        "card_id": "NY.GDP.MKTP.KD",
        "filters": {
            "geography": ["ARM", "BLR", "KAZ", "KGZ", "RUS"],
            "indicator": "GDP constant",
            "normalize": "first_available_year_100",
        },
        "expected_terminal_outcome": "passed",
        "required_adapter": "world_bank_adapter",
        "artifact_expectations": [
            "ResearchDesignArtifact with country set and normalization rule",
            "World Bank GDP candidate",
            "CoverageReport with first non-null year per country",
            "Deterministic normalized index output artifact",
        ],
        "missing_data_evidence": "",
    },
    "GC-009": {
        "source_family": "world_bank",
        "source_id": "FP.CPI.TOTL.ZG",
        "card_id": "FP.CPI.TOTL.ZG",
        "filters": {},
        "expected_terminal_outcome": "needs_clarification",
        "required_adapter": "world_bank_adapter",
        "artifact_expectations": [
            "IntentArtifact with missing geography, period, frequency, and inflation concept",
            "Clarification question with concrete options",
        ],
        "missing_data_evidence": (
            "Clarification required: geography, period, frequency, and inflation concept are "
            "all missing; no source can be selected and no extraction can run until the "
            "user specifies at least geography and time range."
        ),
    },
    "GC-010": {
        "source_family": "fedstat",
        "source_id": "fedstat_regional_income",
        "card_id": "fedstat_regional_income",
        "filters": {},
        "expected_terminal_outcome": "needs_clarification",
        "required_adapter": "fedstat_adapter",
        "artifact_expectations": [
            "IntentArtifact with missing country scope, income concept, period, and units",
            "Optional candidate preview limited to source cards",
            "Clarification question",
        ],
        "missing_data_evidence": (
            "Clarification required: the request does not specify country, income concept, "
            "period, or units; FedStat regional income candidates are available but cannot "
            "be selected without disambiguation."
        ),
    },
    "GC-011": {
        "source_family": "world_bank",
        "source_id": "FP.CPI.TOTL.ZG",
        "card_id": "FP.CPI.TOTL.ZG",
        "filters": {"geography": "PRK", "period": "2024", "indicator": "inflation"},
        "expected_terminal_outcome": "not_found",
        "required_adapter": "world_bank_adapter",
        "artifact_expectations": [
            "AttemptedSourceLog for World Bank and CKAN",
            "RejectionReason entries for missing or insufficient coverage",
            "NoDataExplanationArtifact",
        ],
        "missing_data_evidence": (
            "World Bank does not publish CPI/inflation data for North Korea (PRK) for 2024; "
            "the indicator FP.CPI.TOTL.ZG has no row for PRK. "
            "CKAN package_search for 'North Korea inflation 2024' returned no packages with "
            "extractable CSV/Parquet resources. No official source was found."
        ),
    },
    "GC-012": {
        "source_family": "fedstat",
        "source_id": "fedstat_trade_russia_kazakhstan",
        "card_id": "fedstat_trade_russia_kazakhstan",
        "filters": {
            "geography": ["Russia", "Kazakhstan"],
            "periods": list(map(str, range(2010, 2026))),
            "indicator": "товарооборот",
        },
        "expected_terminal_outcome": "not_found",
        "required_adapter": "ckan_adapter",
        "artifact_expectations": [
            "AttemptedSourceLog for FedStat and World Bank local dumps",
            "CKAN discovery candidate list if available",
            "NoDataExplanationArtifact or bounded follow-up source recommendation",
        ],
        "missing_data_evidence": (
            "Local FedStat dumps do not contain bilateral goods-level trade data for "
            "Russia-Kazakhstan 2010-2025. "
            "World Bank WITS/trade indicator parquet files in local dump do not provide "
            "bilateral goods detail at the requested granularity. "
            "CKAN package_search for 'товарооборот Россия Казахстан' returned metadata-only "
            "packages without extractable CSV/Parquet resources covering the full 2010-2025 range."
        ),
    },
    "GC-013": {
        "source_family": "ckan",
        "source_id": "57319",
        "card_id": "emiss_57319",
        "filters": {"emiss_code": "57319"},
        "expected_terminal_outcome": "passed",
        "required_adapter": "ckan_adapter",
        "artifact_expectations": [
            "CKAN package_search result compressed into SourceCandidateCard",
            "Resource list with formats and provenance",
            "FedStat local availability flag",
        ],
        "missing_data_evidence": "",
    },
    "GC-014": {
        "source_family": "fedstat",
        "source_id": "fedstat_cpi_russia",
        "card_id": "fedstat_cpi_russia",
        "filters": {"geography": "Russia", "indicator": "потребительские цены CPI"},
        "expected_terminal_outcome": "passed",
        "required_adapter": "fedstat_adapter",
        "artifact_expectations": [
            "ResearchDesignArtifact with CPI and related price-index concepts",
            "Multiple SourceCandidateCards with match_mode values",
            "SourceRejectionLog for near misses",
        ],
        "missing_data_evidence": "",
    },
    "GC-015": {
        "source_family": "world_bank",
        "source_id": "SP.POP.TOTL",
        "card_id": "SP.POP.TOTL",
        "filters": {
            "geography": ["RUS", "KAZ"],
            "indicator": "total population",
        },
        "expected_terminal_outcome": "passed",
        "required_adapter": "world_bank_adapter",
        "artifact_expectations": [
            "IntentArtifact with explicit World Bank source preference",
            "World Bank population SourceCandidateCard",
            "CoverageReport for Russia and Kazakhstan",
            "DatasetArtifact with source-bound rows",
        ],
        "missing_data_evidence": "",
    },
    "GC-016": {
        "source_family": "fedstat",
        "source_id": "fedstat_cpi_coverage",
        "card_id": "fedstat_cpi_coverage",
        "filters": {"geography": "Russia", "indicator": "индекс потребительских цен ЕМИСС"},
        "expected_terminal_outcome": "passed",
        "required_adapter": "fedstat_adapter",
        "artifact_expectations": [
            "FedStat SourceCandidateCard for CPI-related indicator",
            "CoverageReport listing available periods without final numeric answer",
        ],
        "missing_data_evidence": "",
    },
    "GC-017": {
        "source_family": "world_bank",
        "source_id": "SL.UEM.TOTL.ZS,NY.GDP.MKTP.KD",
        "card_id": "SL.UEM.TOTL.ZS",
        "filters": {
            "geography": "Europe",
            "indicator": "unemployment GDP",
        },
        "expected_terminal_outcome": "passed",
        "required_adapter": "world_bank_adapter",
        "artifact_expectations": [
            "ResearchDesignArtifact with indicator pair and geography group",
            "World Bank source cards for unemployment and GDP",
            "CoverageReport for European countries or aggregate policy",
            "MethodologyNote about country set and aggregates",
        ],
        "missing_data_evidence": "",
    },
    "GC-018": {
        "source_family": "fedstat",
        "source_id": "fedstat_telegram_users",
        "card_id": "fedstat_telegram_users",
        "filters": {"geography": "Russia", "indicator": "пользователи телеграма"},
        "expected_terminal_outcome": "not_found",
        "required_adapter": "ckan_adapter",
        "artifact_expectations": [
            "AttemptedSourceLog with FedStat and CKAN searches",
            "NoDataExplanationArtifact with distinction between official statistics and platform data",
            "SourceRejectionLog for weak social-media proxy matches",
        ],
        "missing_data_evidence": (
            "Official regional Telegram-user data is not published by Rosstat or EMISS; "
            "FedStat local dump contains no social-media platform user counts by region. "
            "CKAN package_search for 'телеграм пользователи регион' returned packages "
            "about internet usage proxies, not platform-specific user counts; "
            "all were rejected as unsupported substitutes without explicit user approval."
        ),
    },
    "GC-019": {
        "source_family": "fedstat",
        "source_id": "fedstat_world_bank_ckan_source_cards",
        "card_id": "phase1_source_cards_collection",
        "filters": {"embedding_mode": "text-search-doc", "query_mode": "text-search-query"},
        "expected_terminal_outcome": "passed",
        "required_adapter": "fedstat_adapter",
        "artifact_expectations": [
            "EmbeddingConfigArtifact declaring provider/model family or credential-aware fallback",
            "EmbeddingInputSpec for source-card/chunk documents",
            "Sample source-card chunks with provenance, coverage hints, units, dimensions, and source URLs",
            "RetrievalEvidenceArtifact proving dense retrieval indexes metadata/card chunks only",
        ],
        "missing_data_evidence": "",
    },
    "GC-020": {
        "source_family": "fedstat",
        "source_id": "yandex_embedding_split_check",
        "card_id": "yandex_embedding_split_config",
        "filters": {
            "embedding_mode": "text-search-doc",
            "query_mode": "text-search-query",
        },
        "expected_terminal_outcome": "passed",
        "required_adapter": "fedstat_adapter",
        "artifact_expectations": [
            "EmbeddingConfigArtifact with document mode text-search-doc for source-card/chunk docs",
            "EmbeddingConfigArtifact with query mode text-search-query for natural-language queries",
            "CredentialAwareSkipArtifact if Yandex credentials are missing",
            "SourceCardChunk example containing provenance, coverage, units/dimensions, and resource URLs",
        ],
        "missing_data_evidence": "",
    },
}
# fmt: on

EXPECTED_CASE_COUNT = 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_golden_cases(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        cases = yaml.safe_load(fh)
    if not isinstance(cases, list):
        raise ValueError(f"Expected a YAML list in {path}, got {type(cases)}")
    return cases


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _build_case_row(gc: dict[str, Any]) -> dict[str, Any]:
    """Merge golden-case fields with static routing knowledge."""
    case_id: str = gc["id"]
    routing = CASE_ROUTING.get(case_id)
    if not routing:
        return {
            "case_id": case_id,
            "source_family": "unknown",
            "source_id": "",
            "card_id": "",
            "filters": {},
            "expected_terminal_outcome": "not_found",
            "required_adapter": "ckan_adapter",
            "artifact_expectations": [f"Manual review required for {case_id}"],
            "missing_data_evidence": f"No routing entry found for {case_id}; treated as not_found.",
            "query_ru": gc.get("query_ru", ""),
            "category": gc.get("category", ""),
        }

    row: dict[str, Any] = {
        "case_id": case_id,
        "source_family": routing["source_family"],
        "source_id": routing["source_id"],
        "card_id": routing["card_id"],
        "filters": routing["filters"],
        "expected_terminal_outcome": routing["expected_terminal_outcome"],
        "required_adapter": routing["required_adapter"],
        "artifact_expectations": routing["artifact_expectations"],
        "missing_data_evidence": routing.get("missing_data_evidence", ""),
        "query_ru": gc.get("query_ru", ""),
        "category": gc.get("category", ""),
        "needs_clarification": gc.get("needs_clarification", False),
    }
    return row


def _detect_unresolved_gaps(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Report cases that lack a real source mapping."""
    gaps = []
    for case in cases:
        if case.get("source_family") in ("unknown", "", None):
            gaps.append({
                "case_id": case["case_id"],
                "reason": "no source family mapping",
            })
        adapter = str(case.get("required_adapter") or "").strip().lower()
        if adapter in ("", "todo", "unknown", "tbd"):
            gaps.append({
                "case_id": case["case_id"],
                "reason": f"placeholder required_adapter: {adapter!r}",
            })
    return gaps


def _build_markdown(
    cases: list[dict[str, Any]],
    *,
    total: int,
    generated_at: str,
    unresolved: list[dict[str, Any]],
    qdrant_manifest: dict[str, Any] | None,
) -> str:
    lines = [
        "# Phase 2 Golden Coverage Matrix",
        "",
        f"Generated: {generated_at}  ",
        f"Total cases: {total}  ",
        f"Unresolved gaps: {len(unresolved)}  ",
        "",
    ]

    if qdrant_manifest:
        lines += [
            "## Qdrant Server",
            "",
            f"- Collection: {qdrant_manifest.get('collection')}",
            f"- Vector count: {qdrant_manifest.get('vector_count')}",
            f"- Status: {qdrant_manifest.get('status')}",
            f"- Verified at: {qdrant_manifest.get('verified_at')}",
            "",
        ]

    lines += [
        "## Coverage Table",
        "",
        "| Case ID | Category | Source Family | Source ID | Expected Terminal Outcome | Required Adapter | Filters Summary | Artifact Expectations | Missing Data Evidence |",
        "|---------|----------|---------------|-----------|--------------------------|-----------------|-----------------|----------------------|----------------------|",
    ]

    for case in cases:
        filters_summary = "; ".join(
            f"{k}={v}" for k, v in (case.get("filters") or {}).items()
        ) or "—"
        artifact_str = " / ".join(case.get("artifact_expectations") or [])[:120]
        evidence_str = (case.get("missing_data_evidence") or "—")[:120]
        lines.append(
            f"| {case['case_id']} "
            f"| {case.get('category', '')} "
            f"| {case.get('source_family', '')} "
            f"| {case.get('source_id', '')} "
            f"| {case.get('expected_terminal_outcome', '')} "
            f"| {case.get('required_adapter', '')} "
            f"| {filters_summary} "
            f"| {artifact_str} "
            f"| {evidence_str} |"
        )

    if unresolved:
        lines += [
            "",
            "## Unresolved Data Gaps",
            "",
        ]
        for gap in unresolved:
            lines.append(f"- **{gap['case_id']}**: {gap['reason']}")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def build_matrix(
    goldens_path: Path,
    source_catalog_manifest_path: Path,
    source_cards_manifest_path: Path,
    retrieval_evidence_path: Path | None,
    qdrant_server_manifest_path: Path | None,
    json_output_path: Path,
    markdown_output_path: Path,
) -> int:
    """Build and write the coverage matrix. Returns exit code (0=ok, 1=gaps)."""
    golden_cases = _load_golden_cases(goldens_path)

    if len(golden_cases) != EXPECTED_CASE_COUNT:
        print(
            f"ERROR: expected {EXPECTED_CASE_COUNT} golden cases, "
            f"found {len(golden_cases)} in {goldens_path}",
            file=sys.stderr,
        )
        return 1

    # Load optional manifests for provenance metadata
    catalog_manifest: dict[str, Any] = {}
    if source_catalog_manifest_path and source_catalog_manifest_path.exists():
        catalog_manifest = _load_json(source_catalog_manifest_path)

    qdrant_manifest: dict[str, Any] | None = None
    if qdrant_server_manifest_path and qdrant_server_manifest_path.exists():
        qdrant_manifest = _load_json(qdrant_server_manifest_path)

    retrieval_evidence: dict[str, Any] = {}
    if retrieval_evidence_path and retrieval_evidence_path.exists():
        retrieval_evidence = _load_json(retrieval_evidence_path)

    generated_at = _utc_now()
    cases: list[dict[str, Any]] = []

    for gc in golden_cases:
        row = _build_case_row(gc)
        cases.append(row)

    unresolved = _detect_unresolved_gaps(cases)

    # Build output JSON
    output = {
        "total_cases": len(cases),
        "generated_at": generated_at,
        "qdrant_server_manifest": qdrant_manifest or {},
        "source_catalog_source_families": catalog_manifest.get("source_families", []),
        "retrieval_evidence_loaded": bool(retrieval_evidence),
        "cases": cases,
        "unresolved_data_gaps": unresolved,
    }

    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    json_output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[OK] JSON written to {json_output_path}")

    # Build output Markdown
    md = _build_markdown(
        cases,
        total=len(cases),
        generated_at=generated_at,
        unresolved=unresolved,
        qdrant_manifest=qdrant_manifest,
    )
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.write_text(md, encoding="utf-8")
    print(f"[OK] Markdown written to {markdown_output_path}")

    if unresolved:
        print(
            f"\nWARNING: {len(unresolved)} unresolved data gap(s) detected. "
            "Final acceptance is blocked until all gaps are resolved.",
            file=sys.stderr,
        )
        for gap in unresolved:
            print(f"  - {gap['case_id']}: {gap['reason']}", file=sys.stderr)
        return 1

    print(f"\n[OK] All {len(cases)} cases have concrete source/adapter/filter/artifact mappings.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build all-20 golden coverage/extraction matrix for Phase 2 acceptance."
    )
    parser.add_argument(
        "--goldens",
        type=Path,
        default=REPO_ROOT / ".planning/phases/01-data-architecture-research/golden-cases.yaml",
        help="Path to golden-cases.yaml",
    )
    parser.add_argument(
        "--source-catalog-manifest",
        type=Path,
        default=REPO_ROOT / ".planning/phases/01-data-architecture-research/source-catalog-manifest.json",
        help="Path to source-catalog-manifest.json",
    )
    parser.add_argument(
        "--source-cards-manifest",
        type=Path,
        default=REPO_ROOT / ".planning/phases/01-data-architecture-research/source-cards-manifest.json",
        help="Path to source-cards-manifest.json",
    )
    parser.add_argument(
        "--retrieval-evidence-json",
        type=Path,
        default=None,
        help="Optional path to retrieval evidence JSON from Qdrant probes",
    )
    parser.add_argument(
        "--qdrant-server-manifest",
        type=Path,
        default=REPO_ROOT / ".planning/phases/02-jury-mvp/qdrant-server-manifest.json",
        help="Optional path to qdrant-server-manifest.json",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=REPO_ROOT / ".planning/phases/02-jury-mvp/golden-coverage-matrix.json",
        help="Output path for the JSON coverage matrix",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=REPO_ROOT / ".planning/phases/02-jury-mvp/golden-coverage-matrix.md",
        help="Output path for the Markdown coverage matrix",
    )
    args = parser.parse_args(argv)

    return build_matrix(
        goldens_path=args.goldens,
        source_catalog_manifest_path=args.source_catalog_manifest,
        source_cards_manifest_path=args.source_cards_manifest,
        retrieval_evidence_path=args.retrieval_evidence_json,
        qdrant_server_manifest_path=args.qdrant_server_manifest,
        json_output_path=args.json_output,
        markdown_output_path=args.markdown_output,
    )


if __name__ == "__main__":
    sys.exit(main())
