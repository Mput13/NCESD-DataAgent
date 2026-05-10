from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.retrieval.embedding_index import (
    EmbeddingIndexConfig,
    QdrantEmbeddingIndex,
    YandexEmbeddingProvider,
)

TOKEN_RE = re.compile(r"[\wА-Яа-яЁё]+", re.UNICODE)

# Contextual share/percent phrases that indicate a document is NOT a direct indicator
# when the query is asking for an absolute metric (e.g., GDP value, not GDP share).
_CONTEXTUAL_SHARE_PHRASES_RU = [
    "удельный вес",
    "доля",
    "в процентах от",
    "в % от",
    "в процентах",
    "отношение к",
]
_CONTEXTUAL_SHARE_PHRASES_EN = [
    "share",
    "percent of gdp",
    "% of gdp",
    "as a percentage",
    "as a share",
    "ratio to",
]

# Direct economic indicator keywords that boost exact-match cards
_DIRECT_INDICATOR_KEYWORDS_RU = ["ввп", "валовой", "внутренний", "продукт", "ипц", "инфляция"]
_DIRECT_INDICATOR_KEYWORDS_EN = ["gdp", "cpi", "population", "inflation", "unemployment"]


@dataclass(frozen=True)
class RetrievalCandidate:
    """Metadata-rich source card returned by lexical, dense, or rerank stages."""

    card_id: str
    chunk_id: str
    source_family: str
    title: str
    retrieval_mode: str
    score: float
    relevance_score: float
    evidence_keywords: list[str]
    rejection_reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HybridRetrievalResult:
    query: str
    candidates: list[RetrievalCandidate]
    rejected_candidates: list[RetrievalCandidate]
    dense_status: str
    rerank_status: str
    index_manifest_status: str
    qdrant_collection: str


class LexicalBM25Retriever:
    """Small BM25/FTS local approximation over prepared source-card chunks."""

    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents
        self.doc_tokens = [_tokens(str(document.get("embedding_text", ""))) for document in documents]
        self.doc_lengths = [len(tokens) for tokens in self.doc_tokens]
        self.avg_doc_length = sum(self.doc_lengths) / len(self.doc_lengths) if self.doc_lengths else 0.0
        self.document_frequency = Counter(
            token for tokens in self.doc_tokens for token in set(tokens)
        )

    def search(self, query: str, *, limit: int = 5) -> list[RetrievalCandidate]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        results: list[RetrievalCandidate] = []
        for document, tokens, length in zip(
            self.documents, self.doc_tokens, self.doc_lengths, strict=True
        ):
            score = self._bm25_score(query_tokens, tokens, length)
            overlap = sorted(set(query_tokens).intersection(tokens))
            if score <= 0 and not overlap:
                continue
            results.append(
                _candidate_from_document(
                    document,
                    retrieval_mode="lexical_bm25",
                    score=score,
                    evidence_keywords=overlap,
                )
            )
        results.sort(key=lambda candidate: candidate.score, reverse=True)
        return results[:limit]

    def _bm25_score(self, query_tokens: list[str], tokens: list[str], length: int) -> float:
        counts = Counter(tokens)
        total_docs = max(len(self.documents), 1)
        k1 = 1.5
        b = 0.75
        score = 0.0
        for token in query_tokens:
            if not counts[token]:
                continue
            doc_freq = self.document_frequency.get(token, 0)
            idf = math.log(1 + ((total_docs - doc_freq + 0.5) / (doc_freq + 0.5)))
            numerator = counts[token] * (k1 + 1)
            denominator = counts[token] + k1 * (
                1 - b + b * (length / max(self.avg_doc_length, 1.0))
            )
            score += idf * (numerator / denominator)
        return score


