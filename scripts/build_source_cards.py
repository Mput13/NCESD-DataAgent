#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import csv
import io
import json
import sys
from pathlib import Path
from zipfile import ZipFile

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.source_card_builders import build_ckan, build_fedstat, build_world_bank


DEFAULT_FEDSTAT_ZIP = Path("/Users/a/Downloads/dumps/fedstatru/fedstatru.zip")
DEFAULT_WORLD_BANK_ZIP = Path("/Users/a/Downloads/dumps/wb/data.zip")
DEFAULT_CKAN_ENDPOINT = "https://repository.nsedc.ru/api/3/action/package_search"
DEFAULT_ARTIFACT = Path(".local/dataagent/phase1/source-cards.json")
DEFAULT_MANIFEST = Path(
    ".planning/phases/01-data-architecture-research/source-cards-manifest.json"
)
SOURCE_FAMILY_LABELS = {
    "fedstat": "FedStat",
    "world_bank": "World Bank",
    "ckan": "CKAN",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build deterministic source candidate cards from local metadata and bounded CKAN checks."
    )
    parser.add_argument("--fedstat-zip", type=Path, default=DEFAULT_FEDSTAT_ZIP)
    parser.add_argument("--world-bank-zip", type=Path, default=DEFAULT_WORLD_BANK_ZIP)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional per-source local metadata limit. Default: no limit.",
    )
    parser.add_argument("--fedstat-limit", type=int, default=None)
    parser.add_argument("--world-bank-limit", type=int, default=None)
    parser.add_argument("--ckan-query", default="57319")
    parser.add_argument("--ckan-rows", type=int, default=3)
    parser.add_argument("--ckan-all", action="store_true")
    parser.add_argument("--ckan-page-size", type=int, default=100)
    parser.add_argument("--ckan-resource-limit", type=int, default=3)
    parser.add_argument("--skip-ckan", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_ARTIFACT,
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
    )
    args = parser.parse_args()

    cards, source_notes = build_cards(args)

    payload = serialize_cards_payload(cards)
    write_json(args.output, payload)
    manifest = build_manifest(
        payload,
        artifact_path=args.output,
        manifest_path=args.manifest,
        source_notes=source_notes,
    )
    write_json(args.manifest, manifest)
    print(f"Wrote {len(cards)} source cards to {args.output}")
    print(f"Wrote source-card manifest to {args.manifest}")


def build_cards(args: argparse.Namespace) -> tuple[list[object], dict[str, object]]:
    cards = []
    source_notes: dict[str, object] = {
        "fedstat_zip": str(args.fedstat_zip),
        "world_bank_zip": str(args.world_bank_zip),
        "ckan_endpoint": DEFAULT_CKAN_ENDPOINT,
        "ckan_rows": args.ckan_rows,
        "ckan_resource_limit": args.ckan_resource_limit,
        "ckan_query": args.ckan_query,
    }
    if args.fedstat_zip.exists():
        fedstat_rows, fedstat_parquet, fedstat_clean = read_fedstat_metadata(args.fedstat_zip)
        source_notes["fedstat_metadata_rows"] = len(fedstat_rows)
        source_notes["fedstat_parquet_files"] = len(fedstat_parquet)
        source_notes["fedstat_clean_jsonl_files"] = len(fedstat_clean)
        cards.extend(
            build_fedstat(
                fedstat_rows,
                local_zip_path=str(args.fedstat_zip),
                parquet_paths=fedstat_parquet,
                clean_jsonl_paths=fedstat_clean,
                limit=args.fedstat_limit if args.fedstat_limit is not None else args.limit,
            )
        )

    if args.world_bank_zip.exists():
        indicators, countries, wb_parquet = read_world_bank_metadata(args.world_bank_zip)
        source_notes["world_bank_indicators"] = len(indicators)
        source_notes["world_bank_countries"] = len(countries)
        source_notes["world_bank_parquet_files"] = len(wb_parquet)
        cards.extend(
            build_world_bank(
                indicators,
                countries=countries,
                parquet_paths=wb_parquet,
                limit=args.world_bank_limit
                if args.world_bank_limit is not None
                else args.limit,
            )
        )

    if not args.skip_ckan:
        packages = (
            fetch_all_ckan_packages(
                query=args.ckan_query,
                page_size=args.ckan_page_size,
                endpoint=DEFAULT_CKAN_ENDPOINT,
            )
            if args.ckan_all
            else fetch_ckan_packages(
                query=args.ckan_query,
                rows=args.ckan_rows,
                endpoint=DEFAULT_CKAN_ENDPOINT,
            )
        )
        source_notes["ckan_packages_returned"] = len(packages)
        source_notes["ckan_all"] = args.ckan_all
        cards.extend(
            build_ckan(
                packages,
                query=args.ckan_query,
                api_endpoint=DEFAULT_CKAN_ENDPOINT,
                inspected_resource_limit=args.ckan_resource_limit,
                limit=args.ckan_rows,
            )
        )
    else:
        source_notes["ckan_skipped"] = True

    deduped_cards, duplicate_ids = deduplicate_cards(cards)
    source_notes["duplicate_source_card_ids"] = len(duplicate_ids)
    source_notes["duplicate_source_card_id_examples"] = duplicate_ids[:20]
    return deduped_cards, source_notes


