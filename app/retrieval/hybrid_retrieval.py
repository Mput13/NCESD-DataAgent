"""
Hybrid Graph RAG retrieval pipeline.

Architecture:
    Query
      │
      ├─ LexicalBM25Retriever   → BM25 candidates (lexical match over corpus)
      │
      ├─ DenseQdrantRetriever   → ANN candidates from phase1_source_cards
      │                            (same single Qdrant collection, no duplication)
      │
      ├─ GraphExpander          → takes dense seed card_ids
      │   ├─ entity_link(seeds) → seed nodes in KnowledgeGraphStore
      │   ├─ expand_subgraph(seeds, hops=2) → neighbour card_ids via edge traversal
      │   └─ fetch_by_card_ids(neighbours) → Qdrant point lookup for neighbour docs
      │
      ├─ RRF fusion             → merge lexical + dense + graph_neighbour lists
      │
      └─ HybridRetrievalResult  → candidates + subgraph_context (for LLM)

Key design decisions:
- Graph does NOT have its own embedding collection. It reuses phase1_source_cards.
- Graph contribution = neighbours discovered via edge traversal from dense seeds.
- SubgraphContext carries structured graph info (nodes, edges) for downstream LLM use.
"""

from __future__ import annotations

import json
import math
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
from app.retrieval.graph_store import (
    KnowledgeGraphStore,
    SubgraphContext,
    extract_canonical_ids,
    extraction_readiness,
    normalize_identifier,
)

_TOKEN_RE = re.compile(r"[\wА-Яа-яЁё]+", re.UNICODE)

_STOPWORDS: frozenset[str] = frozenset(
    {
        "а", "в", "во", "год", "году", "данные", "дай", "для", "за", "и", "или",
        "источник", "источники", "как", "какой", "найди", "о", "об", "по",
        "покажи", "про", "с", "со", "что",
        "a", "an", "and", "data", "find", "for", "in", "of", "on", "or",
        "show", "source", "the", "to",
    }
)

_SYNONYM_MAP: dict[str, list[str]] = {
    "ввп": ["gdp", "валовой", "внутренний", "продукт"],
    "gdp": ["ввп"],
    "инфляция": ["ипц", "inflation", "cpi"],
    "ипц": ["инфляция", "cpi", "inflation"],
    "cpi": ["ипц", "инфляция"],
    "inflation": ["инфляция", "ипц"],
}

_SHARE_PHRASES: list[str] = [
    "удельный вес", "доля", "в процентах от", "в % от",
    "в процентах", "отношение к",
    "share", "percent of gdp", "% of gdp", "as a percentage", "as a share", "ratio to",
]

_MIN_MEANINGFUL_OVERLAP = 1


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetrievalCandidate:
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
    subgraph_context: SubgraphContext | None
    dense_status: str
    graph_status: str
    rerank_status: str
    index_manifest_status: str
    qdrant_collection: str


# ---------------------------------------------------------------------------
# Retrieval components
# ---------------------------------------------------------------------------

class LexicalBM25Retriever:
    """BM25 over source-card embedding_text with RU/EN synonym expansion."""

    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents
        self.doc_tokens = [_bm25_tokens(str(d.get("embedding_text", ""))) for d in documents]
        self.doc_lengths = [len(t) for t in self.doc_tokens]
        self.avg_doc_length = (
            sum(self.doc_lengths) / len(self.doc_lengths) if self.doc_lengths else 0.0
        )
        self.document_frequency: Counter[str] = Counter(
            tok for toks in self.doc_tokens for tok in set(toks)
        )

    def search(self, query: str, *, limit: int = 5) -> list[RetrievalCandidate]:
        q_tokens = _bm25_tokens(query)
        q_meaningful = _meaningful_tokens(query)
        if not q_tokens:
            return []
        results: list[RetrievalCandidate] = []
        for doc, toks, length in zip(self.documents, self.doc_tokens, self.doc_lengths):
            score = self._bm25(q_tokens, toks, length)
            overlap = sorted(set(q_meaningful).intersection(toks))
            if score <= 0 and not overlap:
                continue
            if len([t for t in overlap if t not in _STOPWORDS]) < _MIN_MEANINGFUL_OVERLAP:
                continue
            results.append(
                _make_candidate(doc, retrieval_mode="lexical_bm25", score=score, evidence=overlap)
            )
        results.sort(key=lambda c: c.score, reverse=True)
        return results[:limit]

    def _bm25(self, q_tokens: list[str], doc_tokens: list[str], length: int) -> float:
        counts = Counter(doc_tokens)
        n = max(len(self.documents), 1)
        k1, b = 1.5, 0.75
        score = 0.0
        for tok in q_tokens:
            if not counts[tok]:
                continue
            df = self.document_frequency.get(tok, 0)
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            tf = counts[tok]
            norm = tf + k1 * (1 - b + b * length / max(self.avg_doc_length, 1.0))
            score += idf * (tf * (k1 + 1) / norm)
        return score