class DenseQdrantRetriever:
    """Dense retrieval over the prepared Qdrant collection when credentials allow it."""

    def __init__(self, index_manifest: dict[str, Any]) -> None:
        self.index_manifest = index_manifest

    @property
    def status(self) -> str:
        status = str(self.index_manifest.get("dense_status") or self.index_manifest.get("status"))
        if status != "ready":
            return status or "gated_skip"
        config = EmbeddingIndexConfig.from_env()
        if config.missing_env_vars:
            return "query_embedding_gated"
        return "ready"

    def search(self, query: str, *, limit: int = 5) -> list[RetrievalCandidate]:
        if self.status != "ready":
            return []
        config = EmbeddingIndexConfig.from_env()
        provider = YandexEmbeddingProvider(config)
        index = QdrantEmbeddingIndex(config)
        query_vector = provider.embed_query(query)
        hits = index.search(query_vector, limit=limit)
        return [
            _candidate_from_document(
                hit["payload"],
                retrieval_mode="dense_qdrant",
                score=float(hit["score"]),
                evidence_keywords=[],
            )
            for hit in hits
        ]


class BGERerankerCompatible:
    """bge-reranker-v2-m3-compatible seam with deterministic credential-aware fallback."""

    model_name = "bge-reranker-v2-m3"

    def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
        *,
        expected_sources: list[str],
    ) -> tuple[list[RetrievalCandidate], str]:
        if not candidates:
            return [], "fallback_no_candidates"
        if os.getenv("BGE_RERANKER_URL"):
            return candidates, "bge-reranker-v2-m3_endpoint_configured_not_called_in_phase1"

        query_tokens = set(_tokens(query))
        expected = {_normalize_source(source) for source in expected_sources}
        query_asks_for_share = _query_asks_for_share(query)

        reranked: list[RetrievalCandidate] = []
        for candidate in candidates:
            # Source family bonus (Phase 1 preserved)
            source_bonus = 0.5 if _normalize_source(candidate.source_family) in expected else 0.0
            # Expected source family exact match bonus (D-20: direct indicator intent)
            if expected and _normalize_source(candidate.source_family) in expected:
                source_bonus = 0.75  # upgraded from Phase 1 0.5

            # Keyword overlap bonus (Phase 1 preserved)
            keyword_bonus = len(query_tokens.intersection(candidate.evidence_keywords)) * 0.25

            # Domain-aware bonuses (Phase 2 additions)
            # +2.5 for exact indicator/code/title match
            exact_match_bonus = _exact_indicator_match_bonus(query, candidate)
            # +1.0 for direct GDP/CPI/population keyword match
            direct_kw_bonus = _direct_keyword_bonus(query_tokens, candidate)
            # -1.5 contextual penalty when title is a share/percent but query is not
            contextual_penalty = _contextual_penalty(candidate, query_asks_for_share)

            score = candidate.score + source_bonus + keyword_bonus + exact_match_bonus + direct_kw_bonus + contextual_penalty
            reranked.append(
                RetrievalCandidate(
                    **{
                        **candidate.__dict__,
                        "score": score,
                        "relevance_score": round(min(score, 1.0), 4),
                    }
                )
            )
        reranked.sort(key=lambda candidate: candidate.score, reverse=True)
        return reranked, "fallback_keyword_overlap"


