#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.retrieval.embedding_index import load_embedding_documents, stable_point_id
from scripts.build_embedding_index import build_embedding_index

DEFAULT_INDEX_MANIFEST = Path(
    ".planning/phases/01-data-architecture-research/embedding-index-manifest.json"
)
DEFAULT_CORPUS_MANIFEST = Path(
    ".planning/phases/01-data-architecture-research/embedding-corpus-manifest.json"
)
DEFAULT_EMBEDDING_CACHE = Path(".local/dataagent/phase1/embedding-cache.jsonl")
DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_COLLECTION = "phase1_source_cards"
DEFAULT_SERVER_MANIFEST = Path(".planning/phases/02-jury-mvp/qdrant-server-manifest.json")
DEFAULT_COMPOSE_FILE = Path("docker-compose.qdrant.yml")

ClientFactory = Callable[..., QdrantClient]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Promote cached Phase 1 embeddings into shared Phase 2 Qdrant server mode."
    )
    parser.add_argument("--index-manifest", type=Path, default=DEFAULT_INDEX_MANIFEST)
    parser.add_argument("--corpus-manifest", type=Path, default=DEFAULT_CORPUS_MANIFEST)
    parser.add_argument("--embedding-cache", type=Path, default=DEFAULT_EMBEDDING_CACHE)
    parser.add_argument("--qdrant-url", default=DEFAULT_QDRANT_URL)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_SERVER_MANIFEST)
    parser.add_argument("--start-server", action="store_true")
    parser.add_argument("--allow-reembed", action="store_true")
    args = parser.parse_args()

    manifest = promote_qdrant_server(
        index_manifest_path=args.index_manifest,
        corpus_manifest_path=args.corpus_manifest,
        embedding_cache_path=args.embedding_cache,
        qdrant_url=args.qdrant_url,
        collection=args.collection,
        manifest_output=args.manifest_output,
        start_server=args.start_server,
        allow_reembed=args.allow_reembed,
    )
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))


def promote_qdrant_server(
    *,
    index_manifest_path: Path = DEFAULT_INDEX_MANIFEST,
    corpus_manifest_path: Path = DEFAULT_CORPUS_MANIFEST,
    embedding_cache_path: Path = DEFAULT_EMBEDDING_CACHE,
    qdrant_url: str = DEFAULT_QDRANT_URL,
    collection: str = DEFAULT_COLLECTION,
    manifest_output: Path = DEFAULT_SERVER_MANIFEST,
    start_server: bool = False,
    allow_reembed: bool = False,
    client_factory: ClientFactory = QdrantClient,
) -> dict[str, Any]:
    if start_server:
        start_qdrant_server(qdrant_url=qdrant_url)

    index_manifest = _read_json(index_manifest_path)
    corpus_manifest, documents = load_embedding_documents(corpus_manifest_path)
    corpus_hash = str(corpus_manifest.get("content_hash") or "")
    dimensions = int(index_manifest.get("dimensions") or 256)
    model_uri = str(
        index_manifest.get("document_model")
        or index_manifest.get("document_model_uri")
        or index_manifest.get("provider_model_uri")
        or ""
    )

    cache = _load_embedding_cache(
        embedding_cache_path,
        model_uri=model_uri,
        dimensions=dimensions,
    )
    missing_chunks = [
        str(document["chunk_id"])
        for document in documents
        if str(document["chunk_id"]) not in cache
    ]
    if missing_chunks and not allow_reembed:
        raise RuntimeError(
            "cache_incomplete_for_server_promotion: "
            f"{len(missing_chunks)} of {len(documents)} chunks are missing cached vectors"
        )
    if missing_chunks and allow_reembed:
        with _temporary_env(
            QDRANT_URL=qdrant_url,
            QDRANT_COLLECTION=collection,
        ):
            build_embedding_index(
                corpus_manifest_path=corpus_manifest_path,
                manifest_path=index_manifest_path,
                build_log_path=Path(
                    ".planning/phases/01-data-architecture-research/embedding-index-build.md"
                ),
                cache_path=embedding_cache_path,
            )
        cache = _load_embedding_cache(
            embedding_cache_path,
            model_uri=model_uri,
            dimensions=dimensions,
        )
        missing_chunks = [
            str(document["chunk_id"])
            for document in documents
            if str(document["chunk_id"]) not in cache
        ]
        if missing_chunks:
            raise RuntimeError(
                "cache_incomplete_for_server_promotion_after_reembed: "
                f"{len(missing_chunks)} chunks are still missing cached vectors"
            )

    client = client_factory(url=qdrant_url)
    existing = inspect_server_collection(client, collection=collection, corpus_hash=corpus_hash)
    expected_count = len(documents)
    if (
        existing["exists"]
        and existing["vector_count"] == expected_count
        and existing["corpus_hash"] == corpus_hash
    ):
        manifest = _server_manifest(
            status="ready",
            qdrant_url=qdrant_url,
            collection=collection,
            vector_count=existing["vector_count"],
            corpus_hash=corpus_hash,
            manifest_output=manifest_output,
            action="skipped_existing_collection",
        )
        _write_json(manifest_output, manifest)
        return manifest

    recreate_server_collection(client, collection=collection, dimensions=dimensions)
    points = [
        PointStruct(
            id=stable_point_id(str(document["chunk_id"])),
            vector=cache[str(document["chunk_id"])],
            payload={**document, "corpus_hash": corpus_hash},
        )
        for document in documents
    ]
    for batch in _chunks(points, 256):
        client.upsert(collection_name=collection, points=batch)
    vector_count = int(client.count(collection_name=collection, exact=True).count)
    if vector_count != expected_count:
        raise RuntimeError(
            f"server_vector_count_mismatch: expected {expected_count}, got {vector_count}"
        )
    manifest = _server_manifest(
        status="ready",
        qdrant_url=qdrant_url,
        collection=collection,
        vector_count=vector_count,
        corpus_hash=corpus_hash,
        manifest_output=manifest_output,
        action="recreated_from_embedding_cache",
    )
    _write_json(manifest_output, manifest)
    return manifest


