from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any


RUNTIME_DIR_ENV = "DATAAGENT_RUNTIME_DIR"
INDEX_MANIFEST_ENV = "DATAAGENT_INDEX_MANIFEST"
SOURCE_CATALOG_MANIFEST_ENV = "DATAAGENT_SOURCE_CATALOG_MANIFEST"
WORKFLOW_ARTIFACT_DIR_ENV = "DATAAGENT_WORKFLOW_ARTIFACT_DIR"

DEFAULT_RUNTIME_DIR = Path(".local/dataagent/runtime")
DEFAULT_WORKFLOW_ARTIFACT_DIR = Path(".local/dataagent/workflow-runs")
LEGACY_PHASE1_DIR = Path(".planning/phases/01-data-architecture-research")
LEGACY_PHASE2_WORKFLOW_RUNS = Path(".planning/phases/02-jury-mvp/workflow-runs")


def runtime_dir() -> Path:
    return Path(os.getenv(RUNTIME_DIR_ENV, str(DEFAULT_RUNTIME_DIR)))


def workflow_artifact_dir() -> Path:
    return Path(os.getenv(WORKFLOW_ARTIFACT_DIR_ENV, str(DEFAULT_WORKFLOW_ARTIFACT_DIR)))


def index_manifest_path() -> Path:
    return _configured_or_bootstrapped_path(
        env_name=INDEX_MANIFEST_ENV,
        filename="embedding-index-manifest.json",
    )


def source_catalog_manifest_path() -> Path:
    return _configured_or_bootstrapped_path(
        env_name=SOURCE_CATALOG_MANIFEST_ENV,
        filename="source-catalog-manifest.json",
    )


def _configured_or_bootstrapped_path(*, env_name: str, filename: str) -> Path:
    configured = os.getenv(env_name)
    if configured:
        return Path(configured)

    target = runtime_dir() / filename
    if target.exists():
        return target

    legacy = LEGACY_PHASE1_DIR / filename
    if legacy.exists():
        _bootstrap_legacy_manifest(legacy=legacy, target=target, filename=filename)
    return target


def _bootstrap_legacy_manifest(*, legacy: Path, target: Path, filename: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        payload = json.loads(legacy.read_text(encoding="utf-8"))
    except Exception:
        shutil.copyfile(legacy, target)
        return

    payload["manifest_path"] = str(target)
    if filename == "embedding-index-manifest.json":
        payload["runtime_manifest_bootstrapped_from"] = str(legacy)
        _copy_related_manifest(
            payload,
            key="corpus_manifest_path",
            legacy_filename="embedding-corpus-manifest.json",
        )
    elif filename == "source-catalog-manifest.json":
        payload["runtime_manifest_bootstrapped_from"] = str(legacy)
        _copy_related_manifest(
            payload,
            key="source_cards_manifest",
            legacy_filename="source-cards-manifest.json",
        )

    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _copy_related_manifest(
    payload: dict[str, Any],
    *,
    key: str,
    legacy_filename: str,
) -> None:
    raw = str(payload.get(key) or "")
    legacy_related = Path(raw) if raw else LEGACY_PHASE1_DIR / legacy_filename
    if not legacy_related.exists():
        return

    target_related = runtime_dir() / legacy_filename
    if not target_related.exists():
        try:
            related_payload = json.loads(legacy_related.read_text(encoding="utf-8"))
            related_payload["manifest_path"] = str(target_related)
            related_payload["runtime_manifest_bootstrapped_from"] = str(legacy_related)
            target_related.parent.mkdir(parents=True, exist_ok=True)
            target_related.write_text(
                json.dumps(related_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except Exception:
            target_related.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(legacy_related, target_related)
    payload[key] = str(target_related)