def serialize_cards_payload(cards: list[object]) -> dict[str, object]:
    embedding_chunks = [card.to_embedding_chunk().model_dump(mode="json") for card in cards]
    return {
        "metadata_version": "source-card-v1",
        "embedding_provider_target": {
            "provider": "yandex_ai_studio",
            "document_model": "text-search-doc",
            "query_model": "text-search-query",
            "fallback_when_credentials_absent": "skip_dense_index_and_record_lexical_only",
        },
        "index_boundary": "source_card_metadata_only",
        "cards": [card.model_dump(mode="json") for card in cards],
        "embedding_chunks": embedding_chunks,
    }


def deduplicate_cards(cards: list[object]) -> tuple[list[object], list[str]]:
    """Keep one deterministic card per source/dataset/resource identity."""

    seen: set[str] = set()
    deduped: list[object] = []
    duplicates: list[str] = []
    for card in cards:
        card_id = getattr(card, "card_id")
        if card_id in seen:
            duplicates.append(card_id)
            continue
        seen.add(card_id)
        deduped.append(card)
    return deduped, duplicates


def build_manifest(
    payload: dict[str, object],
    *,
    artifact_path: Path,
    manifest_path: Path,
    source_notes: dict[str, object],
) -> dict[str, object]:
    data = stable_json_bytes(payload)
    cards = list(payload.get("cards", []))
    chunks = list(payload.get("embedding_chunks", []))
    families = sorted(
        {
            SOURCE_FAMILY_LABELS.get(str(card.get("source")), str(card.get("source")))
            for card in cards
            if isinstance(card, dict)
        }
    )
    return {
        "metadata_version": payload["metadata_version"],
        "artifact_path": str(artifact_path),
        "manifest_path": str(manifest_path),
        "card_count": len(cards),
        "embedding_chunk_count": len(chunks),
        "source_families": families,
        "content_hash": hashlib.sha256(data).hexdigest(),
        "card_hashes": {
            str(card["card_id"] if "card_id" in card else f"{card['source']}:{card['dataset_id']}:{card.get('resource_id') or 'metadata'}"): hashlib.sha256(
                stable_json_bytes(card)
            ).hexdigest()
            for card in cards
            if isinstance(card, dict)
        },
        "local_artifacts": [str(artifact_path)],
        "source_notes": source_notes,
    }


def stable_json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_fedstat_metadata(zip_path: Path) -> tuple[list[dict[str, str]], set[str], set[str]]:
    with ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        with archive.open("fedstatru/data/metdata.csv") as raw_file:
            text_file = io.TextIOWrapper(raw_file, encoding="utf-8-sig", newline="")
            rows = list(csv.DictReader(text_file))
    parquet = {name for name in names if name.startswith("fedstatru/data/parquet/") and name.endswith(".parquet")}
    clean = {
        name
        for name in names
        if name.startswith("fedstatru/data/clean_jsonl/") and name.endswith(".jsonl.gz")
    }
    return rows, parquet, clean


def read_world_bank_metadata(
    zip_path: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]], set[str]]:
    with ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        indicators = json.loads(archive.read("wb/indicators.json"))
        countries = json.loads(archive.read("wb/countries.json"))
    parquet = {name for name in names if name.startswith("wb/parquet/") and name.endswith(".parquet")}
    return indicators, countries, parquet


def fetch_ckan_packages(*, query: str, rows: int, endpoint: str) -> list[dict[str, object]]:
    response = requests.get(endpoint, params={"q": query, "rows": rows}, timeout=20)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError(f"CKAN package_search failed for query {query!r}")
    return list(payload.get("result", {}).get("results", []))


def fetch_all_ckan_packages(
    *, query: str, page_size: int, endpoint: str
) -> list[dict[str, object]]:
    packages: list[dict[str, object]] = []
    start = 0
    total: int | None = None
    while total is None or start < total:
        response = requests.get(
            endpoint,
            params={"q": query, "rows": page_size, "start": start},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise RuntimeError(f"CKAN package_search failed for query {query!r}")
        result = payload.get("result", {})
        total = int(result.get("count") or 0)
        batch = list(result.get("results", []))
        packages.extend(batch)
        if not batch:
            break
        start += len(batch)
    return packages


if __name__ == "__main__":
    main()
