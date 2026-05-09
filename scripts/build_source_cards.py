#!/usr/bin/env python3
from __future__ import annotations

import argparse
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build deterministic source candidate cards from local metadata and bounded CKAN checks."
    )
    parser.add_argument("--fedstat-zip", type=Path, default=DEFAULT_FEDSTAT_ZIP)
    parser.add_argument("--world-bank-zip", type=Path, default=DEFAULT_WORLD_BANK_ZIP)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--ckan-query", default="57319")
    parser.add_argument("--ckan-rows", type=int, default=3)
    parser.add_argument("--ckan-resource-limit", type=int, default=3)
    parser.add_argument("--skip-ckan", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".planning/phases/01-data-architecture-research/source-cards.json"),
    )
    args = parser.parse_args()

    cards = []
    if args.fedstat_zip.exists():
        fedstat_rows, fedstat_parquet, fedstat_clean = read_fedstat_metadata(args.fedstat_zip)
        cards.extend(
            build_fedstat(
                fedstat_rows,
                local_zip_path=str(args.fedstat_zip),
                parquet_paths=fedstat_parquet,
                clean_jsonl_paths=fedstat_clean,
                limit=args.limit,
            )
        )

    if args.world_bank_zip.exists():
        indicators, countries, wb_parquet = read_world_bank_metadata(args.world_bank_zip)
        cards.extend(
            build_world_bank(
                indicators,
                countries=countries,
                parquet_paths=wb_parquet,
                limit=args.limit,
            )
        )

    if not args.skip_ckan:
        packages = fetch_ckan_packages(
            query=args.ckan_query,
            rows=args.ckan_rows,
            endpoint=DEFAULT_CKAN_ENDPOINT,
        )
        cards.extend(
            build_ckan(
                packages,
                query=args.ckan_query,
                api_endpoint=DEFAULT_CKAN_ENDPOINT,
                inspected_resource_limit=args.ckan_resource_limit,
                limit=args.ckan_rows,
            )
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps([card.model_dump(mode="json") for card in cards], ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(cards)} source cards to {args.output}")


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


if __name__ == "__main__":
    main()
