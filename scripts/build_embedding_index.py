#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build or gate the Phase 1 Qdrant embedding index for source-card chunks."
    )
    parser.add_argument("--corpus-manifest", type=Path, default=DEFAULT_CORPUS_MANIFEST)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_INDEX_MANIFEST)
    parser.add_argument("--build-log", type=Path, default=DEFAULT_BUILD_LOG)
    args = parser.parse_args()

    manifest = build_embedding_index(
        corpus_manifest_path=args.corpus_manifest,
        manifest_path=args.manifest,
        build_log_path=args.build_log,
    )
    print(f"{manifest['status']} {manifest['collection_name']}")


def build_embedding_index(
    *,
    corpus_manifest_path: Path,
    manifest_path: Path,
    build_log_path: Path,
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
    index.ensure_collection()
    provider = YandexEmbeddingProvider(config)
    vectors = provider.embed_documents([str(document["embedding_text"]) for document in documents])
    vector_count = index.upsert_documents(documents, vectors)
    manifest = {
        **base_manifest,
        "status": "ready",
        "dense_status": "ready",
        "missing_env_vars": [],
        "vector_count": vector_count,
        "qdrant_collection_status": "ready",
        "qdrant_reported_status": index.collection_status(),
    }
    _write_manifest_and_log(manifest, manifest_path=manifest_path, build_log_path=build_log_path)
    return manifest


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
            "PATH=\"$PWD/.local/bin:$PATH\" python scripts/build_embedding_index.py "
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
