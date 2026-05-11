"""Source scout node for Phase 2 workflow.

run_source_scouts uses HybridRetriever for lexical/dense search across FedStat
and World Bank, and adds bounded CKAN discovery when relevant.
"""
from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.artifacts.workflow_artifacts import (
    EvidenceBundleArtifact,
    IntentFrame,
    RejectedSourceCandidate,
    ResearchDesignArtifact,
    RetrievalChannelStatus,
    SourceCandidate,
)
from app.retrieval.hybrid_retrieval import HybridRetriever

# Patterns that trigger CKAN scout regardless of expected_sources
_CKAN_TRIGGER_PATTERNS = [
    re.compile(r"\b\d{5}\b"),          # 5-digit ЕМИСС-style indicator codes like 57319
    re.compile(r"ЕМИСС", re.IGNORECASE),
    re.compile(r"НЦСЭД", re.IGNORECASE),
    re.compile(r"\bCKAN\b", re.IGNORECASE),
    re.compile(r"nsedc", re.IGNORECASE),
]


class RetrievalPolicy(BaseModel):
    """Bounded retrieval settings for source scouts."""

    expected_sources: list[str] = Field(default_factory=list)
    ckan_required: bool = False
    limit: int = 5

    model_config = ConfigDict(extra="forbid")


class ScoutQuery(BaseModel):
    """Concrete query text sent to retrieval channels."""

    original_query: str
    normalized_query: str | None = None
    intent_terms: list[str] = Field(default_factory=list)
    research_terms: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @property
    def text(self) -> str:
        parts = [self.normalized_query or self.original_query]
        parts.extend(self.intent_terms)
        parts.extend(self.research_terms)
        return " ".join(str(part).strip() for part in parts if str(part).strip())


class SourceScoutInput(BaseModel):
    """Typed input for scouts, keeping legacy query calls available."""

    query: str
    normalized_query: str | None = None
    intent: IntentFrame | None = None
    research_design: ResearchDesignArtifact | None = None
    retrieval_policy: RetrievalPolicy = Field(default_factory=RetrievalPolicy)
    index_manifest_path: Path

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


def run_source_scouts(
    query: str | SourceScoutInput,
    *,
    expected_sources: list[str] | None = None,
    index_manifest_path: Path | None = None,
) -> EvidenceBundleArtifact:
    """Run source scouts and return an EvidenceBundleArtifact.

    Uses HybridRetriever for FedStat and World Bank catalog search.
    Triggers bounded CKAN discovery when expected_sources includes 'ckan'
    or when the query contains ЕМИСС/НЦСЭД/CKAN keywords or a 5-digit code.
    """
    scout_input = _coerce_scout_input(
        query,
        expected_sources=expected_sources,
        index_manifest_path=index_manifest_path,
    )
    scout_query = build_scout_query(scout_input)
    query_text = scout_query.text
    policy = scout_input.retrieval_policy

    retriever = HybridRetriever(scout_input.index_manifest_path)
    result = retriever.search(
        query_text,
        expected_sources=policy.expected_sources,
        limit=policy.limit,
    )

    selected: list[SourceCandidate] = []
    rejected: list[RejectedSourceCandidate] = []

    for candidate in result.candidates:
        selected.append(_source_candidate_from_retrieval(candidate))

    for candidate in result.rejected_candidates:
        rejected.append(_rejected_candidate_from_retrieval(candidate))

    channel_statuses = _retrieval_channel_statuses(
        selected,
        rejected,
        dense_status=result.dense_status,
        graph_status=result.graph_status,
        ckan_required=policy.ckan_required,
    )

    # CKAN discovery: trigger if expected or query matches patterns
    if _should_run_ckan(query_text, policy.expected_sources):
        ckan_cards, ckan_status = _run_ckan_scout(query_text)
        for card in ckan_cards:
            # Check if already in selected/rejected by dataset_id
            existing_ids = {
                candidate.card_id or candidate.dataset_id
                for candidate in selected + rejected
            }
            did = card.get("dataset_id", "")
            if did and did not in existing_ids:
                selected.append(_source_candidate_from_ckan_card(card))
        channel_statuses = _replace_channel_status(
            channel_statuses,
            RetrievalChannelStatus(
                channel="ckan",
                status=ckan_status["status"],
                required=policy.ckan_required,
                selected_count=len(ckan_cards),
                reason=ckan_status.get("reason"),
                error=ckan_status.get("error"),
            ),
        )

    selected_dicts = [candidate.model_dump(exclude_none=True) for candidate in selected]
    rejected_dicts = [candidate.model_dump(exclude_none=True) for candidate in rejected]

    return EvidenceBundleArtifact(
        selected_for_coverage=selected,
        rejected_candidates=rejected,
        selected_sources=selected_dicts,
        rejected_sources=rejected_dicts,
        channel_statuses=channel_statuses,
        subgraph_context=_serialize_subgraph_context(result.subgraph_context),
        retrieval_status=_aggregate_retrieval_status(channel_statuses, has_selected=bool(selected)),
        qdrant_status=result.dense_status,
        dense_status=result.dense_status,
    )