class DenseQdrantRetriever:
    """ANN retrieval over phase1_source_cards collection."""

    def __init__(self, index_manifest: dict[str, Any]) -> None:
        self.index_manifest = index_manifest
        self._config: EmbeddingIndexConfig | None = None
        self._provider: YandexEmbeddingProvider | None = None
        self._index: QdrantEmbeddingIndex | None = None

    @property
    def status(self) -> str:
        raw = str(self.index_manifest.get("dense_status") or self.index_manifest.get("status", ""))
        if raw != "ready":
            return raw or "gated_skip"
        if EmbeddingIndexConfig.from_env().missing_env_vars:
            return "query_embedding_gated"
        return "ready"

    def _ensure_clients(self) -> tuple[EmbeddingIndexConfig, YandexEmbeddingProvider, QdrantEmbeddingIndex]:
        if self._config is None:
            self._config = EmbeddingIndexConfig.from_env()
            self._provider = YandexEmbeddingProvider(self._config)
            self._index = QdrantEmbeddingIndex(self._config)
        return self._config, self._provider, self._index  # type: ignore[return-value]

    def search(self, query: str, *, limit: int = 5) -> list[RetrievalCandidate]:
        if self.status != "ready":
            return []
        _, provider, index = self._ensure_clients()
        vector = provider.embed_query(query)
        hits = index.search(vector, limit=limit)
        return [
            _make_candidate(
                hit["payload"], retrieval_mode="dense_qdrant",
                score=float(hit["score"]), evidence=[],
            )
            for hit in hits
        ]

    def fetch_by_card_ids(self, card_ids: list[str]) -> list[RetrievalCandidate]:
        """
        Lookup documents in Qdrant by card_id from payload filter.
        Used by GraphExpander to fetch neighbour documents.
        """
        if self.status != "ready" or not card_ids:
            return []
        _, _, index = self._ensure_clients()
        # Scroll with filter — no embedding needed, pure metadata lookup
        from qdrant_client.models import Filter, FieldCondition, MatchAny
        try:
            results, _ = index.client.scroll(
                collection_name=index.config.collection_name,
                scroll_filter=Filter(
                    must=[FieldCondition(key="card_id", match=MatchAny(any=card_ids))]
                ),
                limit=len(card_ids) * 2,
                with_payload=True,
                with_vectors=False,
            )
            return [
                _make_candidate(
                    point.payload or {}, retrieval_mode="graph_neighbour",
                    score=0.0, evidence=[],
                )
                for point in results
                if point.payload
            ]
        except Exception:
            return []


class GraphExpander:
    """
    Post-retrieval graph expansion.

    Takes seed card_ids from dense retrieval, expands subgraph via edge traversal,
    returns neighbour documents and structured SubgraphContext for LLM.
    """

    def __init__(
        self,
        graph: KnowledgeGraphStore,
        dense: DenseQdrantRetriever,
    ) -> None:
        self.graph = graph
        self.dense = dense

    @property
    def status(self) -> str:
        return "ready"

    def expand(
        self,
        seed_card_ids: list[str],
        *,
        hops: int = 2,
    ) -> tuple[list[RetrievalCandidate], SubgraphContext]:
        """
        1. entity_link(seed_card_ids) → seed GraphNodes
        2. expand_subgraph(seed_nodes, hops) → SubgraphContext with neighbour card_ids
        3. fetch_by_card_ids(neighbours) → RetrievalCandidates via Qdrant scroll
        """
        if not seed_card_ids:
            return [], SubgraphContext([], [], [], [])

        # Step 1: entity linking
        seed_nodes = self.graph.entity_link(seed_card_ids)
        seed_node_ids = [n.node_id for n in seed_nodes]

        # Step 2: subgraph traversal
        subgraph = self.graph.expand_subgraph(seed_node_ids, hops=hops)

        # Step 3: fetch neighbour documents from Qdrant (no re-embedding needed)
        neighbour_ids = [
            cid for cid in subgraph.neighbour_card_ids
            if cid not in set(seed_card_ids)
        ]
        neighbour_docs = self.dense.fetch_by_card_ids(neighbour_ids) if neighbour_ids else []

        return neighbour_docs, subgraph


# ---------------------------------------------------------------------------
# Main retriever
# ---------------------------------------------------------------------------

