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
