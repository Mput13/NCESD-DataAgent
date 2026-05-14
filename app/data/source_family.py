"""Source family detection shared by workflow and extraction fallbacks."""
from __future__ import annotations

import re
from typing import Any


KNOWN_SOURCE_FAMILIES = frozenset({"fedstat", "world_bank", "ckan"})
_WB_UPPER_INDICATOR_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:[._][A-Z0-9]+)+$")


def detect_source_family_from_card(source_card: dict[str, Any]) -> str:
    """Infer a supported source family from explicit card metadata or IDs."""
    family = str(source_card.get("source_family") or "").lower()
    if family in KNOWN_SOURCE_FAMILIES:
        return family

    for key in ("source_id", "card_id", "dataset_id", "resource_id", "provenance_url"):
        detected = detect_source_family_from_id(source_card.get(key))
        if detected != "unknown":
            return detected
    return "unknown"


def detect_source_family_from_plan(plan: Any) -> str:
    """Infer source family from an ExtractionPlan-like object."""
    detected = detect_source_family_from_id(getattr(plan, "source_id", None))
    if detected != "unknown":
        return detected

    operations = " ".join(getattr(plan, "operations", []) or [])
    return detect_source_family_from_id(operations)


def detect_source_family_from_id(raw_id: Any) -> str:
    """Infer source family from a single source identifier string."""
    raw = str(raw_id or "").strip()
    if not raw:
        return "unknown"

    lower = raw.lower()
    if "fedstat" in lower or "emiss" in lower or "емисс" in lower:
        return "fedstat"
    if raw.isdigit():
        return "fedstat"
    if "ckan" in lower:
        return "ckan"
    if (
        "world_bank" in lower
        or "worldbank" in lower
        or lower.startswith("wb:")
        or "/wb/" in lower
        or "wb/parquet" in lower
    ):
        return "world_bank"
    if _WB_UPPER_INDICATOR_RE.fullmatch(raw):
        return "world_bank"
    return "unknown"
