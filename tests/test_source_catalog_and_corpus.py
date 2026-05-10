from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


class SourceCatalogAndCorpusTest(unittest.TestCase):
    def test_source_catalog_materializes_cards_and_embedding_chunks(self) -> None:
        from app.artifacts.source_cards import CoverageHint, MatchMode, SourceCandidateCard
        from app.catalog.source_catalog import SourceCatalog

        card = SourceCandidateCard(
            source="FedStat",
            builder_source="fedstat_metdata_csv",
            dataset_id="57319",
            resource_id="fedstatru/data/parquet/57319.parquet",
            title="Gross domestic product",
            match_mode=MatchMode.EXACT,
            units="million rubles",
            geography=["Russian Federation"],
            period_coverage=CoverageHint(start_period="2011", end_period="2024"),
            provenance_url="https://fedstat.ru/indicator/57319",
            dimensions=["OKATO", "period"],
            why_matched="Exact code match.",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "source-catalog.sqlite"
            catalog = SourceCatalog(db_path)
            catalog.rebuild([card])

            self.assertEqual(catalog.count_source_cards(), 1)
            self.assertEqual(catalog.count_embedding_chunks(), 1)
            self.assertEqual(catalog.source_families(), ["FedStat"])
            self.assertTrue(catalog.queryable())

            with sqlite3.connect(db_path) as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "select name from sqlite_master where type = 'table'"
                    )
                }
            self.assertIn("source_cards", tables)
            self.assertIn("embedding_chunks", tables)
            self.assertIn("rejection_metadata", tables)

    def test_embedding_corpus_manifest_uses_ordered_jsonl_hash(self) -> None:
        from app.artifacts.source_cards import CoverageHint, MatchMode, SourceCandidateCard
        from scripts.build_embedding_corpus import build_embedding_corpus

        card = SourceCandidateCard(
            source="World Bank",
            builder_source="world_bank_indicators_json",
            dataset_id="NY.GDP.MKTP.CD",
            resource_id="wb/parquet/NY.GDP.MKTP.CD.parquet",
            title="GDP (current US$)",
            match_mode=MatchMode.LEXICAL,
            units="current US$",
            geography=["Kazakhstan"],
            period_coverage=CoverageHint(coverage_note="Verified during extraction."),
            provenance_url="https://api.worldbank.org/v2/indicator/NY.GDP.MKTP.CD",
            dimensions=["country", "date", "indicator"],
            why_matched="Lexical GDP title match.",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "embedding-corpus.jsonl"
            manifest_path = Path(tmpdir) / "embedding-corpus-manifest.json"
            manifest = build_embedding_corpus(
                [card.model_dump(mode="json")],
                artifact_path=artifact_path,
                manifest_path=manifest_path,
            )

            rows = [json.loads(line) for line in artifact_path.read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_family"], "World Bank")
            self.assertNotIn("numeric_answer", rows[0]["embedding_text"])
            self.assertEqual(manifest["chunk_count"], 1)
            self.assertEqual(manifest["source_families"], ["World Bank"])
            self.assertRegex(manifest["content_hash"], r"^[0-9a-f]{64}$")
            self.assertEqual(json.loads(manifest_path.read_text())["chunk_count"], 1)

    def test_embedding_text_is_bounded_for_provider_limits(self) -> None:
        from app.artifacts.source_cards import MatchMode, SourceCandidateCard

        card = SourceCandidateCard(
            source="fedstat",
            builder_source="fedstat_metdata_csv",
            dataset_id="LONG",
            resource_id="fedstatru/data/parquet/LONG.parquet",
            title="Long methodology source",
            match_mode=MatchMode.LEXICAL,
            geography=["Russian Federation"],
            description="Очень длинное методологическое описание. " * 600,
            why_matched="Full source-card metadata candidate.",
            metadata={"methodology": "Подробная методология. " * 600},
        )

        text = card.to_embedding_text()

        self.assertLessEqual(len(text), 6000)
        self.assertIn("truncated_for_embedding", text)


if __name__ == "__main__":
    unittest.main()
