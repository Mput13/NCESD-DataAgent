from __future__ import annotations

import unittest


class SourceCardBuildersTest(unittest.TestCase):
    def test_fedstat_builder_flags_wide_parquet_normalization(self) -> None:
        from app.data.source_card_builders import build_fedstat

        cards = build_fedstat(
            [
                {
                    "code": "57319",
                    "name": "Gross domestic product in market prices",
                    "url": "https://fedstat.ru/indicator/57319",
                    "Единицы измерения": "million rubles",
                    "Периодичность и характеристика временного ряда": "quarterly",
                    "Длина временного ряда": "2011 - 2025",
                    "Признаки (перечень на базе классификаторов и справочников)": "OKATO; period",
                    "Методологические пояснения": "SNA 2008 methodology",
                    "rows": "31",
                }
            ],
            local_zip_path="/Users/a/Downloads/dumps/fedstatru/fedstatru.zip",
            parquet_paths={"fedstatru/data/parquet/57319.parquet"},
            clean_jsonl_paths=set(),
        )

        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual(card.source, "fedstat")
        self.assertEqual(card.builder_source, "fedstat_metdata_csv")
        self.assertEqual(card.dataset_id, "57319")
        self.assertEqual(card.resource_id, "fedstatru/data/parquet/57319.parquet")
        self.assertEqual(card.units, "million rubles")
        self.assertTrue(card.availability.has_local_metadata)
        self.assertTrue(card.availability.has_local_data)
        self.assertTrue(card.quality.wide_parquet)
        self.assertTrue(card.quality.requires_normalization)
        self.assertEqual(card.period_coverage.start_period, "2011")
        self.assertEqual(card.period_coverage.end_period, "2025")
        self.assertIn("OKATO", card.dimensions)

    def test_world_bank_builder_uses_indicator_and_country_metadata(self) -> None:
        from app.data.source_card_builders import build_world_bank

        cards = build_world_bank(
            [
                {
                    "id": "NY.GDP.MKTP.CD",
                    "name": "GDP (current US$)",
                    "unit": "",
                    "source": {"id": "2", "value": "World Development Indicators"},
                    "sourceNote": "GDP at purchaser prices.",
                    "topics": [{"value": "Economy & Growth"}],
                }
            ],
            countries=[
                {"id": "RUS", "name": "Russian Federation", "region": {"value": "Europe & Central Asia"}},
                {"id": "WLD", "name": "World", "region": {"value": "Aggregates"}},
            ],
            parquet_paths={"wb/parquet/NY.GDP.MKTP.CD.parquet"},
        )

        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual(card.source, "world_bank")
        self.assertEqual(card.builder_source, "world_bank_indicators_json")
        self.assertEqual(card.dataset_id, "NY.GDP.MKTP.CD")
        self.assertEqual(card.units, "current US$")
        self.assertTrue(card.availability.has_local_data)
        self.assertIn("Russian Federation", card.geography)
        self.assertIn("World", card.geography)
        self.assertEqual(card.metadata["country_count"], 2)
        self.assertEqual(card.metadata["aggregate_count"], 1)
        self.assertIn("Economy & Growth", card.metadata["topics"])

    def test_ckan_builder_records_bounded_resource_inspection(self) -> None:
        from app.data.source_card_builders import build_ckan

        cards = build_ckan(
            [
                {
                    "name": "emiss_57319",
                    "title": "Gross domestic product in market prices",
                    "organization": {"title": "Rosstat"},
                    "license_title": "Creative Commons Attribution",
                    "metadata_modified": "2026-02-12T00:00:00",
                    "resources": [
                        {
                            "id": "csv",
                            "name": "57319.csv.gz",
                            "format": "csv.gz",
                            "url": "https://example.invalid/57319.csv.gz",
                        },
                        {
                            "id": "parquet",
                            "name": "57319.parquet",
                            "format": "parquet",
                            "url": "https://example.invalid/57319.parquet",
                        },
                    ],
                }
            ],
            query="57319",
            api_endpoint="https://repository.nsedc.ru/api/3/action/package_search",
            inspected_resource_limit=1,
        )

        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual(card.source, "ckan")
        self.assertEqual(card.builder_source, "ckan_package_search")
        self.assertEqual(card.dataset_id, "emiss_57319")
        self.assertEqual(card.match_mode.value, "ckan_discovery")
        self.assertTrue(card.availability.has_live_api)
        self.assertTrue(card.availability.api_checked)
        self.assertTrue(card.availability.resource_inspection_truncated)
        self.assertEqual(card.metadata["resources_total"], 2)
        self.assertEqual(card.metadata["resources_inspected"], 1)
        self.assertEqual(card.metadata["resources"][0]["format"], "csv.gz")


if __name__ == "__main__":
    unittest.main()
