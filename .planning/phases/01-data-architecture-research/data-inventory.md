# Phase 1 Data Inventory

Updated: 2026-05-09T22:22:01Z

This inventory records deterministic source facts used by Plan 01-02. It does not contain numeric answer claims. Its purpose is to describe source metadata, local dump availability, bounded CKAN checks, and known gaps for later retrieval and extraction work.

## Local Dumps

| Source | Verified path | Metadata files used | Data files observed |
|---|---|---|---|
| FedStat / EMISS | `/Users/a/Downloads/dumps/fedstatru/fedstatru.zip` | `fedstatru/data/metdata.csv`, `fedstatru/data/metadata/{code}.json`, `fedstatru/data/metadata.jsonl`, `fedstatru/data/indicators.csv` | `fedstatru/data/parquet/{code}.parquet`, `fedstatru/data/clean_jsonl/{code}.jsonl.gz` |
| World Bank | `/Users/a/Downloads/dumps/wb/data.zip` | `wb/indicators.json`, `wb/countries.json`, `wb/sources.json`, `wb/metadata.json`, `wb/metadata.jsonl`, `wb/metadata/*.json` | `wb/parquet/{indicator_id}.parquet` |

## Verified Archive Counts

These counts were checked with Python `zipfile` against the local archives:

| Source | Archive entries | Parquet files | Metadata JSON files | Normalized JSONL files |
|---|---:|---:|---:|---:|
| FedStat / EMISS | 14756 | 7328 | 7330 | 84 |
| World Bank | 27719 | 27654 | 49 | 0 |

World Bank also has `wb/indicators.json`, `wb/countries.json`, `wb/sources.json`, `wb/metadata.json`, and `wb/metadata.jsonl` in the archive.

## FedStat Notes

- `metdata.csv` is the primary local metadata table because it expands indicator properties into columns and includes row/file size metadata.
- `metadata/{code}.json` keeps source passports with units, period hints, methodology, agency, and source formation fields.
- `metadata.jsonl` is present but incomplete and must not be treated as the full catalog.
- Most FedStat Parquet resources are wide tables with technical columns and first-row headers, so source cards flag wide-parquet normalization requirements when no matching `clean_jsonl` file is present.
- `clean_jsonl` exists for only a small subset and is useful as an extraction-friendly normalized layer.

## World Bank Notes

- `indicators.json` is the primary indicator catalog.
- `countries.json` includes countries, territories, and aggregates; cards preserve aggregate counts so later coverage logic can distinguish real countries from aggregate geographies.
- World Bank indicator `unit` metadata is often empty, so cards may derive a unit hint from the indicator title while keeping the original metadata trace.
- Parquet files follow the source pattern `wb/parquet/{indicator_id}.parquet`; coverage by country and year is verified later by deterministic extraction probes.

## CKAN Checks

CKAN is first-class for discovery and data access.

Bounded CKAN means:

- API root: `https://repository.nsedc.ru/api/3`
- Search endpoint: `https://repository.nsedc.ru/api/3/action/package_search`
- Package inspection endpoint: `https://repository.nsedc.ru/api/3/action/package_show`
- Default builder-script search bound: `rows=3`
- Default per-package resource inspection bound: `3` resources

The builder records whether resource inspection was skipped or truncated. CKAN results are treated as trusted NSED catalog metadata, not general web search.

Previously verified CKAN facts from `.planning/DATA_REPORT.md`:

- `package_search?rows=0` returned a catalog count of 53799 at analysis time.
- Query `q=57319&rows=1` found package `emiss_57319`.
- The `emiss_57319` package included resources in `csv.gz`, `parquet`, `xls.zip`, and `HTML` formats.

Because CKAN is live, counts and package metadata can change. Later scripts should cache only promoted metadata and preserve API timestamps/provenance.

## Known Gaps

- FedStat `metadata.jsonl` is incomplete and cannot satisfy SRCH-01 by itself.
- FedStat `indicators.csv` and actual metadata/parquet file presence do not fully agree; source-card generation must join catalog rows with file presence.
- FedStat wide Parquet normalization is required for most indicators before deterministic numeric extraction.
- World Bank unit metadata is sparse; unit display needs a deterministic normalization pass.
- World Bank indicators and actual parquet file presence do not fully agree; source cards should preserve missing-data availability flags.
- CKAN package search can return broad results, so later retrieval work needs ranking, rejection reasons, and bounded `package_show` resource checks.
