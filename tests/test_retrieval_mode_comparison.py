from __future__ import annotations

import json
from pathlib import Path


def test_retrieval_mode_comparison_scores_lexical_dense_and_hybrid(
    monkeypatch, tmp_path: Path
) -> None:
    import scripts.evaluate_retrieval_modes as mod

    corpus = tmp_path / "embedding-corpus.jsonl"
    docs = [
        {
            "chunk_id": "fedstat:context",
            "card_id": "fedstat:contextual_share",
            "source_family": "fedstat",
            "embedding_text": (
                "title: Доля расходов в валовом внутреннем продукте\n"
                "source_family: FedStat\n"
                "dataset_id: 12345"
            ),
            "provenance_url": "https://fedstat.ru/indicator/12345",
            "metadata": {"match_mode": "lexical"},
        },
        {
            "chunk_id": "world-bank:gdp",
            "card_id": "world_bank:NY.GDP.MKTP.CD:wb/parquet/NY.GDP.MKTP.CD.parquet",
            "source_family": "world_bank",
            "embedding_text": (
                "title: GDP current US dollars\n"
                "source_family: World Bank\n"
                "indicator_code: NY.GDP.MKTP.CD"
            ),
            "provenance_url": "https://api.worldbank.org/v2/indicator/NY.GDP.MKTP.CD",
            "metadata": {"match_mode": "dense"},
        },
    ]
    corpus.write_text(
        "\n".join(json.dumps(doc, ensure_ascii=False) for doc in docs) + "\n",
        encoding="utf-8",
    )
    index_manifest = tmp_path / "embedding-index-manifest.json"
    index_manifest.write_text(
        json.dumps(
            {
                "status": "ready",
                "dense_status": "ready",
                "collection_name": "test_collection",
                "qdrant_url": "http://localhost:6333",
                "corpus_artifact_path": str(corpus),
            }
        ),
        encoding="utf-8",
    )
    goldens = tmp_path / "goldens.yaml"
    goldens.write_text(
        """
- id: GC-T01
  query_ru: "Какой ВВП России?"
""",
        encoding="utf-8",
    )
    matrix = tmp_path / "matrix.json"
    matrix.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "GC-T01",
                        "source_family": "world_bank",
                        "source_id": "NY.GDP.MKTP.CD",
                        "card_id": "NY.GDP.MKTP.CD",
                        "expected_terminal_outcome": "passed",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    class FakeDenseRetriever:
        def __init__(self, index_manifest: dict) -> None:
            self.index_manifest = index_manifest

        @property
        def status(self) -> str:
            return "ready"

        def search(self, query: str, *, limit: int = 5):
            return [
                mod.RetrievalCandidate(
                    card_id="world_bank:NY.GDP.MKTP.CD:wb/parquet/NY.GDP.MKTP.CD.parquet",
                    chunk_id="world-bank:gdp",
                    source_family="world_bank",
                    title="GDP current US dollars",
                    retrieval_mode="dense_qdrant",
                    score=0.91,
                    relevance_score=0.91,
                    evidence_keywords=[],
                    metadata={
                        "canonical_ids": ["ny.gdp.mktp.cd"],
                        "provenance_url": "https://api.worldbank.org/v2/indicator/NY.GDP.MKTP.CD",
                        "embedding_text": "indicator_code: NY.GDP.MKTP.CD",
                    },
                )
            ][:limit]

        def fetch_by_card_ids(self, card_ids: list[str]):
            return []

    monkeypatch.setattr(mod, "DenseQdrantRetriever", FakeDenseRetriever)

    result = mod.evaluate_retrieval_modes(
        goldens_path=goldens,
        coverage_matrix_path=matrix,
        index_manifest_path=index_manifest,
        top_k=5,
    )

    assert result["metadata"]["dense_status"] == "ready"
    assert result["metadata"]["graph_status"] == "ready"
    modes = {row["mode"]: row for row in result["rows"]}
    assert set(modes) == {
        "dense_only",
        "lexical_only",
        "graph_first",
        "dense_plus_lexical",
        "hybrid_graph",
    }
    assert modes["dense_only"]["expected_id_hit_top1"] == "true"
    assert modes["dense_only"]["source_family_hit_top1"] == "true"
    assert modes["dense_plus_lexical"]["expected_id_hit_top5"] == "true"
    assert modes["hybrid_graph"]["expected_id_hit_top5"] == "true"
    assert "dense_only" in result["summary"]


def test_retrieval_mode_comparison_writes_all_outputs(tmp_path: Path, monkeypatch) -> None:
    import scripts.evaluate_retrieval_modes as mod

    result = {
        "metadata": {
            "case_count": 1,
            "top_k": 5,
            "dense_status": "query_embedding_gated",
            "graph_status": "query_embedding_gated",
            "index_status": "ready",
            "dense_index_status": "ready",
            "qdrant_collection": "test",
            "qdrant_url": "http://localhost:6333",
        },
        "summary": {
            "lexical_only": {
                "cases": 1,
                "source_family_hit_top1_rate": 1.0,
                "source_family_hit_top5_rate": 1.0,
                "expected_id_hit_top1_rate": 0.0,
                "expected_id_hit_top3_rate": 0.0,
                "expected_id_hit_top5_rate": 0.0,
            }
        },
        "rows": [
            {
                field: ""
                for field in mod.FIELDNAMES
            }
        ],
    }
    result["rows"][0].update(
        {
            "case_id": "GC-T01",
            "mode": "lexical_only",
            "top1_card_id": "card",
            "top1_title": "title",
            "top1_source_family": "fedstat",
            "source_family_hit_top1": "true",
            "expected_id_hit_top5": "false",
        }
    )

    output_csv = tmp_path / "out.csv"
    output_json = tmp_path / "out.json"
    output_md = tmp_path / "out.md"
    mod.write_outputs(
        result=result,
        output_csv=output_csv,
        output_json=output_json,
        output_md=output_md,
    )

    assert output_csv.exists()
    assert output_json.exists()
    assert output_md.exists()
    assert "Retrieval Mode Comparison" in output_md.read_text(encoding="utf-8")
