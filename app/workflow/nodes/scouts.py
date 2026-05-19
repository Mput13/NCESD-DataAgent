"""Source scout node for Phase 2 workflow.

run_source_scouts uses HybridRetriever for lexical/dense search across FedStat
and World Bank, and adds bounded CKAN discovery when relevant.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.artifacts.workflow_artifacts import EvidenceBundleArtifact, RetrievalInput, SearchProbe
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
    retrieval_input: RetrievalInput | None = None,
    research_design=None,  # ResearchDesignArtifact | None
) -> EvidenceBundleArtifact:
    """Run source scouts and return an EvidenceBundleArtifact.

    Uses HybridRetriever for FedStat and World Bank catalog search.
    Triggers bounded CKAN discovery when expected_sources includes 'ckan'
    or when the query contains ЕМИСС/НЦСЭД/CKAN keywords or a 5-digit code.
    """
    retriever = HybridRetriever(index_manifest_path)
    if retrieval_input is None:
        result = retriever.search(query, expected_sources=expected_sources, limit=5)
        return _legacy_evidence_from_result(
            query=query,
            expected_sources=expected_sources,
            result=result,
            retriever=retriever,
            research_design=research_design,
        )

    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    selected_by_id: dict[str, dict[str, Any]] = {}
    dense_status = "unknown"

    hard_expected_sources = (
        list(retrieval_input.source_scope.requested_sources)
        if retrieval_input.source_scope.source_constraint == "hard_only"
        else []
    )
    probes = sorted(retrieval_input.probes, key=lambda probe: probe.priority, reverse=True)
    for probe in probes:
        result = retriever.search(
            probe.text,
            expected_sources=hard_expected_sources,
            limit=retrieval_input.budget_policy.per_probe_limit,
        )
        dense_status = result.dense_status
        for candidate in result.candidates:
            _merge_selected_candidate(selected_by_id, candidate, probe)
        for candidate in result.rejected_candidates:
            rejected.append(_rejected_candidate_dict(candidate, probe))

        if _should_run_ckan_probe(probe, retrieval_input):
            for card in _run_ckan_scout(probe.text):
                _merge_ckan_card(selected_by_id, card, probe)

    selected = list(selected_by_id.values())
    return EvidenceBundleArtifact(
        selected_sources=selected,
        rejected_sources=rejected,
        retrieval_status="ok" if selected else "no_candidate",
        qdrant_status=dense_status,
        dense_status=dense_status,
    )


def _legacy_evidence_from_result(
    *,
    query: str,
    expected_sources: list[str],
    result: Any,
    retriever: HybridRetriever,
    research_design: Any,
) -> EvidenceBundleArtifact:
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for candidate in result.candidates:
        selected.append(_selected_candidate_dict(candidate, probe=None))

    for candidate in result.rejected_candidates:
        rejected.append(_rejected_candidate_dict(candidate, probe=None))

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
                    item_dict = _selected_candidate_dict(candidate, probe=None)
                    item_dict["why_matched"] = f"expanded_indicator={item.get('name_ru')} q={search_q}"
                    selected.append(item_dict)

    return EvidenceBundleArtifact(
        selected_sources=selected,
        rejected_sources=rejected,
        retrieval_status="ok" if selected else "no_candidate",
        qdrant_status=result.dense_status,
        dense_status=result.dense_status,
    )


def _selected_candidate_dict(candidate: Any, probe: SearchProbe | None) -> dict[str, Any]:
    item = {
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
    }
    if probe is not None:
        item["probe_evidence"] = [_probe_evidence(candidate, probe)]
    return item


def _rejected_candidate_dict(candidate: Any, probe: SearchProbe | None) -> dict[str, Any]:
    item = {
        "source_family": candidate.source_family,
        "card_id": candidate.card_id,
        "title": candidate.title,
        "score": candidate.score,
        "retrieval_mode": candidate.retrieval_mode,
        "rejection_reasons": candidate.rejection_reasons,
    }
    if probe is not None:
        item["probe_evidence"] = [_probe_evidence(candidate, probe)]
    return item


def _merge_selected_candidate(
    selected_by_id: dict[str, dict[str, Any]],
    candidate: Any,
    probe: SearchProbe,
) -> None:
    identity = _stable_source_identity(candidate.source_family, candidate.card_id)
    evidence = _probe_evidence(candidate, probe)
    if identity not in selected_by_id:
        selected_by_id[identity] = _selected_candidate_dict(candidate, probe)
        return
    existing = selected_by_id[identity]
    if candidate.score > existing.get("score", 0):
        existing.update(_selected_candidate_dict(candidate, probe))
    probe_evidence = existing.setdefault("probe_evidence", [])
    if not any(item.get("probe_id") == evidence["probe_id"] for item in probe_evidence):
        probe_evidence.append(evidence)


def _merge_ckan_card(
    selected_by_id: dict[str, dict[str, Any]],
    card: dict[str, Any],
    probe: SearchProbe,
) -> None:
    did = str(card.get("dataset_id", ""))
    if not did:
        return
    identity = _stable_source_identity("ckan", did)
    evidence = {
        "probe_id": probe.probe_id,
        "probe_text": probe.text,
        "purpose": probe.purpose,
        "origin": probe.origin,
        "source_family_hint": probe.source_family_hint,
        "score": 0.5,
        "retrieval_mode": "ckan_package_search",
    }
    if identity not in selected_by_id:
        selected_by_id[identity] = {
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
            "probe_evidence": [evidence],
        }
        return
    selected_by_id[identity].setdefault("probe_evidence", []).append(evidence)


def _probe_evidence(candidate: Any, probe: SearchProbe) -> dict[str, Any]:
    return {
        "probe_id": probe.probe_id,
        "probe_text": probe.text,
        "purpose": probe.purpose,
        "measure_id": probe.measure_id,
        "origin": probe.origin,
        "source_family_hint": probe.source_family_hint,
        "score": candidate.score,
        "retrieval_mode": candidate.retrieval_mode,
    }


def _stable_source_identity(source_family: str, card_id: str) -> str:
    return f"{source_family}:{card_id}"


def _should_run_ckan(query: str, expected_sources: list[str]) -> bool:
    """Return True if CKAN scout should be invoked."""
    normalized_expected = {s.strip().lower() for s in expected_sources}
    if "ckan" in normalized_expected:
        return True
    for pattern in _CKAN_TRIGGER_PATTERNS:
        if pattern.search(query):
            return True
    return False


def _should_run_ckan_probe(probe: SearchProbe, retrieval_input: RetrievalInput) -> bool:
    if probe.source_family_hint == "ckan":
        return True
    if "ckan" in retrieval_input.source_scope.requested_sources:
        return True
    return _should_run_ckan(probe.text, list(retrieval_input.source_scope.requested_sources))


def _run_ckan_scout(query: str) -> list[dict[str, Any]]:
    """Run bounded CKAN package search and return compressed source cards."""
    try:
        from app.data.ckan_adapter import search_ckan_source_cards
        return search_ckan_source_cards(query, rows=5)
    except Exception:
        return []