def build_scout_query(scout_input: SourceScoutInput) -> ScoutQuery:
    """Build a retrieval query from normalized/original query plus upstream artifacts."""
    intent_terms: list[str] = []
    if scout_input.intent:
        known = scout_input.intent.known_fields or {}
        for key in ("indicator", "indicator_name", "indicator_id", "geography", "period"):
            value = known.get(key)
            if value:
                intent_terms.append(str(value))
        intent_terms.extend(str(source) for source in scout_input.intent.source_preferences)

    research_terms: list[str] = []
    if scout_input.research_design:
        research_terms.extend(scout_input.research_design.indicators[:5])
        research_terms.extend(scout_input.research_design.dimensions[:5])
        research_terms.extend(scout_input.research_design.hypotheses[:2])

    return ScoutQuery(
        original_query=scout_input.query,
        normalized_query=scout_input.normalized_query,
        intent_terms=intent_terms,
        research_terms=research_terms,
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


def _run_ckan_scout(query: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Run bounded CKAN package search and return compressed source cards."""
    try:
        from app.data.ckan_adapter import search_ckan_source_cards
        cards = search_ckan_source_cards(query, rows=5)
        return cards, {"status": "ok" if cards else "empty"}
    except Exception as exc:
        return [], {
            "status": "error",
            "reason": "ckan_package_search_error",
            "error": str(exc),
        }


def _coerce_scout_input(
    query: str | SourceScoutInput,
    *,
    expected_sources: list[str] | None,
    index_manifest_path: Path | None,
) -> SourceScoutInput:
    if isinstance(query, SourceScoutInput):
        return query
    if index_manifest_path is None:
        raise ValueError("index_manifest_path is required for legacy run_source_scouts calls")
    expected = expected_sources or []
    return SourceScoutInput(
        query=query,
        retrieval_policy=RetrievalPolicy(
            expected_sources=expected,
            ckan_required="ckan" in {source.strip().lower() for source in expected},
        ),
        index_manifest_path=index_manifest_path,
    )


def _source_candidate_from_retrieval(candidate: Any) -> SourceCandidate:
    metadata = dict(candidate.metadata or {})
    provenance = {
        "retrieval_mode": candidate.retrieval_mode,
        "fusion_modes": list(metadata.get("fusion_modes") or []),
        "fusion_ranks": dict(metadata.get("fusion_ranks") or {}),
        "fusion_raw_scores": dict(metadata.get("fusion_raw_scores") or {}),
        "canonical_ids": list(metadata.get("canonical_ids") or []),
        "extraction_readiness": metadata.get("extraction_readiness"),
        "resource_url": metadata.get("resource_url"),
    }
    retrieval_paths = list(provenance["fusion_modes"] or [candidate.retrieval_mode])
    readiness = metadata.get("extraction_readiness") or {}
    blockers = [
        str(reason)
        for reason in (
            readiness.get("blockers") if isinstance(readiness, dict) else []
        ) or []
    ]
    return SourceCandidate(
        source_candidate_id=candidate.card_id,
        source_family=candidate.source_family,
        card_id=candidate.card_id,
        chunk_id=candidate.chunk_id,
        dataset_id=_dataset_id_from_card(candidate.card_id),
        title=candidate.title,
        score=candidate.score,
        relevance_score=candidate.relevance_score,
        retrieval_mode=candidate.retrieval_mode,
        retrieval_paths=retrieval_paths,
        evidence_terms=list(candidate.evidence_keywords),
        match_mode=metadata.get("match_mode"),
        provenance_url=metadata.get("provenance_url"),
        why_matched=f"hybrid retrieval score={candidate.score:.4f}",
        risk_flags=[],
        retrieval_provenance=provenance,
        adapter_name=_adapter_for_family(candidate.source_family),
        extraction_ready=not blockers,
        extraction_blockers=blockers,
        metadata={
            "resource_url": metadata.get("resource_url"),
            "canonical_ids": metadata.get("canonical_ids"),
        },
    )


def _rejected_candidate_from_retrieval(candidate: Any) -> RejectedSourceCandidate:
    metadata = dict(candidate.metadata or {})
    provenance = {
        "retrieval_mode": candidate.retrieval_mode,
        "fusion_modes": list(metadata.get("fusion_modes") or []),
        "fusion_ranks": dict(metadata.get("fusion_ranks") or {}),
        "fusion_raw_scores": dict(metadata.get("fusion_raw_scores") or {}),
    }
    return RejectedSourceCandidate(
        source_candidate_id=candidate.card_id,
        source_family=candidate.source_family,
        card_id=candidate.card_id,
        chunk_id=candidate.chunk_id,
        dataset_id=_dataset_id_from_card(candidate.card_id),
        title=candidate.title,
        score=candidate.score,
        retrieval_mode=candidate.retrieval_mode,
        retrieval_paths=list(provenance["fusion_modes"] or [candidate.retrieval_mode]),
        rejection_reasons=list(candidate.rejection_reasons),
        retrieval_provenance=provenance,
    )


def _source_candidate_from_ckan_card(card: dict[str, Any]) -> SourceCandidate:
    did = str(card.get("dataset_id") or card.get("card_id") or "")
    return SourceCandidate(
        source_candidate_id=did,
        source_family="ckan",
        card_id=did,
        chunk_id=did,
        dataset_id=did,
        title=str(card.get("title") or ""),
        formats=[str(fmt) for fmt in card.get("formats") or []],
        resource_count=int(card.get("resource_count") or 0),
        promoted_resources=list(card.get("promoted_resources") or []),
        provenance_url=card.get("provenance_url") or "",
        why_matched="ckan_bounded_package_search",
        risk_flags=[str(flag) for flag in card.get("risk_flags") or []],
        score=0.5,
        relevance_score=0.5,
        retrieval_mode="ckan_package_search",
        retrieval_paths=["ckan"],
        evidence_terms=[],
        match_mode="ckan_catalog",
        retrieval_provenance={"retrieval_mode": "ckan_package_search"},
        adapter_name="extract_ckan_dataset",
        extraction_ready=True,
    )


def _retrieval_channel_statuses(
    selected: list[SourceCandidate],
    rejected: list[RejectedSourceCandidate],
    *,
    dense_status: str,
    graph_status: str,
    ckan_required: bool,
) -> list[RetrievalChannelStatus]:
    statuses: list[RetrievalChannelStatus] = []
    for channel in ("lexical", "dense", "graph"):
        selected_count = sum(1 for item in selected if channel in item.retrieval_paths)
        rejected_count = sum(1 for item in rejected if channel in item.retrieval_paths)
        if channel == "dense" and dense_status != "ready":
            status = "gated"
            reason = dense_status
        elif channel == "graph" and graph_status != "ready":
            status = "gated"
            reason = graph_status
        else:
            status = "ok" if selected_count else "empty"
            reason = None
        statuses.append(
            RetrievalChannelStatus(
                channel=channel,  # type: ignore[arg-type]
                status=status,  # type: ignore[arg-type]
                selected_count=selected_count,
                rejected_count=rejected_count,
                reason=reason,
            )
        )
    statuses.append(
        RetrievalChannelStatus(
            channel="ckan",
            status="not_run",
            required=ckan_required,
        )
    )
    return statuses


def _replace_channel_status(
    statuses: list[RetrievalChannelStatus],
    replacement: RetrievalChannelStatus,
) -> list[RetrievalChannelStatus]:
    return [
        replacement if status.channel == replacement.channel else status
        for status in statuses
    ]


def _aggregate_retrieval_status(
    statuses: list[RetrievalChannelStatus],
    *,
    has_selected: bool,
) -> str:
    if not has_selected:
        return "no_candidate"
    visible_failures = [
        status for status in statuses
        if status.status in {"gated", "error"} and (status.required or status.channel in {"dense", "graph"})
    ]
    if visible_failures:
        return "partial"
    return "ok"


def _serialize_subgraph_context(subgraph_context: Any) -> dict[str, Any] | None:
    if subgraph_context is None:
        return None
    if is_dataclass(subgraph_context):
        data = asdict(subgraph_context)
    elif hasattr(subgraph_context, "__dict__"):
        data = dict(subgraph_context.__dict__)
    else:
        return None
    if hasattr(subgraph_context, "as_text"):
        data["text"] = subgraph_context.as_text()
    return data


def _dataset_id_from_card(card_id: str) -> str | None:
    parts = str(card_id).split(":")
    if len(parts) >= 2:
        return parts[1]
    return card_id or None


def _adapter_for_family(source_family: str) -> str | None:
    family = source_family.strip().lower()
    return {
        "fedstat": "extract_fedstat_dataset",
        "world_bank": "extract_world_bank_dataset",
        "worldbank": "extract_world_bank_dataset",
        "ckan": "extract_ckan_dataset",
    }.get(family)
