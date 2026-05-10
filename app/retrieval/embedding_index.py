from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

DEFAULT_QDRANT_PATH = Path(".local/qdrant")
DEFAULT_QDRANT_COLLECTION = "phase1_source_cards"
DEFAULT_DOC_MODEL = "emb://<folder_id>/text-search-doc/latest"
DEFAULT_QUERY_MODEL = "emb://<folder_id>/text-search-query/latest"
DEFAULT_DIMENSIONS = 256
YANDEX_EMBEDDING_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/textEmbedding"


@dataclass(frozen=True)
class EmbeddingIndexConfig:
    """Environment-backed configuration for Yandex embeddings and Qdrant."""

    provider: str
    document_model: str
    query_model: str
    dimensions: int
    qdrant_mode: str
    qdrant_path: str | None
    qdrant_url: str | None
    qdrant_api_key: str | None
    collection_name: str
    api_key: str | None

    @classmethod
    def from_env(cls) -> "EmbeddingIndexConfig":
        qdrant_url = os.getenv("QDRANT_URL")
        qdrant_mode = "remote" if qdrant_url else os.getenv("QDRANT_MODE", "local").lower()
        dimensions = int(os.getenv("YANDEX_EMBEDDING_DIMENSIONS", str(DEFAULT_DIMENSIONS)))
        return cls(
            provider="yandex_ai_studio",
            document_model=os.getenv("YANDEX_EMBEDDING_DOC_MODEL", DEFAULT_DOC_MODEL),
            query_model=os.getenv("YANDEX_EMBEDDING_QUERY_MODEL", DEFAULT_QUERY_MODEL),
            dimensions=dimensions,
            qdrant_mode=qdrant_mode,
            qdrant_path=None if qdrant_mode == "remote" else os.getenv("QDRANT_PATH", str(DEFAULT_QDRANT_PATH)),
            qdrant_url=qdrant_url,
            qdrant_api_key=os.getenv("QDRANT_API_KEY"),
            collection_name=os.getenv("QDRANT_COLLECTION", DEFAULT_QDRANT_COLLECTION),
            api_key=os.getenv("YANDEX_EMBEDDING_API_KEY") or os.getenv("YANDEX_AI_STUDIO_API_KEY"),
        )

    @property
    def missing_env_vars(self) -> list[str]:
        missing: list[str] = []
        if not self.api_key:
            missing.append("YANDEX_AI_STUDIO_API_KEY or YANDEX_EMBEDDING_API_KEY")
        if not self.document_model:
            missing.append("YANDEX_EMBEDDING_DOC_MODEL")
        if not self.query_model:
            missing.append("YANDEX_EMBEDDING_QUERY_MODEL")
        if not self.dimensions:
            missing.append("YANDEX_EMBEDDING_DIMENSIONS")
        if self.qdrant_mode == "remote" and not self.qdrant_url:
            missing.append("QDRANT_URL")
        return missing

    def qdrant_location(self) -> str:
        if self.qdrant_mode == "remote":
            return self.qdrant_url or ""
        return self.qdrant_path or str(DEFAULT_QDRANT_PATH)

    def manifest_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "provider": self.provider,
            "document_model": self.document_model,
            "query_model": self.query_model,
            "dimensions": self.dimensions,
            "vector_store": "qdrant",
            "qdrant_mode": self.qdrant_mode,
            "collection_name": self.collection_name,
        }
        if self.qdrant_mode == "remote":
            fields["qdrant_url"] = self.qdrant_url
        else:
            fields["qdrant_path"] = self.qdrant_path
        return fields


@dataclass(frozen=True)
class GatedSkipStatus:
    """Explicit status used when credentials gate vector population."""

    status: str
    dense_status: str
    missing_env_vars: list[str]
    reason: str

    @classmethod
    def from_config(cls, config: EmbeddingIndexConfig) -> "GatedSkipStatus":
        return cls(
            status="gated_skip",
            dense_status="gated_skip",
            missing_env_vars=config.missing_env_vars,
            reason="Yandex embedding credentials are unavailable; Qdrant collection abstraction is preserved.",
        )

    def model_dump(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "dense_status": self.dense_status,
            "missing_env_vars": self.missing_env_vars,
            "gate_reason": self.reason,
        }


