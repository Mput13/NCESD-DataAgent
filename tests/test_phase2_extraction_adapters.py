from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def _write_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    pq.write_table(pa.Table.from_pylist(rows), path)


def test_fedstat_wide_parquet_preview_and_extracts_canonical_rows(tmp_path: Path) -> None:
    from app.data.fedstat_adapter import (
        extract_fedstat_dataset,
        preview_fedstat_coverage,
    )

    parquet_path = tmp_path / "fedstat-wide.parquet"
    _write_parquet(
        parquet_path,
        [
            {
                "column00": "region",
                "column01": "indicator",
                "column02": "unit",
                "column03": "2019",
                "column04": "2020",
            },
            {
                "column00": "Russian Federation",
                "column01": "GDP",
                "column02": "billion rubles",
                "column03": "110",
                "column04": None,
            },
            {
                "column00": "Kazakhstan",
                "column01": "GDP",
                "column02": "billion rubles",
                "column03": "55",
                "column04": "60",
            },
        ],
    )
    source_card = {
        "dataset_id": "fedstat-gdp",
        "title": "FedStat GDP synthetic",
        "resource_id": str(parquet_path),
        "provenance_url": "https://fedstat.ru/indicator/fedstat-gdp",
        "frequency": "annual",
        "units": "billion rubles",
    }

    preview = preview_fedstat_coverage(source_card, filters={"indicator": "GDP"})
    dataset = extract_fedstat_dataset(
        source_card,
        filters={"indicator": "GDP", "geography": "Russian Federation", "periods": ["2019", "2020"]},
        output_dir=tmp_path / "out",
        artifact_id="fedstat-test",
    )

    assert preview.available_periods == ["2019", "2020"]
    assert preview.available_geographies == ["Kazakhstan", "Russian Federation"]
    assert preview.unit == "billion rubles"
    assert preview.frequency == "annual"
    assert preview.evidence["missing_values"] == 1
    assert dataset.columns == [
        "source",
        "dataset_id",
        "indicator_id",
        "indicator_name",
        "geo_id",
        "geo_name",
        "period",
        "period_type",
        "value",
        "unit",
        "dimensions",
        "source_url",
        "retrieved_at",
        "quality_flags",
    ]
    assert dataset.records[0]["value"] == 110
    assert dataset.records[0]["quality_flags"] == []
    assert dataset.records[1]["quality_flags"] == ["missing_value"]
    assert dataset.csv_path and Path(dataset.csv_path).exists()
