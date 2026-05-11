from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_CATALOG = Path(".local/dataagent/phase1/source-catalog.sqlite")


def lookup_source_card(
    source_id: str | None,
    *,
    catalog_path: Path = DEFAULT_SOURCE_CATALOG,
) -> dict[str, Any] | None:
    """Load a full source-card JSON from the local SQLite catalog."""
    if not source_id or not catalog_path.exists():
        return None

    keys = _candidate_keys(source_id)
    if not keys:
        return None

    connection = sqlite3.connect(str(catalog_path))
    try:
        connection.row_factory = sqlite3.Row
        for key in keys:
            row = connection.execute(
                """
                select card_json
                from source_cards
                where card_id = ? or dataset_id = ? or resource_id = ?
                limit 1
                """,
                (key, key, key),
            ).fetchone()
            if row:
                card = json.loads(str(row["card_json"]))
                if isinstance(card, dict):
                    return card
    finally:
        connection.close()
    return None


def hydrate_source_card(source_card: dict[str, Any]) -> dict[str, Any]:
    """Merge a lightweight retrieval card with its full catalog card when possible."""
    lookup_key = (
        source_card.get("card_id")
        or source_card.get("dataset_id")
        or source_card.get("resource_id")
        or source_card.get("source_id")
    )
    full = lookup_source_card(str(lookup_key) if lookup_key else None)
    if not full:
        return source_card
    merged = dict(full)
    merged.update({key: value for key, value in source_card.items() if value not in (None, "")})
    return merged


def _candidate_keys(source_id: str) -> list[str]:
    raw = str(source_id).strip()
    keys = [raw]

    parts = raw.split(":")
    if len(parts) >= 2:
        keys.append(parts[1])
    if len(parts) >= 3:
        keys.append(parts[2])
    if len(parts) >= 4:
        keys.append(parts[3])

    deduped: list[str] = []
    for key in keys:
        if key and key not in deduped:
            deduped.append(key)
    return deduped