class HybridRetriever:
    """
    Hybrid Graph RAG retriever.

    Pipeline per query:
      1. BM25 lexical search over local corpus
      2. Dense ANN search over phase1_source_cards (Qdrant)
      3. Graph expansion from dense seeds → neighbour documents via edge traversal
      4. RRF fusion: lexical + dense + graph_neighbours
      5. Rejection filtering
      6. Return HybridRetrievalResult with SubgraphContext attached
    """

    def __init__(self, index_manifest_path: Path) -> None:
        self.index_manifest_path = index_manifest_path
        self.index_manifest = json.loads(
            index_manifest_path.read_text(encoding="utf-8")
        )
        self.documents = _load_documents(self.index_manifest)

        self.lexical = LexicalBM25Retriever(self.documents)
        self.dense = DenseQdrantRetriever(self.index_manifest)
        self.graph = KnowledgeGraphStore(self.documents)
        self.graph_expander = GraphExpander(self.graph, self.dense)
        self.documents_by_card_id = {
            str(document.get("card_id") or ""): document for document in self.documents
        }

    def search(
        self,
        query: str,
        *,
        expected_sources: list[str] | None = None,
        limit: int = 5,
    ) -> HybridRetrievalResult:
        expected_sources = expected_sources or []
        pool = max(limit * 10, 20)

        # --- Lexical ---
        lexical_cands = self.lexical.search(query, limit=pool)

        # --- Dense ANN ---
        dense_cands = self.dense.search(query, limit=pool)

        # --- Graph-first concept/entity lookup ---
        graph_first_cands = self._graph_first(query, pool=pool)

        # --- Graph expansion from dense seeds ---
        graph_cands, subgraph_ctx = self._graph_expand(dense_cands, pool=pool)

        # --- RRF fusion ---
        fused = _rrf_fuse(
            [
                ("lexical", lexical_cands, 0.55),
                ("dense", dense_cands, 4.0),
                ("graph_first", graph_first_cands, 2.5),
                ("graph", graph_cands, 1.5),
            ],
            limit=pool,
        )

        # --- Rejection filtering ---
        accepted, rejected = _split_rejections(
            fused, expected_sources=expected_sources, query=query
        )

        mode = (
            "hybrid_lexical_dense_graph"
            if self.dense.status == "ready"
            else "hybrid_lexical_dense_gated"
        )
        accepted = [
            RetrievalCandidate(**{**c.__dict__, "retrieval_mode": mode})
            for c in accepted
        ]

        return HybridRetrievalResult(
            query=query,
            candidates=accepted[:limit],
            rejected_candidates=rejected,
            subgraph_context=subgraph_ctx if subgraph_ctx.nodes else None,
            dense_status=self.dense.status,
            graph_status=self.graph_expander.status,
            rerank_status="rrf_fusion",
            index_manifest_status=str(self.index_manifest.get("status", "")),
            qdrant_collection=str(self.index_manifest.get("collection_name", "")),
        )

    def _graph_expand(
        self,
        dense_cands: list[RetrievalCandidate],
        *,
        pool: int,
    ) -> tuple[list[RetrievalCandidate], SubgraphContext]:
        if not dense_cands or self.graph_expander.status != "ready":
            return [], SubgraphContext([], [], [], [])

        seed_card_ids = [c.card_id for c in dense_cands[:20]]
        neighbour_cands, subgraph = self.graph_expander.expand(seed_card_ids, hops=2)
        return neighbour_cands[:pool], subgraph

    def _graph_first(self, query: str, *, pool: int) -> list[RetrievalCandidate]:
        card_ids = self.graph.graph_first_card_ids(query, limit=pool)
        candidates: list[RetrievalCandidate] = []
        for rank, card_id in enumerate(card_ids, start=1):
            doc = self.documents_by_card_id.get(card_id)
            if not doc:
                continue
            candidates.append(
                _make_candidate(
                    doc,
                    retrieval_mode="graph_first",
                    score=1.0 / rank,
                    evidence=["graph_first"],
                )
            )
        return candidates


# ---------------------------------------------------------------------------
# Fusion and filtering
# ---------------------------------------------------------------------------

