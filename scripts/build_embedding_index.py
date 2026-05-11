#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.retrieval.embedding_index import (
    EmbeddingIndexConfig,
    GatedSkipStatus,
    QdrantEmbeddingIndex,
    YandexEmbeddingProvider,
    load_embedding_documents,
)

DEFAULT_CORPUS_MANIFEST = Path(
    ".planning/phases/01-data-architecture-research/embedding-corpus-manifest.json"
)
DEFAULT_INDEX_MANIFEST = Path(
    ".planning/phases/01-data-architecture-research/embedding-index-manifest.json"
)
DEFAULT_BUILD_LOG = Path(".planning/phases/01-data-architecture-research/embedding-index-build.md")
DEFAULT_CACHE = Path(".local/dataagent/phase1/embedding-cache.jsonl")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build or gate the Phase 1 Qdrant embedding index for source-card chunks."
    )
    parser.add_argument("--corpus-manifest", type=Path, default=DEFAULT_CORPUS_MANIFEST)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_INDEX_MANIFEST)
    parser.add_argument("--build-log", type=Path, default=DEFAULT_BUILD_LOG)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Concurrent Yandex embedding requests per batch.",
    )
    parser.add_argument(
        "--recreate-collection",
        action="store_true",
        help="Drop and recreate the Qdrant collection before upserting cached/new vectors.",
    )
    args = parser.parse_args()

    manifest = build_embedding_index(
        corpus_manifest_path=args.corpus_manifest,
        manifest_path=args.manifest,
        build_log_path=args.build_log,
        cache_path=args.cache,
        batch_size=args.batch_size,
        workers=args.workers,
        recreate_collection=args.recreate_collection,
    )
    print(f"{manifest['status']} {manifest['collection_name']}")


def build_embedding_index(
    *,
    corpus_manifest_path: Path,
    manifest_path: Path,
    build_log_path: Path,
    cache_path: Path = DEFAULT_CACHE,
    batch_size: int = 64,
    workers: int = 4,
    recreate_collection: bool = False,
) -> dict[str, Any]:
    config = EmbeddingIndexConfig.from_env()
    corpus_manifest, documents = load_embedding_documents(corpus_manifest_path)
    started_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if manifest_path.exists():
        previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        started_at = str(previous_manifest.get("created_at") or started_at)

    base_manifest = _base_manifest(
        config=config,
        corpus_manifest=corpus_manifest,
        corpus_manifest_path=corpus_manifest_path,
        documents=documents,
        manifest_path=manifest_path,
        build_log_path=build_log_path,
        started_at=started_at,
    )

    if config.missing_env_vars:
        manifest = {
            **base_manifest,
            **GatedSkipStatus.from_config(config).model_dump(),
            "qdrant_collection_status": "not_populated_credentials_missing",
            "vector_count": 0,
        }
        _write_manifest_and_log(manifest, manifest_path=manifest_path, build_log_path=build_log_path)
        return manifest

    index = QdrantEmbeddingIndex(config)
    if recreate_collection:
        index.recreate_collection()
    else:
        index.ensure_collection()
    provider = YandexEmbeddingProvider(config)
    cache = EmbeddingCache(
        cache_path,
        model_uri=config.document_model,
        dimensions=config.dimensions,
    )
    vector_count = 0
    cache_hits = 0
    cache_misses = 0
    batches = _chunks(documents, max(batch_size, 1))
    workers = max(workers, 1)
    for batch_index, batch in enumerate(batches, start=1):
        batch_vectors_by_chunk: dict[str, list[float]] = {}
        misses: list[dict[str, Any]] = []
        for document in batch:
            cached = cache.get(document)
            if cached is not None:
                cache_hits += 1
                batch_vectors_by_chunk[str(document["chunk_id"])] = cached
                continue
            misses.append(document)
        if misses:
            with ThreadPoolExecutor(max_workers=min(workers, len(misses))) as executor:
                futures = {
                    executor.submit(provider.embed_document, str(document["embedding_text"])): document
                    for document in misses
                }
                for future in as_completed(futures):
                    document = futures[future]
                    vector = future.result()
                    cache.put(document, vector)
                    cache_misses += 1
                    batch_vectors_by_chunk[str(document["chunk_id"])] = vector
        batch_vectors = [
            batch_vectors_by_chunk[str(document["chunk_id"])] for document in batch
        ]
        vector_count += index.upsert_documents(batch, batch_vectors)
        print(
            json.dumps(
                {
                    "batch": batch_index,
                    "batches": len(batches),
                    "vectors_upserted": vector_count,
                    "cache_hits": cache_hits,
                    "cache_misses": cache_misses,
                    "workers": workers,
                },
                sort_keys=True,
            ),
            flush=True,
        )
    manifest = {
        **base_manifest,
        "status": "ready",
        "dense_status": "ready",
        "missing_env_vars": [],
        "vector_count": vector_count,
        "qdrant_collection_status": "ready",
        "qdrant_reported_status": index.collection_status(),
        "embedding_cache_path": str(cache_path),
        "embedding_cache_hits": cache_hits,
        "embedding_cache_misses": cache_misses,
        "embedding_workers": workers,
    }
    _write_manifest_and_log(manifest, manifest_path=manifest_path, build_log_path=build_log_path)
    return manifest


