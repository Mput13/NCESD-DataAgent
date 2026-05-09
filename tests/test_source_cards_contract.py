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


if __name__ == "__main__":
    unittest.main()