def _rrf_fuse(
    ranked_lists: list[tuple[str, list[RetrievalCandidate], float]],
    *,
    limit: int,
    rrf_k: int = 60,
) -> list[RetrievalCandidate]:
    by_card: dict[str, RetrievalCandidate] = {}
    scores: dict[str, float] = {}
    evidence: dict[str, set[str]] = {}
    modes: dict[str, list[str]] = {}
    ranks: dict[str, dict[str, int]] = {}
    raw_scores: dict[str, dict[str, float]] = {}

    for mode, candidates, weight in ranked_lists:
        for rank, cand in enumerate(candidates, start=1):
            cid = cand.card_id
            if cid not in by_card or cand.score > by_card[cid].score:
                by_card[cid] = cand
            scores[cid] = scores.get(cid, 0.0) + weight / (rrf_k + rank)
            evidence.setdefault(cid, set()).update(cand.evidence_keywords)
            modes.setdefault(cid, []).append(mode)
            ranks.setdefault(cid, {})[mode] = rank
            raw_scores.setdefault(cid, {})[mode] = cand.score

    fused: list[RetrievalCandidate] = []
    for cid, cand in by_card.items():
        score = scores[cid]
        meta = {
            **cand.metadata,
            "fusion_modes": sorted(set(modes.get(cid, []))),
            "fusion_ranks": ranks.get(cid, {}),
            "fusion_raw_scores": raw_scores.get(cid, {}),
        }
        fused.append(
            RetrievalCandidate(
                **{
                    **cand.__dict__,
                    "retrieval_mode": "hybrid_rrf",
                    "score": round(float(score), 6),
                    "relevance_score": round(min(max(float(score), 0.0), 1.0), 4),
                    "evidence_keywords": sorted(evidence.get(cid, set())),
                    "metadata": meta,
                }
            )
        )
    fused.sort(key=lambda c: c.score, reverse=True)
    return fused[:limit]


def _split_rejections(
    candidates: list[RetrievalCandidate],
    *,
    expected_sources: list[str],
    query: str = "",
) -> tuple[list[RetrievalCandidate], list[RetrievalCandidate]]:
    expected = {_norm_source(s) for s in expected_sources}
    query_wants_share = _query_asks_share(query)
    accepted: list[RetrievalCandidate] = []
    rejected: list[RetrievalCandidate] = []
    for cand in candidates:
        reasons = list(cand.rejection_reasons)
        if expected and _norm_source(cand.source_family) not in expected:
            reasons.append("source_preference_mismatch")
        if cand.score <= 0:
            reasons.append("no_evidence")
        if not query_wants_share and _title_is_share(cand.title):
            reasons.append("contextual_match_not_direct_indicator")
        if reasons:
            rejected.append(RetrievalCandidate(**{**cand.__dict__, "rejection_reasons": reasons}))
        else:
            accepted.append(cand)
    return accepted, rejected


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_documents_from_index_manifest(index_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return _load_documents(index_manifest)


def _load_documents(index_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    artifact_path = Path(str(index_manifest.get("corpus_artifact_path") or ""))
    if not artifact_path.exists():
        raise FileNotFoundError(f"Corpus artifact not found: {artifact_path}")
    return [
        json.loads(line)
        for line in artifact_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _make_candidate(
    doc: dict[str, Any],
    *,
    retrieval_mode: str,
    score: float,
    evidence: list[str],
) -> RetrievalCandidate:
    text = str(doc.get("embedding_text", ""))
    title = _field_from_text(text, "title") or str(doc.get("title") or doc.get("card_id", ""))
    meta = {
        "provenance_url": doc.get("provenance_url"),
        "resource_url": doc.get("resource_url"),
        "match_mode": (doc.get("metadata") or {}).get("match_mode"),
        "embedding_text": text,
        "canonical_ids": sorted(extract_canonical_ids(doc)),
        "extraction_readiness": extraction_readiness(doc),
    }
    return RetrievalCandidate(
        card_id=str(doc.get("card_id", "")),
        chunk_id=str(doc.get("chunk_id", "")),
        source_family=str(doc.get("source_family", "")),
        title=title,
        retrieval_mode=retrieval_mode,
        score=round(float(score), 6),
        relevance_score=round(min(max(float(score), 0.0), 1.0), 4),
        evidence_keywords=evidence,
        metadata=meta,
    )


def _field_from_text(text: str, field_name: str) -> str | None:
    prefix = f"{field_name}:"
    for line in text.splitlines():
        if line.lower().startswith(prefix):
            return line.split(":", 1)[1].strip()
    return None


def _bm25_tokens(text: str) -> list[str]:
    raw = [t.casefold() for t in _TOKEN_RE.findall(text)]
    out: list[str] = []
    for tok in raw:
        out.append(tok)
        out.extend(_SYNONYM_MAP.get(tok, []))
    return out


def _meaningful_tokens(text: str) -> list[str]:
    return [
        t for t in _bm25_tokens(text)
        if t not in _STOPWORDS and not t.isdigit() and len(t) > 1
    ]


def _norm_source(source: str) -> str:
    return source.strip().casefold().replace(" ", "_")


def _title_is_share(title: str) -> bool:
    t = title.casefold()
    return any(p in t for p in _SHARE_PHRASES)


def _query_asks_share(query: str) -> bool:
    q = query.casefold()
    return any(p in q for p in _SHARE_PHRASES)
