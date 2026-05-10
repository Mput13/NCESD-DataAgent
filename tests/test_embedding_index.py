from __future__ import annotations

import json
from pathlib import Path


def _write_corpus(tmp_path: Path) -> Path:
    artifact_path = tmp_path / "embedding-corpus.jsonl"
    document = {
        "source_id": "57319",
        "card_id": "fedstat:57319:metadata",
        "chunk_id": "fedstat:57319:metadata:source-card-v1:abcdef1234567890",
        "source_family": "FedStat",
        "language": "mixed",
        "embedding_text": "title: Валовой внутренний продукт\nsource_family: FedStat",
        "content_hash": "a" * 64,
        "metadata_version": "source-card-v1",
        "input_format_version": "source-card-embedding-text-v1",
        "provenance_url": "https://fedstat.ru/indicator/57319",
        "resource_url": None,
        "builder_source": "unit_test",
        "metadata": {"match_mode": "exact"},
    }
    artifact_path.write_text(json.dumps(document, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest_path = tmp_path / "embedding-corpus-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "artifact_path": str(artifact_path),
                "manifest_path": str(manifest_path),
                "chunk_count": 1,
                "content_hash": "b" * 64,
                "metadata_version": "source-card-v1",
                "input_format_version": "source-card-embedding-text-v1",
                "provider": "yandex_ai_studio",
                "document_model": "text-search-doc",
                "query_model": "text-search-query",
                "local_artifacts": [str(artifact_path)],
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_yandex_embedding_config_uses_split_models(monkeypatch) -> None:
    from app.retrieval.embedding_index import EmbeddingIndexConfig

    monkeypatch.setenv(
        "YANDEX_EMBEDDING_DOC_MODEL",
        "emb://folder-id/text-search-doc/latest",
    )
    monkeypatch.setenv(
        "YANDEX_EMBEDDING_QUERY_MODEL",
        "emb://folder-id/text-search-query/latest",
    )
    monkeypatch.setenv("YANDEX_EMBEDDING_DIMENSIONS", "256")

    config = EmbeddingIndexConfig.from_env()

    assert config.document_model == "emb://folder-id/text-search-doc/latest"
    assert config.query_model == "emb://folder-id/text-search-query/latest"
    assert config.dimensions == 256
    assert config.collection_name


def test_build_embedding_index_writes_gated_manifest_with_qdrant_config(
    monkeypatch, tmp_path: Path
) -> None:
    from scripts.build_embedding_index import build_embedding_index

    corpus_manifest = _write_corpus(tmp_path)
    index_manifest = tmp_path / "embedding-index-manifest.json"
    build_log = tmp_path / "embedding-index-build.md"
    qdrant_path = tmp_path / "qdrant"

    monkeypatch.delenv("YANDEX_AI_STUDIO_API_KEY", raising=False)
    monkeypatch.delenv("YANDEX_EMBEDDING_API_KEY", raising=False)
    monkeypatch.setenv("QDRANT_MODE", "local")
    monkeypatch.setenv("QDRANT_PATH", str(qdrant_path))
    monkeypatch.setenv("QDRANT_COLLECTION", "phase1_source_cards_test")
    monkeypatch.setenv(
        "YANDEX_EMBEDDING_DOC_MODEL",
        "emb://folder-id/text-search-doc/latest",
    )
    monkeypatch.setenv(
        "YANDEX_EMBEDDING_QUERY_MODEL",
        "emb://folder-id/text-search-query/latest",
    )
    monkeypatch.setenv("YANDEX_EMBEDDING_DIMENSIONS", "256")

    manifest = build_embedding_index(
        corpus_manifest_path=corpus_manifest,
        manifest_path=index_manifest,
        build_log_path=build_log,
    )

    assert manifest["status"] == "gated_skip"
    assert manifest["dense_status"] == "gated_skip"
    assert manifest["vector_store"] == "qdrant"
    assert manifest["qdrant_mode"] == "local"
    assert manifest["qdrant_path"] == str(qdrant_path)
    assert manifest["collection_name"] == "phase1_source_cards_test"
    assert manifest["chunk_count"] == 1
    assert manifest["corpus_hash"] == "b" * 64
    assert manifest["metadata_version"] == "source-card-v1"
    assert manifest["document_model"].endswith("/text-search-doc/latest")
    assert manifest["query_model"].endswith("/text-search-query/latest")
    assert manifest["dimensions"] == 256
    assert "YANDEX" in ",".join(manifest["missing_env_vars"])
    assert "gated_skip" in build_log.read_text(encoding="utf-8")
    assert json.loads(index_manifest.read_text(encoding="utf-8"))["status"] == "gated_skip"

    second_manifest = build_embedding_index(
        corpus_manifest_path=corpus_manifest,
        manifest_path=index_manifest,
        build_log_path=build_log,
    )

    assert second_manifest["created_at"] == manifest["created_at"]
