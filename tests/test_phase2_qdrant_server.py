from __future__ import annotations

import json
from pathlib import Path


def test_qdrant_url_selects_server_mode_without_embedded_path(monkeypatch) -> None:
    from app.retrieval.embedding_index import EmbeddingIndexConfig

    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setenv("QDRANT_MODE", "local")
    monkeypatch.setenv("QDRANT_PATH", ".local/qdrant")
    monkeypatch.setenv("QDRANT_COLLECTION", "phase1_source_cards")

    config = EmbeddingIndexConfig.from_env()

    assert config.qdrant_mode == "remote"
    assert config.qdrant_url == "http://localhost:6333"
    assert config.qdrant_path is None
    assert config.collection_name == "phase1_source_cards"
    assert config.manifest_fields()["qdrant_url"] == "http://localhost:6333"
    assert "qdrant_path" not in config.manifest_fields()


def test_local_mode_large_phase2_index_warns_and_is_not_ready(tmp_path: Path) -> None:
    from app.retrieval.readiness import assess_phase2_index_readiness

    corpus_manifest = tmp_path / "embedding-corpus-manifest.json"
    corpus_manifest.write_text(
        json.dumps(
            {
                "chunk_count": 36321,
                "content_hash": "corpus-hash",
            }
        ),
        encoding="utf-8",
    )
    index_manifest = tmp_path / "embedding-index-manifest.json"
    index_manifest.write_text(
        json.dumps(
            {
                "status": "ready",
                "dense_status": "ready",
                "chunk_count": 36321,
                "vector_count": 36321,
                "corpus_hash": "corpus-hash",
                "qdrant_mode": "local",
                "qdrant_path": ".local/qdrant",
                "collection_name": "phase1_source_cards",
            }
        ),
        encoding="utf-8",
    )

    readiness = assess_phase2_index_readiness(index_manifest, corpus_manifest)

    assert readiness["ready"] is False
    assert "embedded_local_qdrant_not_recommended_for_phase2" in readiness["warnings"]


def test_promote_qdrant_server_fails_on_incomplete_cache_without_reembed(
    tmp_path: Path,
) -> None:
    import pytest
    from scripts.promote_qdrant_server import promote_qdrant_server

    corpus_path = tmp_path / "embedding-corpus.jsonl"
    documents = [
        {
            "chunk_id": "chunk-1",
            "text_hash": "text-1",
            "content_hash": "content-1",
            "embedding_text": "one",
        },
        {
            "chunk_id": "chunk-2",
            "text_hash": "text-2",
            "content_hash": "content-2",
            "embedding_text": "two",
        },
    ]
    corpus_path.write_text(
        "\n".join(json.dumps(document) for document in documents) + "\n",
        encoding="utf-8",
    )
    corpus_manifest = tmp_path / "embedding-corpus-manifest.json"
    corpus_manifest.write_text(
        json.dumps(
            {
                "artifact_path": str(corpus_path),
                "chunk_count": 2,
                "content_hash": "corpus-hash",
                "metadata_version": "source-card-v1",
            }
        ),
        encoding="utf-8",
    )
    index_manifest = tmp_path / "embedding-index-manifest.json"
    index_manifest.write_text(
        json.dumps(
            {
                "status": "ready",
                "dense_status": "ready",
                "document_model": "emb://folder/text-search-doc/latest",
                "dimensions": 2,
            }
        ),
        encoding="utf-8",
    )
    cache_path = tmp_path / "embedding-cache.jsonl"
    cache_path.write_text(
        json.dumps(
            {
                "chunk_id": "chunk-1",
                "model_uri": "emb://folder/text-search-doc/latest",
                "dimensions": 2,
                "embedding": [0.1, 0.2],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="cache_incomplete_for_server_promotion"):
        promote_qdrant_server(
            index_manifest_path=index_manifest,
            corpus_manifest_path=corpus_manifest,
            embedding_cache_path=cache_path,
            qdrant_url="http://localhost:6333",
            collection="phase1_source_cards",
            manifest_output=tmp_path / "qdrant-server-manifest.json",
            start_server=False,
            allow_reembed=False,
            client_factory=lambda *_args, **_kwargs: None,
        )
