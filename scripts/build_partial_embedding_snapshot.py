#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.retrieval.embedding_index import stable_point_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a safe partial Qdrant snapshot from embedding cache.")
    parser.add_argument("--corpus", type=Path, default=Path(".local/dataagent/phase1/embedding-corpus.jsonl"))
    parser.add_argument("--cache", type=Path, default=Path(".local/dataagent/phase1/embedding-cache.jsonl"))
    parser.add_argument("--qdrant-path", type=Path, default=Path(".local/qdrant-partial-dev"))
    parser.add_argument("--collection", default="phase1_source_cards_partial")
    parser.add_argument("--manifest", type=Path, default=Path(".planning/phases/01-data-architecture-research/partial-embedding-index-manifest.json"))
    args = parser.parse_args()

    manifest = build_snapshot(
        corpus_path=args.corpus,
        cache_path=args.cache,
        qdrant_path=args.qdrant_path,
        collection_name=args.collection,
        manifest_path=args.manifest,
    )
    print(json.dumps({"status": manifest["status"], "vector_count": manifest["vector_count"]}, sort_keys=True))


def build_snapshot(
    *,
    corpus_path: Path,
    cache_path: Path,
    qdrant_path: Path,
    collection_name: str,
    manifest_path: Path,
) -> dict[str, Any]:
    corpus = load_corpus(corpus_path)
    cache = load_cache(cache_path)
    documents: list[dict[str, Any]] = []
    vectors: list[list[float]] = []
    for chunk_id, document in corpus.items():
        vector = cache.get(chunk_id)
        if vector is None:
            continue
        documents.append(document)
        vectors.append(vector)

    qdrant_path.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(path=str(qdrant_path))
    existing = {collection.name for collection in client.get_collections().collections}
    if collection_name in existing:
        client.delete_collection(collection_name=collection_name)
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=256, distance=Distance.COSINE),
    )
    points = [
        PointStruct(id=stable_point_id(document["chunk_id"]), vector=vector, payload=document)
        for document, vector in zip(documents, vectors, strict=True)
    ]
    if points:
        client.upsert(collection_name=collection_name, points=points)
    families = sorted({document["source_family"] for document in documents})
    manifest = {
        "status": "partial_ready",
        "dense_status": "partial_ready",
        "vector_store": "qdrant",
        "qdrant_mode": "local",
        "qdrant_path": str(qdrant_path),
        "collection_name": collection_name,
        "vector_count": len(points),
        "total_corpus_count": len(corpus),
        "coverage_pct": round(len(points) / len(corpus) * 100, 2) if corpus else 0,
        "source_families_ready": families,
        "corpus_artifact_path": str(corpus_path),
        "embedding_cache_path": str(cache_path),
        "manifest_path": str(manifest_path),
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def load_corpus(path: Path) -> dict[str, dict[str, Any]]:
    return {
        document["chunk_id"]: document
        for document in (
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    }


def load_cache(path: Path) -> dict[str, list[float]]:
    if not path.exists():
        return {}
    vectors: dict[str, list[float]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        embedding = record.get("embedding")
        if isinstance(embedding, list) and len(embedding) == 256:
            vectors[str(record["chunk_id"])] = [float(value) for value in embedding]
    return vectors


if __name__ == "__main__":
    main()
