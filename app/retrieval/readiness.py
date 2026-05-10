from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PHASE2_BASELINE_VECTOR_COUNT = 36321
LOCAL_QDRANT_WARNING_THRESHOLD = 20000


def assess_phase2_index_readiness(
    index_manifest_path: Path,
    corpus_manifest_path: Path,
    server_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Assess whether the Phase 2 dense index is safe for jury runtime use."""

    index_manifest = _read_json(index_manifest_path)
    corpus_manifest = _read_json(corpus_manifest_path)
    server_manifest = _read_json(server_manifest_path) if server_manifest_path else {}

    reasons: list[str] = []
    warnings: list[str] = []

    status = str(index_manifest.get("status") or "")
    dense_status = str(index_manifest.get("dense_status") or "")
    chunk_count = int(corpus_manifest.get("chunk_count") or index_manifest.get("chunk_count") or 0)
    vector_count = int(index_manifest.get("vector_count") or 0)
    corpus_hash = str(corpus_manifest.get("content_hash") or "")
    index_corpus_hash = str(index_manifest.get("corpus_hash") or "")
    qdrant_mode = str(index_manifest.get("qdrant_mode") or "")
    qdrant_collection = str(
        server_manifest.get("collection")
        or index_manifest.get("collection")
        or index_manifest.get("collection_name")
        or ""
    )
    qdrant_url = str(server_manifest.get("qdrant_url") or index_manifest.get("qdrant_url") or "")
    server_manifest_status = str(server_manifest.get("status") or "")
    reproduce_command = str(
        server_manifest.get("reproduce_command")
        or index_manifest.get("rebuild_command")
        or ""
    )

    if status != "ready":
        reasons.append("index_status_not_ready")
    if dense_status != "ready":
        reasons.append("dense_status_not_ready")
    if corpus_hash and index_corpus_hash and corpus_hash != index_corpus_hash:
        reasons.append("corpus_hash_mismatch")
    if chunk_count != PHASE2_BASELINE_VECTOR_COUNT:
        reasons.append("chunk_count_mismatch")
    if vector_count != chunk_count or vector_count != PHASE2_BASELINE_VECTOR_COUNT:
        reasons.append("server_vector_count_mismatch")
    if qdrant_mode == "local" and vector_count > LOCAL_QDRANT_WARNING_THRESHOLD:
        warnings.append("embedded_local_qdrant_not_recommended_for_phase2")
        reasons.append("server_qdrant_required_for_phase2")

    ready = not reasons
    return {
        "ready": ready,
        "status": status,
        "dense_status": dense_status,
        "chunk_count": chunk_count,
        "vector_count": vector_count,
        "qdrant_collection": qdrant_collection,
        "qdrant_url": qdrant_url,
        "qdrant_mode": qdrant_mode,
        "server_manifest_status": server_manifest_status,
        "reproduce_command": reproduce_command,
        "reasons": reasons,
        "warnings": warnings,
    }


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