class EmbeddingCache:
    """Append-only JSONL cache for resumable full-corpus embedding builds."""

    def __init__(self, path: Path, *, model_uri: str, dimensions: int) -> None:
        self.path = path
        self.model_uri = model_uri
        self.dimensions = dimensions
        self._vectors = self._load()

    def get(self, document: dict[str, Any]) -> list[float] | None:
        key = self._key(document)
        return self._vectors.get(key)

    def put(self, document: dict[str, Any], vector: list[float]) -> None:
        if len(vector) != self.dimensions:
            raise RuntimeError(
                f"Embedding cache dimensions mismatch: expected {self.dimensions}, got {len(vector)}"
            )
        key = self._key(document)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "key": key,
            "chunk_id": document["chunk_id"],
            "text_hash": document["text_hash"],
            "model_uri": self.model_uri,
            "dimensions": self.dimensions,
            "embedding": vector,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        self._vectors[key] = vector

    def _load(self) -> dict[str, list[float]]:
        vectors: dict[str, list[float]] = {}
        if not self.path.exists():
            return vectors
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("model_uri") != self.model_uri:
                continue
            if int(record.get("dimensions") or 0) != self.dimensions:
                continue
            embedding = record.get("embedding")
            if isinstance(embedding, list) and len(embedding) == self.dimensions:
                vectors[str(record["key"])] = [float(value) for value in embedding]
        return vectors

    def _key(self, document: dict[str, Any]) -> str:
        raw = {
            "chunk_id": document["chunk_id"],
            "text_hash": document.get("text_hash") or document["content_hash"],
            "model_uri": self.model_uri,
            "dimensions": self.dimensions,
        }
        return hashlib.sha256(
            json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def _chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _base_manifest(
    *,
    config: EmbeddingIndexConfig,
    corpus_manifest: dict[str, Any],
    corpus_manifest_path: Path,
    documents: list[dict[str, Any]],
    manifest_path: Path,
    build_log_path: Path,
    started_at: str,
) -> dict[str, Any]:
    local_artifacts = list(corpus_manifest.get("local_artifacts") or [])
    if config.qdrant_mode == "local" and config.qdrant_path:
        local_artifacts.append(config.qdrant_path)
    manifest: dict[str, Any] = {
        **config.manifest_fields(),
        "status": "pending",
        "dense_status": "pending",
        "provider_model_uri": config.document_model,
        "document_model_uri": config.document_model,
        "query_model_uri": config.query_model,
        "document_query_split": {
            "document": "YANDEX_EMBEDDING_DOC_MODEL",
            "query": "YANDEX_EMBEDDING_QUERY_MODEL",
        },
        "chunk_count": len(documents),
        "corpus_hash": corpus_manifest.get("content_hash"),
        "metadata_version": corpus_manifest.get("metadata_version"),
        "input_format_version": corpus_manifest.get("input_format_version"),
        "source_families": corpus_manifest.get("source_families", []),
        "corpus_manifest_path": str(corpus_manifest_path),
        "corpus_artifact_path": corpus_manifest.get("artifact_path"),
        "manifest_path": str(manifest_path),
        "build_log_path": str(build_log_path),
        "local_artifact_paths": sorted(set(local_artifacts)),
        "rebuild_command": (
            "PATH=\"$PWD/.local/bin:$PATH\" python3 scripts/build_embedding_index.py "
            f"--corpus-manifest {corpus_manifest_path} --manifest {manifest_path} --build-log {build_log_path}"
        ),
        "created_at": started_at,
    }
    return manifest


def _write_manifest_and_log(
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    build_log_path: Path,
) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    build_log_path.parent.mkdir(parents=True, exist_ok=True)
    build_log_path.write_text(_render_build_log(manifest), encoding="utf-8")


def _render_build_log(manifest: dict[str, Any]) -> str:
    missing = manifest.get("missing_env_vars") or []
    lines = [
        "# Embedding Index Build",
        "",
        f"- Status: `{manifest['status']}`",
        f"- Dense status: `{manifest['dense_status']}`",
        f"- Vector store: `qdrant_client` / Qdrant",
        f"- QDRANT_MODE: `{manifest['qdrant_mode']}`",
        f"- QDRANT_PATH: `{manifest.get('qdrant_path', '')}`",
        f"- QDRANT_URL: `{manifest.get('qdrant_url', '')}`",
        f"- QDRANT_COLLECTION / collection_name: `{manifest['collection_name']}`",
        f"- YANDEX_EMBEDDING_DOC_MODEL: `{manifest['document_model']}`",
        f"- YANDEX_EMBEDDING_QUERY_MODEL: `{manifest['query_model']}`",
        f"- YANDEX_EMBEDDING_DIMENSIONS: `{manifest['dimensions']}`",
        f"- Chunk count: `{manifest['chunk_count']}`",
        f"- Corpus hash: `{manifest['corpus_hash']}`",
        f"- Metadata version: `{manifest['metadata_version']}`",
        f"- Vector count: `{manifest.get('vector_count', 0)}`",
        "",
        "## Credential Gate",
        "",
    ]
    if manifest["status"] == "gated_skip":
        lines.extend(
            [
                "Vector population was gated_skip because embedding credentials were missing.",
                f"- Missing env vars: `{', '.join(missing)}`",
                "- Qdrant mode/path or URL and collection configuration were still materialized in the manifest.",
            ]
        )
    else:
        lines.append("Yandex embeddings ran and vectors were upserted into the Qdrant collection.")
    lines.extend(
        [
            "",
            "## Rebuild",
            "",
            f"```bash\n{manifest['rebuild_command']}\n```",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
