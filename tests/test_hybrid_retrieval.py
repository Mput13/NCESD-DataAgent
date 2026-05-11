from __future__ import annotations

import csv
import json
from pathlib import Path


# ---------------------------------------------------------------------------
# LexicalBM25Retriever
# ---------------------------------------------------------------------------

def test_lexical_bm25_returns_metadata_rich_source_cards() -> None:
    from app.retrieval.hybrid_retrieval import LexicalBM25Retriever

    documents = [
        {
            "chunk_id": "fedstat:gdp",
            "card_id": "fedstat:57319:metadata",
            "source_family": "fedstat",
            "embedding_text": "title: Валовой внутренний продукт GDP\nsource_family: FedStat\ndataset_id: 57319",
            "provenance_url": "https://fedstat.ru/indicator/57319",
            "resource_url": "https://fedstat.ru/indicator/57319",
            "metadata": {"match_mode": "exact"},
        },
        {
            "chunk_id": "world-bank:poverty",
            "card_id": "world_bank:poverty:metadata",
            "source_family": "world_bank",
            "embedding_text": "title: Poverty headcount ratio\nsource_family: World Bank",
            "provenance_url": "https://api.worldbank.org/v2/indicator/example",
            "resource_url": None,
            "metadata": {"match_mode": "lexical"},
        },
    ]

    results = LexicalBM25Retriever(documents).search("ВВП России GDP", limit=2)

    assert results
    assert results[0].card_id == "fedstat:57319:metadata"
    assert results[0].retrieval_mode == "lexical_bm25"
    assert results[0].source_family == "fedstat"
    assert results[0].score > 0
    assert any(tok in results[0].evidence_keywords for tok in ["gdp", "ввп"])
    assert results[0].metadata["provenance_url"]


def test_lexical_bm25_ignores_stopword_only_matches() -> None:
    from app.retrieval.hybrid_retrieval import LexicalBM25Retriever

    documents = [
        {
            "chunk_id": "fedstat:disease",
            "card_id": "fedstat:43820:metadata",
            "source_family": "fedstat",
            "embedding_text": (
                "title: Заболеваемость краснухой, на 100 тысяч населения\n"
                "source_family: FedStat\nnotes: источник по год за"
            ),
            "provenance_url": "https://fedstat.ru/indicator/43820",
            "resource_url": "https://fedstat.ru/indicator/43820",
            "metadata": {"match_mode": "lexical"},
        }
    ]

    results = LexicalBM25Retriever(documents).search(
        "Найди источник по инфляции России за 2023 год.",
        limit=5,
    )
    assert results == []


# ---------------------------------------------------------------------------
# KnowledgeGraphStore
# ---------------------------------------------------------------------------

def test_knowledge_graph_store_builds_nodes_and_edges() -> None:
    from app.retrieval.graph_store import KnowledgeGraphStore

    docs = [
        {
            "card_id": "fedstat:57319:metadata",
            "chunk_id": "fedstat:57319:chunk_001",
            "source_family": "fedstat",
            "embedding_text": (
                "title: Валовой внутренний продукт GDP\n"
                "source_family: FedStat\n"
                "dataset_id: 57319\n"
                "units: миллион рублей\n"
                "geography: Российская Федерация\n"
                "period_start: 2011\n"
                "period_end: 2024"
            ),
            "provenance_url": "https://fedstat.ru/indicator/57319",
            "metadata": {"availability": {"has_local_data": True}},
        }
    ]
    store = KnowledgeGraphStore(docs)
    assert store.node_count() > 0
    assert store.edge_count() > 0

    # Entity linking works
    nodes = store.entity_link(["fedstat:57319:metadata"])
    assert nodes
    assert nodes[0].node_type == "SourceCard"
    assert nodes[0].card_id == "fedstat:57319:metadata"


def test_knowledge_graph_store_subgraph_expansion() -> None:
    from app.retrieval.graph_store import KnowledgeGraphStore

    docs = [
        {
            "card_id": "fedstat:57319:metadata",
            "chunk_id": "fedstat:57319:chunk_001",
            "source_family": "fedstat",
            "embedding_text": (
                "title: ВВП\ndataset_id: 57319\nunits: млн руб\n"
                "geography: Россия\nperiod_start: 2011\nperiod_end: 2024"
            ),
            "provenance_url": "https://fedstat.ru/indicator/57319",
            "metadata": {},
        },
        {
            "card_id": "fedstat:12345:metadata",
            "chunk_id": "fedstat:12345:chunk_001",
            "source_family": "fedstat",
            "embedding_text": (
                "title: Инфляция\ndataset_id: 12345\nunits: %\n"
                "geography: Россия\nperiod_start: 2010\nperiod_end: 2024"
            ),
            "provenance_url": "https://fedstat.ru/indicator/12345",
            "metadata": {},
        },
    ]
    store = KnowledgeGraphStore(docs)
    nodes = store.entity_link(["fedstat:57319:metadata"])
    seed_ids = [n.node_id for n in nodes]
    subgraph = store.expand_subgraph(seed_ids, hops=2)

    # Subgraph must contain at least the seed node
    assert any(n.card_id == "fedstat:57319:metadata" for n in subgraph.nodes)
    # Edges must be present (at least Provider, Dataset, etc.)
    assert len(subgraph.edges) > 0
    # as_text should not crash
    text = subgraph.as_text()
    assert isinstance(text, str)