class YandexEmbeddingProvider:
    """Yandex AI Studio text embedding client with document/query split."""

    def __init__(self, config: EmbeddingIndexConfig) -> None:
        self.config = config

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        return [self._embed(text, model_uri=self.config.document_model) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text, model_uri=self.config.query_model)

    def _embed(self, text: str, *, model_uri: str) -> list[float]:
        if not self.config.api_key:
            raise RuntimeError("Yandex embedding credentials are missing")
        response = requests.post(
            YANDEX_EMBEDDING_URL,
            headers={"Authorization": f"Api-Key {self.config.api_key}"},
            json={"modelUri": model_uri, "text": text},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        embedding = payload.get("embedding")
        if not isinstance(embedding, list):
            raise RuntimeError("Yandex embedding response did not contain an embedding list")
        vector = [float(value) for value in embedding]
        if len(vector) != self.config.dimensions:
            raise RuntimeError(
                f"Embedding dimensions mismatch: expected {self.config.dimensions}, got {len(vector)}"
            )
        return vector


class QdrantEmbeddingIndex:
    """Qdrant collection wrapper for source-card embedding documents."""

    def __init__(self, config: EmbeddingIndexConfig) -> None:
        self.config = config
        self.client = self._create_client(config)

    @staticmethod
    def _create_client(config: EmbeddingIndexConfig) -> QdrantClient:
        if config.qdrant_mode == "remote":
            return QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key)
        path = Path(config.qdrant_path or DEFAULT_QDRANT_PATH)
        path.mkdir(parents=True, exist_ok=True)
        return QdrantClient(path=str(path))

    def ensure_collection(self) -> None:
        existing = {collection.name for collection in self.client.get_collections().collections}
        if self.config.collection_name in existing:
            return
        self.client.create_collection(
            collection_name=self.config.collection_name,
            vectors_config=VectorParams(size=self.config.dimensions, distance=Distance.COSINE),
        )

    def upsert_documents(self, documents: list[dict[str, Any]], vectors: list[list[float]]) -> int:
        if len(documents) != len(vectors):
            raise ValueError("Document/vector count mismatch")
        points = [
            PointStruct(
                id=stable_point_id(str(document["chunk_id"])),
                vector=vector,
                payload=document,
            )
            for document, vector in zip(documents, vectors, strict=True)
        ]
        if points:
            self.client.upsert(collection_name=self.config.collection_name, points=points)
        return len(points)

    def search(self, query_vector: list[float], *, limit: int = 5) -> list[dict[str, Any]]:
        hits = self.client.search(
            collection_name=self.config.collection_name,
            query_vector=query_vector,
            limit=limit,
        )
        return [
            {
                "score": float(hit.score),
                "payload": hit.payload or {},
            }
            for hit in hits
        ]

    def collection_status(self) -> str:
        info = self.client.get_collection(collection_name=self.config.collection_name)
        return str(info.status)

    def count_vectors(self) -> int:
        result = self.client.count(collection_name=self.config.collection_name, exact=True)
        return int(result.count)


def stable_point_id(chunk_id: str) -> int:
    """Create deterministic unsigned 63-bit Qdrant point ids from chunk ids."""

    digest = hashlib.sha256(chunk_id.encode("utf-8")).hexdigest()[:16]
    return int(digest, 16) & ((1 << 63) - 1)


def cosine_distance(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Cosine distance requires equal vector lengths")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 1.0
    return 1.0 - (dot / (left_norm * right_norm))


def load_embedding_documents(corpus_manifest_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    corpus_manifest = json.loads(corpus_manifest_path.read_text(encoding="utf-8"))
    artifact_path = Path(corpus_manifest["artifact_path"])
    documents = [
        json.loads(line)
        for line in artifact_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    expected_count = int(corpus_manifest.get("chunk_count", 0))
    if expected_count != len(documents):
        raise RuntimeError(
            f"Embedding corpus chunk_count mismatch: manifest={expected_count}, jsonl={len(documents)}"
        )
    return corpus_manifest, documents