class HybridRetriever:
    """Hybrid lexical + dense Qdrant retrieval over the prepared index contract."""

    def __init__(self, index_manifest_path: Path) -> None:
        self.index_manifest_path = index_manifest_path
        self.index_manifest = json.loads(index_manifest_path.read_text(encoding="utf-8"))
        self.documents = load_documents_from_index_manifest(self.index_manifest)
        self.lexical = LexicalBM25Retriever(self.documents)
        self.dense = DenseQdrantRetriever(self.index_manifest)
        self.reranker = BGERerankerCompatible()

    def search(
        self,
        query: str,
        *,
        expected_sources: list[str] | None = None,
        limit: int = 5,
    ) -> HybridRetrievalResult:
        expected_sources = expected_sources or []
        lexical = self.lexical.search(query, limit=limit)
        dense = self.dense.search(query, limit=limit)
        merged = _merge_candidates(lexical + dense)
        reranked, rerank_status = self.reranker.rerank(
            query,
            merged,
            expected_sources=expected_sources,
        )
        accepted, rejected = split_rejections(reranked, expected_sources=expected_sources, query=query)
        mode = "hybrid_lexical_dense"
        if self.dense.status != "ready":
            mode = "hybrid_lexical_dense_gated"
        accepted = [
            RetrievalCandidate(
                **{
                    **candidate.__dict__,
                    "retrieval_mode": mode if candidate.retrieval_mode.startswith("lexical") else candidate.retrieval_mode,
                }
            )
            for candidate in accepted
        ]
        return HybridRetrievalResult(
            query=query,
            candidates=accepted[:limit],
            rejected_candidates=rejected,
            dense_status=self.dense.status,
            rerank_status=rerank_status,
            index_manifest_status=str(self.index_manifest.get("status")),
            qdrant_collection=str(self.index_manifest.get("collection_name", "")),
        )


