from __future__ import annotations

import unittest


class SourceCardsContractTest(unittest.TestCase):
    def test_source_candidate_card_captures_required_metadata(self) -> None:
        from app.artifacts.source_cards import (
            AvailabilityFlags,
            CoverageHint,
            MatchMode,
            QualityFlags,
            SourceCandidateCard,
        )

        card = SourceCandidateCard(
            source="fedstat",
            builder_source="fedstat_metadata_csv",
            dataset_id="57319",
            resource_id="fedstatru/data/parquet/57319.parquet",
            title="Gross domestic product",
            match_mode=MatchMode.EXACT,
            units="million rubles",
            geography=["Russian Federation"],
            period_coverage=CoverageHint(start_period="2011", end_period="2024"),
            provenance_url="https://fedstat.ru/indicator/57319",
            local_paths=["/Users/a/Downloads/dumps/fedstatru/fedstatru.zip"],
            availability=AvailabilityFlags(has_local_data=True, has_live_api=False),
            quality=QualityFlags(requires_normalization=True),
            why_matched="Exact indicator code match.",
        )

        dumped = card.model_dump()
        self.assertEqual(dumped["source"], "fedstat")
        self.assertEqual(dumped["dataset_id"], "57319")
        self.assertEqual(dumped["resource_id"], "fedstatru/data/parquet/57319.parquet")
        self.assertEqual(dumped["match_mode"], "exact")
        self.assertEqual(dumped["units"], "million rubles")
        self.assertEqual(dumped["geography"], ["Russian Federation"])
        self.assertEqual(dumped["period_coverage"]["start_period"], "2011")
        self.assertEqual(dumped["builder_source"], "fedstat_metadata_csv")
        self.assertTrue(dumped["availability"]["has_local_data"])
        self.assertTrue(dumped["quality"]["requires_normalization"])

    def test_evidence_bundle_separates_candidates_rejections_and_intent(self) -> None:
        from app.artifacts.source_cards import (
            CoverageHint,
            EvidenceBundle,
            MatchMode,
            RejectedCandidate,
            SourceCandidateCard,
        )

        selected = SourceCandidateCard(
            source="world_bank",
            builder_source="world_bank_indicators_json",
            dataset_id="NY.GDP.MKTP.CD",
            resource_id="wb/data/parquet/NY.GDP.MKTP.CD.parquet",
            title="GDP (current US$)",
            match_mode=MatchMode.LEXICAL,
            units="current US$",
            geography=["Kazakhstan"],
            period_coverage=CoverageHint(start_period="1990", end_period="2024"),
            provenance_url="https://api.worldbank.org/v2/indicator/NY.GDP.MKTP.CD",
            why_matched="Lexical GDP title match.",
        )
        rejected = RejectedCandidate(
            candidate=selected,
            reason_code="coverage_gap",
            reason="Requested geography was unavailable in the candidate coverage.",
        )

        bundle = EvidenceBundle(
            coverage_intent="Compare GDP for Kazakhstan over the requested period.",
            selected_candidates=[selected],
            rejected_candidates=[rejected],
            rejection_reasons=["coverage_gap"],
        )

        dumped = bundle.model_dump()
        self.assertEqual(dumped["coverage_intent"], "Compare GDP for Kazakhstan over the requested period.")
        self.assertEqual(dumped["selected_candidates"][0]["source"], "world_bank")
        self.assertEqual(dumped["rejected_candidates"][0]["reason_code"], "coverage_gap")
        self.assertEqual(dumped["rejection_reasons"], ["coverage_gap"])
        self.assertNotIn("answer_text", dumped)
        self.assertNotIn("numeric_answer", dumped)

    def test_required_match_modes_are_available(self) -> None:
        from app.artifacts.source_cards import MatchMode

        self.assertEqual(MatchMode.EXACT.value, "exact")
        self.assertEqual(MatchMode.LEXICAL.value, "lexical")
        self.assertEqual(MatchMode.SEMANTIC.value, "semantic")
        self.assertEqual(MatchMode.PROXY.value, "proxy")
        self.assertEqual(MatchMode.CKAN_DISCOVERY.value, "ckan_discovery")
        self.assertEqual(MatchMode.METHODOLOGY_MATCH.value, "methodology_match")

    def test_source_card_builds_stable_embedding_chunk_contract(self) -> None:
        from app.artifacts.source_cards import CoverageHint, MatchMode, SourceCandidateCard

        card = SourceCandidateCard(
            source="ckan",
            builder_source="ckan_package_search",
            dataset_id="emiss_57319",
            resource_id="57319.parquet",
            title="Gross domestic product in market prices",
            match_mode=MatchMode.CKAN_DISCOVERY,
            units="million rubles",
            geography=["Russian Federation"],
            period_coverage=CoverageHint(start_period="2011", end_period="2024"),
            provenance_url="https://fedstat.ru/indicator/57319",
            dimensions=["OKATO", "period"],
            description="SNA 2008 methodology",
            why_matched="CKAN discovery by indicator code.",
        )

        chunk = card.to_embedding_chunk()
        dumped = chunk.model_dump()
        self.assertEqual(card.embedding.provider_target.provider, "yandex_ai_studio")
        self.assertEqual(card.embedding.provider_target.document_model, "text-search-doc")
        self.assertEqual(card.embedding.provider_target.query_model, "text-search-query")
        self.assertEqual(card.embedding.index_boundary, "source_card_metadata_only")
        self.assertEqual(dumped["card_id"], "ckan:emiss_57319:57319.parquet")
        self.assertEqual(dumped["source_family"], "ckan")
        self.assertEqual(dumped["metadata_version"], "source-card-v1")
        self.assertEqual(dumped["provenance_url"], "https://fedstat.ru/indicator/57319")
        self.assertRegex(dumped["chunk_id"], r"^ckan:emiss_57319:57319\\.parquet:source-card-v1:")
        self.assertRegex(dumped["content_hash"], r"^[0-9a-f]{64}$")
        self.assertIn("title: Gross domestic product in market prices", dumped["embedding_text"])
        self.assertIn("dataset_id: emiss_57319", dumped["embedding_text"])
        self.assertIn("dimensions: OKATO; period", dumped["embedding_text"])
        self.assertNotIn("numeric_answer", dumped["embedding_text"])


if __name__ == "__main__":
    unittest.main()
