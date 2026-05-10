# Extraction Probes

## FedStat wide Parquet probe

- DuckDB SQL-first: `.planning/phases/01-data-architecture-research/extraction-probe-artifacts/fedstat-wide-preview.sql`
- FedStat normalizer evidence: first-row header handling, dimension-column preservation, and wide year-column melt strategy are recorded in JSON evidence.
- PyArrow: metadata/read path before normalization.
- Polars: Polars not used in the Phase 1 probe because PyArrow + DuckDB are sufficient for bounded metadata/schema preview.
- Coverage status: `ok`
- Extraction status: `skipped_with_reason`

## World Bank parquet probe

- DuckDB SQL-first: `.planning/phases/01-data-architecture-research/extraction-probe-artifacts/world-bank-coverage-preview.sql`
- World Bank canonical long-format adapter evidence: indicator/country/period/value shape is recorded in JSON evidence.
- PyArrow: parquet metadata/read path remains available before DuckDB SQL.
- Polars: Polars not used; DuckDB can query the narrow long-format parquet directly.
- Coverage status: `ok`
- Extraction status: `skipped_with_reason`

## CKAN resource path probe

- DuckDB SQL-first: `.planning/phases/01-data-architecture-research/extraction-probe-artifacts/ckan-resource-preview.sql`
- Resource-level access path: package id `ckan_missing`, resource id `None`.
- PyArrow: used after a promoted parquet resource is downloaded or mapped locally.
- Polars: not used for the bounded CKAN suitability probe.
- Coverage status: `skipped_with_reason`
- Extraction status: `skipped_with_reason`
- Skip/gate reason: No promoted CKAN package id available.