def load_documents_from_index_manifest(index_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    artifact_path = Path(str(index_manifest.get("corpus_artifact_path") or ""))
    if not artifact_path.exists():
        raise FileNotFoundError(f"Prepared index corpus artifact not found: {artifact_path}")
    return [
        json.loads(line)
        for line in artifact_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def split_rejections(
    candidates: list[RetrievalCandidate],
    *,
    expected_sources: list[str],
    query: str = "",
) -> tuple[list[RetrievalCandidate], list[RetrievalCandidate]]:
    """Split candidates into accepted and rejected, attaching concrete rejection reasons.

    Rejection reasons:
    - source_preference_mismatch: candidate source family does not match the expected
      sources explicitly requested by the caller.
    - source_family_mismatch: legacy alias (preserved for backward compatibility).
    - contextual_match_not_direct_indicator: candidate title is a contextual share/percent
      metric, but the query is asking for a direct absolute indicator.
    - no_lexical_or_dense_evidence: candidate has zero or negative retrieval score.
    """
    expected = {_normalize_source(source) for source in expected_sources}
    query_asks_for_share = _query_asks_for_share(query) if query else False
    accepted: list[RetrievalCandidate] = []
    rejected: list[RetrievalCandidate] = []
    for candidate in candidates:
        reasons = list(candidate.rejection_reasons)
        if expected and _normalize_source(candidate.source_family) not in expected:
            # Use source_preference_mismatch when explicit source preference was given
            reasons.append("source_preference_mismatch")
        if candidate.score <= 0:
            reasons.append("no_lexical_or_dense_evidence")
        # Add contextual rejection reason for share/percent titles when query is direct
        if not query_asks_for_share and _title_is_contextual_share(candidate.title):
            reasons.append("contextual_match_not_direct_indicator")
        if reasons:
            rejected.append(
                RetrievalCandidate(**{**candidate.__dict__, "rejection_reasons": reasons})
            )
        else:
            accepted.append(candidate)
    return accepted, rejected


def _merge_candidates(candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
    merged: dict[str, RetrievalCandidate] = {}
    for candidate in candidates:
        existing = merged.get(candidate.card_id)
        if existing is None or candidate.score > existing.score:
            merged[candidate.card_id] = candidate
    return sorted(merged.values(), key=lambda item: item.score, reverse=True)


def _candidate_from_document(
    document: dict[str, Any],
    *,
    retrieval_mode: str,
    score: float,
    evidence_keywords: list[str],
) -> RetrievalCandidate:
    text = str(document.get("embedding_text", ""))
    title = _extract_text_field(text, "title") or str(document.get("title") or document.get("card_id"))
    metadata = {
        "provenance_url": document.get("provenance_url"),
        "resource_url": document.get("resource_url"),
        "match_mode": (document.get("metadata") or {}).get("match_mode"),
        "embedding_text": text,
    }
    return RetrievalCandidate(
        card_id=str(document.get("card_id", "")),
        chunk_id=str(document.get("chunk_id", "")),
        source_family=str(document.get("source_family", "")),
        title=title,
        retrieval_mode=retrieval_mode,
        score=round(float(score), 6),
        relevance_score=round(min(max(float(score), 0.0), 1.0), 4),
        evidence_keywords=evidence_keywords,
        metadata=metadata,
    )


def _extract_text_field(text: str, field_name: str) -> str | None:
    prefix = f"{field_name}:"
    for line in text.splitlines():
        if line.lower().startswith(prefix):
            return line.split(":", 1)[1].strip()
    return None


def _tokens(text: str) -> list[str]:
    tokens = [token.lower() for token in TOKEN_RE.findall(text)]
    expanded = list(tokens)
    if "ввп" in tokens:
        expanded.extend(["gdp", "валовой", "внутренний", "продукт"])
    if "gdp" in tokens:
        expanded.append("ввп")
    return expanded


def _normalize_source(source: str) -> str:
    return source.strip().lower().replace(" ", "_")


def _title_is_contextual_share(title: str) -> bool:
    """Return True if the title describes a share/percent metric, not a direct absolute metric."""
    title_lower = title.lower()
    for phrase in _CONTEXTUAL_SHARE_PHRASES_RU:
        if phrase in title_lower:
            return True
    for phrase in _CONTEXTUAL_SHARE_PHRASES_EN:
        if phrase in title_lower:
            return True
    return False


def _query_asks_for_share(query: str) -> bool:
    """Return True if the query itself asks for a share or percentage."""
    q_lower = query.lower()
    for phrase in _CONTEXTUAL_SHARE_PHRASES_RU + _CONTEXTUAL_SHARE_PHRASES_EN:
        if phrase in q_lower:
            return True
    return False


def _exact_indicator_match_bonus(query: str, candidate: RetrievalCandidate) -> float:
    """Return +2.5 bonus for exact indicator code/title matches in the candidate embedding text."""
    query_lower = query.lower()
    embedding_text = str(candidate.metadata.get("embedding_text", "")).lower()
    title = candidate.title.lower()

    # Check for indicator code match in query vs embedding text
    indicator_code = ""
    for line in embedding_text.splitlines():
        if line.startswith("indicator_code:"):
            indicator_code = line.split(":", 1)[1].strip().lower()
            break

    if indicator_code and indicator_code in query_lower:
        return 2.5

    # Check for direct title/keyword match in query and title
    query_tokens = set(_tokens(query))
    title_tokens = set(_tokens(title))
    # High overlap between query tokens and title tokens = near-exact match
    if query_tokens and len(query_tokens.intersection(title_tokens)) >= max(2, len(query_tokens) * 0.6):
        return 2.5

    return 0.0


def _direct_keyword_bonus(query_tokens: set[str], candidate: RetrievalCandidate) -> float:
    """Return +1.0 bonus when direct economic indicator keywords appear in both query and candidate."""
    direct_kws = set(_DIRECT_INDICATOR_KEYWORDS_RU + _DIRECT_INDICATOR_KEYWORDS_EN)
    embedding_text = str(candidate.metadata.get("embedding_text", "")).lower()
    embedding_tokens = set(_tokens(embedding_text))

    shared_direct_kws = query_tokens.intersection(direct_kws).intersection(embedding_tokens)
    if shared_direct_kws:
        return 1.0
    return 0.0


def _contextual_penalty(candidate: RetrievalCandidate, query_asks_for_share: bool) -> float:
    """Return -1.5 penalty when candidate is a contextual share/percent but query wants a direct metric."""
    if query_asks_for_share:
        return 0.0  # No penalty — query explicitly wants a share/percent
    if _title_is_contextual_share(candidate.title):
        return -1.5
    return 0.0