def start_qdrant_server(*, qdrant_url: str, compose_file: Path = DEFAULT_COMPOSE_FILE) -> None:
    subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "up", "-d", "qdrant"],
        check=True,
    )
    client = QdrantClient(url=qdrant_url)
    last_error: Exception | None = None
    for _attempt in range(30):
        try:
            client.get_collections()
            return
        except Exception as exc:  # pragma: no cover - depends on Docker timing
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"qdrant_server_not_ready: {qdrant_url}") from last_error


def inspect_server_collection(
    client: QdrantClient,
    *,
    collection: str,
    corpus_hash: str,
) -> dict[str, Any]:
    collections = {item.name for item in client.get_collections().collections}
    if collection not in collections:
        return {"exists": False, "vector_count": 0, "corpus_hash": ""}
    vector_count = int(client.count(collection_name=collection, exact=True).count)
    payload_hash = ""
    if vector_count:
        points, _next_page = client.scroll(collection_name=collection, limit=1, with_payload=True)
        if points:
            payload_hash = str((points[0].payload or {}).get("corpus_hash") or "")
    return {
        "exists": True,
        "vector_count": vector_count,
        "corpus_hash": payload_hash,
        "corpus_hash_matches": payload_hash == corpus_hash,
    }


def recreate_server_collection(
    client: QdrantClient,
    *,
    collection: str,
    dimensions: int,
) -> None:
    collections = {item.name for item in client.get_collections().collections}
    if collection in collections:
        client.delete_collection(collection_name=collection)
    client.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=dimensions, distance=Distance.COSINE),
    )


def _load_embedding_cache(
    cache_path: Path,
    *,
    model_uri: str,
    dimensions: int,
) -> dict[str, list[float]]:
    vectors: dict[str, list[float]] = {}
    if not cache_path.exists():
        return vectors
    for line in cache_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if model_uri and record.get("model_uri") != model_uri:
            continue
        if int(record.get("dimensions") or 0) != dimensions:
            continue
        embedding = record.get("embedding")
        if isinstance(embedding, list) and len(embedding) == dimensions:
            vectors[str(record["chunk_id"])] = [float(value) for value in embedding]
    return vectors


def _server_manifest(
    *,
    status: str,
    qdrant_url: str,
    collection: str,
    vector_count: int,
    corpus_hash: str,
    manifest_output: Path,
    action: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "qdrant_url": qdrant_url,
        "collection": collection,
        "vector_count": vector_count,
        "corpus_hash": corpus_hash,
        "verified_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "promotion_action": action,
        "reproduce_command": (
            "python3 scripts/promote_qdrant_server.py --start-server "
            f"--manifest-output {manifest_output}"
        ),
    }


def _chunks(items: list[Any], size: int) -> Iterator[list[Any]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@contextmanager
def _temporary_env(**updates: str) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    main()
