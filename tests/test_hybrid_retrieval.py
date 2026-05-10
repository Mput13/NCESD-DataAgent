from __future__ import annotations

import csv
import json
from pathlib import Path


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
    assert any(token in results[0].evidence_keywords for token in ["gdp", "ввп"])
    assert results[0].metadata["provenance_url"]


def test_retrieval_spike_writes_eval_csv_with_dense_and_rerank_status(tmp_path: Path) -> None:
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
        "\n".join(json.dumps(doc, ensure_ascii=False) for doc in docs) + "\n",
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
    assert csv_rows[0]["rerank_status"] == "fallback_keyword_overlap"
    assert csv_rows[0]["qdrant_collection"] == "phase1_source_cards_test"
    assert "rejection_reasons" in {name.lower() for name in csv_rows[0].keys()}
    assert "bge-reranker-v2-m3" in comparison.read_text(encoding="utf-8")