def test_subgraph_context_as_text_is_non_empty() -> None:
    from app.retrieval.graph_store import KnowledgeGraphStore

    docs = [
        {
            "card_id": "wb:NY.GDP.MKTP.CD:metadata",
            "chunk_id": "wb:NY.GDP.MKTP.CD:chunk_001",
            "source_family": "world_bank",
            "embedding_text": (
                "title: GDP current US dollars\n"
                "indicator_code: NY.GDP.MKTP.CD\n"
                "geography: World\n"
                "period_start: 1960\nperiod_end: 2023"
            ),
            "provenance_url": "https://api.worldbank.org/v2/indicator/NY.GDP.MKTP.CD",
            "metadata": {},
        }
    ]
    store = KnowledgeGraphStore(docs)
    nodes = store.entity_link(["wb:NY.GDP.MKTP.CD:metadata"])
    subgraph = store.expand_subgraph([n.node_id for n in nodes], hops=1)
    assert subgraph.as_text()


def test_knowledge_graph_store_graph_first_resolves_concept_aliases() -> None:
    from app.retrieval.graph_store import KnowledgeGraphStore

    docs = [
        {
            "card_id": "wb:NY.GDP.MKTP.CD:metadata",
            "chunk_id": "wb:NY.GDP.MKTP.CD:chunk_001",
            "source_family": "world_bank",
            "embedding_text": (
                "title: GDP current US dollars\n"
                "indicator_code: NY.GDP.MKTP.CD\n"
                "geography: Russia\n"
                "period_start: 1960\nperiod_end: 2024"
            ),
            "provenance_url": "https://api.worldbank.org/v2/indicator/NY.GDP.MKTP.CD",
            "metadata": {"availability": {"has_live_api": True}},
        },
        {
            "card_id": "wb:FP.CPI.TOTL.ZG:metadata",
            "chunk_id": "wb:FP.CPI.TOTL.ZG:chunk_001",
            "source_family": "world_bank",
            "embedding_text": (
                "title: Inflation consumer prices annual percent\n"
                "indicator_code: FP.CPI.TOTL.ZG\n"
                "geography: Russia\n"
                "period_start: 1960\nperiod_end: 2024"
            ),
            "provenance_url": "https://api.worldbank.org/v2/indicator/FP.CPI.TOTL.ZG",
            "metadata": {"availability": {"has_live_api": True}},
        },
    ]

    store = KnowledgeGraphStore(docs)
    results = store.graph_first_card_ids("gross domestic product Russia 2020", limit=5)

    assert results
    assert results[0] == "wb:NY.GDP.MKTP.CD:metadata"


# ---------------------------------------------------------------------------
# HybridRetriever integration (gated — no credentials)
# ---------------------------------------------------------------------------

def test_retrieval_spike_writes_eval_csv_with_graph_embedding_status(tmp_path: Path) -> None:
    from scripts.run_retrieval_spike import run_retrieval_evaluation

    corpus_artifact = tmp_path / "embedding-corpus.jsonl"
    docs = [
        {
            "chunk_id": "fedstat:gdp",
            "card_id": "fedstat:57319:metadata",
            "source_family": "fedstat",
            "embedding_text": "title: Валовой внутренний продукт GDP\nsource_family: FedStat\ndataset_id: 57319",
            "provenance_url": "https://fedstat.ru/indicator/57319",
            "resource_url": "https://fedstat.ru/indicator/57319",
            "metadata": {"match_mode": "exact"},
        },
        {
            "chunk_id": "world-bank:gdp",
            "card_id": "world_bank:NY.GDP.MKTP.CD:metadata",
            "source_family": "world_bank",
            "embedding_text": "title: GDP current US dollars\nsource_family: World Bank",
            "provenance_url": "https://api.worldbank.org/v2/indicator/NY.GDP.MKTP.CD",
            "resource_url": None,
            "metadata": {"match_mode": "lexical"},
        },
    ]
    corpus_artifact.write_text(
        "\n".join(json.dumps(d, ensure_ascii=False) for d in docs) + "\n",
        encoding="utf-8",
    )
    index_manifest = tmp_path / "embedding-index-manifest.json"
    index_manifest.write_text(
        json.dumps(
            {
                "status": "gated_skip",
                "dense_status": "gated_skip",
                "vector_store": "qdrant",
                "collection_name": "phase1_source_cards_test",
                "qdrant_mode": "local",
                "qdrant_path": str(tmp_path / "qdrant"),
                "corpus_artifact_path": str(corpus_artifact),
                "missing_env_vars": ["YANDEX_AI_STUDIO_API_KEY"],
            }
        ),
        encoding="utf-8",
    )
    goldens = tmp_path / "golden-cases.yaml"
    goldens.write_text(
        """
- id: GC-T01
  category: simple
  query_ru: "Какой ВВП России?"
  expected_sources:
    - "FedStat"
    - "World Bank"
  expected_rejection_or_no_data:
    - "Reject unrelated poverty candidates."
""",
        encoding="utf-8",
    )
    output = tmp_path / "retrieval-eval.csv"
    comparison = tmp_path / "retrieval-comparison.md"

    rows = run_retrieval_evaluation(
        goldens_path=goldens,
        index_manifest_path=index_manifest,
        output_path=output,
        comparison_path=comparison,
    )

    assert rows
    csv_rows = list(csv.DictReader(output.open()))
    assert csv_rows
    assert csv_rows[0]["case_id"] == "GC-T01"
    assert csv_rows[0]["retrieval_mode"]
    assert csv_rows[0]["dense_status"] == "gated_skip"
    assert csv_rows[0]["qdrant_collection"] == "phase1_source_cards_test"
    assert "rejection_reasons" in {k.lower() for k in csv_rows[0]}
