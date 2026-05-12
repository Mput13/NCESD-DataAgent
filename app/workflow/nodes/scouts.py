"""Source scout node for Phase 2 workflow.

run_source_scouts uses HybridRetriever for lexical/dense search across FedStat
and World Bank, and adds bounded CKAN discovery when relevant.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.artifacts.workflow_artifacts import EvidenceBundleArtifact
from app.retrieval.hybrid_retrieval import HybridRetriever

# Patterns that trigger CKAN scout regardless of expected_sources
_CKAN_TRIGGER_PATTERNS = [
    re.compile(r"\b\d{5}\b"),          # 5-digit ЕМИСС-style indicator codes like 57319
    re.compile(r"ЕМИСС", re.IGNORECASE),
    re.compile(r"НЦСЭД", re.IGNORECASE),
    re.compile(r"\bCKAN\b", re.IGNORECASE),
    re.compile(r"nsedc", re.IGNORECASE),
]


def run_source_scouts(
    query: str,
    *,
    expected_sources: list[str],
    index_manifest_path: Path,
    research_design=None,  # ResearchDesignArtifact | None
) -> EvidenceBundleArtifact:
    """Run source scouts and return an EvidenceBundleArtifact.

    Uses HybridRetriever for FedStat and World Bank catalog search.
    Triggers bounded CKAN discovery when expected_sources includes 'ckan'
    or when the query contains ЕМИСС/НЦСЭД/CKAN keywords or a 5-digit code.
    """
    retriever = HybridRetriever(index_manifest_path)
    result = retriever.search(query, expected_sources=expected_sources, limit=5)

    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for candidate in result.candidates:
        selected.append({
            "source_family": candidate.source_family,
            "card_id": candidate.card_id,
            "chunk_id": candidate.chunk_id,
            "title": candidate.title,
            "score": candidate.score,
            "relevance_score": candidate.relevance_score,
            "retrieval_mode": candidate.retrieval_mode,
            "evidence_keywords": candidate.evidence_keywords,
            "match_mode": candidate.metadata.get("match_mode"),
            "provenance_url": candidate.metadata.get("provenance_url"),
            "why_matched": f"lexical/dense retrieval score={candidate.score:.4f}",
            "risk_flags": [],
        })

    for candidate in result.rejected_candidates:
        rejected.append({
            "source_family": candidate.source_family,
            "card_id": candidate.card_id,
            "title": candidate.title,
            "score": candidate.score,
            "retrieval_mode": candidate.retrieval_mode,
            "rejection_reasons": candidate.rejection_reasons,
        })

    # CKAN discovery: trigger if expected or query matches patterns
    if _should_run_ckan(query, expected_sources):
        ckan_cards = _run_ckan_scout(query)
        for card in ckan_cards:
            # Check if already in selected/rejected by dataset_id
            existing_ids = {s.get("card_id", s.get("dataset_id")) for s in selected + rejected}
            did = card.get("dataset_id", "")
            if did and did not in existing_ids:
                selected.append({
                    "source_family": "ckan",
                    "card_id": did,
                    "chunk_id": did,
                    "title": card.get("title", ""),
                    "dataset_id": did,
                    "formats": card.get("formats", []),
                    "resource_count": card.get("resource_count", 0),
                    "provenance_url": card.get("provenance_url", ""),
                    "why_matched": "ckan_bounded_package_search",
                    "risk_flags": card.get("risk_flags", []),
                    "score": 0.5,
                    "relevance_score": 0.5,
                    "retrieval_mode": "ckan_package_search",
                    "evidence_keywords": [],
                    "match_mode": "ckan_catalog",
                })

    # Expanded indicator search
    if research_design is not None:
        expanded = getattr(research_design, "expanded_indicators", []) or []
        for item in expanded:
            for search_q in [item.get("search_query_ru", ""), item.get("search_query_en", "")]:
                if not search_q:
                    continue
                exp_result = retriever.search(search_q, expected_sources=expected_sources, limit=3)
                for candidate in exp_result.candidates:
                    # Skip if already selected (by card_id)
                    if any(s.get("card_id") == candidate.card_id for s in selected):
                        continue
                    selected.append({
                        "source_family": candidate.source_family,
                        "card_id": candidate.card_id,
                        "chunk_id": candidate.chunk_id,
                        "title": candidate.title,
                        "score": candidate.score,
                        "relevance_score": candidate.relevance_score,
                        "retrieval_mode": candidate.retrieval_mode,
                        "evidence_keywords": candidate.evidence_keywords,
                        "match_mode": candidate.metadata.get("match_mode"),
                        "provenance_url": candidate.metadata.get("provenance_url"),
                        "why_matched": f"expanded_indicator={item.get('name_ru')} q={search_q}",
                        "risk_flags": [],
                    })

    return EvidenceBundleArtifact(
        selected_sources=selected,
        rejected_sources=rejected,
        retrieval_status="ok" if selected else "no_candidate",
        qdrant_status=result.dense_status,
        dense_status=result.dense_status,
    )


def _should_run_ckan(query: str, expected_sources: list[str]) -> bool:
    """Return True if CKAN scout should be invoked."""
    normalized_expected = {s.strip().lower() for s in expected_sources}
    if "ckan" in normalized_expected:
        return True
    for pattern in _CKAN_TRIGGER_PATTERNS:
        if pattern.search(query):
            return True
    return False


def _run_ckan_scout(query: str) -> list[dict[str, Any]]:
    """Run bounded CKAN package search and return compressed source cards."""
    try:
        from app.data.ckan_adapter import search_ckan_source_cards
        return search_ckan_source_cards(query, rows=5)
    except Exception:
        return []
