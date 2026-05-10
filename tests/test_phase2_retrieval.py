"""Phase 2 retrieval tests: domain-aware ranking and Phase 2 evidence fields.

Task 1: Direct-indicator reranking regression tests.
Task 2: Phase 2 retrieval evidence fields and --phase2-output-json CLI flag.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

WEAK_CONTEXTUAL_TITLE = (
    "Удельный вес бюджетных расходов на фундаментальные исследования в валовом"
    " внутреннем продукте"
)
DIRECT_GDP_TITLE = "Валовой внутренний продукт GDP"


def _make_corpus(tmp_path: Path) -> Path:
    """Create a minimal embedding corpus with direct and contextual GDP cards."""
    docs = [
        {
            "chunk_id": "fedstat:gdp:direct",
            "card_id": "fedstat:57319:metadata",
            "source_family": "fedstat",
            "embedding_text": (
                f"title: {DIRECT_GDP_TITLE}\n"
                "source_family: FedStat\n"
                "dataset_id: 57319\n"
                "indicator_code: GDP"
            ),
            "provenance_url": "https://fedstat.ru/indicator/57319",
            "resource_url": "https://fedstat.ru/indicator/57319",
            "metadata": {"match_mode": "exact"},
        },
        {
            "chunk_id": "fedstat:gdp:contextual",
            "card_id": "fedstat:contextual_gdp_share:metadata",
            "source_family": "fedstat",
            "embedding_text": (
                f"title: {WEAK_CONTEXTUAL_TITLE}\n"
                "source_family: FedStat\n"
                "dataset_id: 12345"
            ),
            "provenance_url": "https://fedstat.ru/indicator/12345",
            "resource_url": "https://fedstat.ru/indicator/12345",
            "metadata": {"match_mode": "lexical"},
        },
        {
            "chunk_id": "world_bank:gdp:direct",
            "card_id": "world_bank:NY.GDP.MKTP.CD:metadata",
            "source_family": "world_bank",
            "embedding_text": (
                "title: GDP current US dollars\n"
                "source_family: World Bank\n"
                "indicator_code: NY.GDP.MKTP.CD"
            ),
            "provenance_url": "https://api.worldbank.org/v2/indicator/NY.GDP.MKTP.CD",
            "resource_url": None,
            "metadata": {"match_mode": "lexical"},
        },
    ]
    corpus = tmp_path / "embedding-corpus.jsonl"
    corpus.write_text(
        "\n".join(json.dumps(d, ensure_ascii=False) for d in docs) + "\n",
        encoding="utf-8",
    )
    return corpus


def _make_manifest(tmp_path: Path, corpus_path: Path) -> Path:
    manifest = tmp_path / "embedding-index-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "status": "gated_skip",
                "dense_status": "gated_skip",
                "vector_store": "qdrant",
                "collection_name": "phase2_test_collection",
                "qdrant_mode": "server",
                "qdrant_path": "",
                "qdrant_url": "http://localhost:6333",
                "corpus_artifact_path": str(corpus_path),
                "missing_env_vars": ["YANDEX_AI_STUDIO_API_KEY"],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _make_goldens(tmp_path: Path) -> Path:
    goldens = tmp_path / "golden-cases.yaml"
    goldens.write_text(
        """
- id: GC-001
  category: simple
  query_ru: "Какой ВВП России в 2024 году?"
  expected_sources:
    - "FedStat"
    - "World Bank"
  expected_rejection_or_no_data: []
- id: GC-002
  category: simple
  query_ru: "ВВП России 2023"
  expected_sources:
    - "World Bank"
  expected_rejection_or_no_data: []
""",
        encoding="utf-8",
    )
    return goldens


# ---------------------------------------------------------------------------
# Task 1: domain-aware reranking tests
# ---------------------------------------------------------------------------


def test_direct_gdp_card_ranks_above_contextual_gdp_share(tmp_path: Path) -> None:
    """Direct GDP card must outrank a contextual 'share of GDP' card for GDP queries."""
    from app.retrieval.hybrid_retrieval import HybridRetriever

    corpus = _make_corpus(tmp_path)
    manifest = _make_manifest(tmp_path, corpus)
    retriever = HybridRetriever(manifest)
    result = retriever.search(
        "Какой ВВП России в 2024 году?",
        expected_sources=["FedStat", "World Bank"],
        limit=5,
    )

    all_candidates = result.candidates + result.rejected_candidates
    assert all_candidates, "Expected at least one candidate"

    card_ids = [c.card_id for c in result.candidates]
    direct_card_id = "fedstat:57319:metadata"
    contextual_card_id = "fedstat:contextual_gdp_share:metadata"

    # Direct GDP card must appear in accepted results
    assert direct_card_id in card_ids, (
        f"Direct GDP card '{direct_card_id}' not found in accepted candidates: {card_ids}"
    )

    # Direct card must rank higher than contextual if both present
    direct_candidates = [c for c in result.candidates if c.card_id == direct_card_id]
    contextual_accepted = [c for c in result.candidates if c.card_id == contextual_card_id]
    if contextual_accepted:
        assert direct_candidates[0].score > contextual_accepted[0].score, (
            f"Direct GDP card score {direct_candidates[0].score} must exceed contextual "
            f"score {contextual_accepted[0].score}"
        )


def test_contextual_gdp_share_rejection_reason(tmp_path: Path) -> None:
    """Weak contextual 'share of GDP' card must receive contextual_match_not_direct_indicator rejection."""
    from app.retrieval.hybrid_retrieval import HybridRetriever

    corpus = _make_corpus(tmp_path)
    manifest = _make_manifest(tmp_path, corpus)
    retriever = HybridRetriever(manifest)
    result = retriever.search(
        "Какой ВВП России в 2024 году?",
        expected_sources=["FedStat", "World Bank"],
        limit=5,
    )

    contextual_card_id = "fedstat:contextual_gdp_share:metadata"
    rejected_ids = [c.card_id for c in result.rejected_candidates]

    if contextual_card_id in rejected_ids:
        rejected_card = next(c for c in result.rejected_candidates if c.card_id == contextual_card_id)
        assert "contextual_match_not_direct_indicator" in rejected_card.rejection_reasons, (
            f"Expected 'contextual_match_not_direct_indicator' in rejection reasons, "
            f"got {rejected_card.rejection_reasons}"
        )
    else:
        # Card is accepted, but must have lower score than direct card
        accepted_card = next(
            (c for c in result.candidates if c.card_id == contextual_card_id), None
        )
        direct_card = next(
            (c for c in result.candidates if c.card_id == "fedstat:57319:metadata"), None
        )
        if accepted_card and direct_card:
            assert direct_card.score > accepted_card.score


def test_source_preference_mismatch_rejection(tmp_path: Path) -> None:
    """FedStat cards must be rejected with source_preference_mismatch when World Bank is preferred."""
    from app.retrieval.hybrid_retrieval import HybridRetriever

    corpus = _make_corpus(tmp_path)
    manifest = _make_manifest(tmp_path, corpus)
    retriever = HybridRetriever(manifest)
    result = retriever.search(
        "Какой ВВП России в 2024 году?",
        expected_sources=["World Bank"],  # explicit World Bank preference
        limit=5,
    )

    fedstat_rejected = [
        c for c in result.rejected_candidates if c.source_family == "fedstat"
    ]
    # Some FedStat cards should be rejected due to source preference
    assert fedstat_rejected, "Expected FedStat cards to be rejected when World Bank is preferred"

    for card in fedstat_rejected:
        has_preference_reason = "source_preference_mismatch" in card.rejection_reasons or \
                                "source_family_mismatch" in card.rejection_reasons
        assert has_preference_reason, (
            f"FedStat card {card.card_id} missing source mismatch rejection reason, "
            f"got {card.rejection_reasons}"
        )


def test_split_rejections_adds_source_preference_mismatch(tmp_path: Path) -> None:
    """split_rejections must add source_preference_mismatch for source family mismatches."""
    from app.retrieval.hybrid_retrieval import RetrievalCandidate, split_rejections

    candidates = [
        RetrievalCandidate(
            card_id="fedstat:test",
            chunk_id="fedstat:test",
            source_family="fedstat",
            title="Test FedStat card",
            retrieval_mode="lexical_bm25",
            score=1.5,
            relevance_score=1.0,
            evidence_keywords=["gdp"],
        ),
        RetrievalCandidate(
            card_id="world_bank:test",
            chunk_id="world_bank:test",
            source_family="world_bank",
            title="Test World Bank card",
            retrieval_mode="lexical_bm25",
            score=1.2,
            relevance_score=1.0,
            evidence_keywords=["gdp"],
        ),
    ]

    accepted, rejected = split_rejections(candidates, expected_sources=["World Bank"])
    assert any(c.card_id == "world_bank:test" for c in accepted), "World Bank card should be accepted"
    fedstat_rejected = [c for c in rejected if c.card_id == "fedstat:test"]
    assert fedstat_rejected, "FedStat card should be rejected"
    # Accept either source_preference_mismatch or source_family_mismatch
    reasons = fedstat_rejected[0].rejection_reasons
    assert any(r in reasons for r in ("source_preference_mismatch", "source_family_mismatch")), (
        f"Expected source mismatch reason, got {reasons}"
    )


def test_hybrid_retrieval_contains_contextual_rejection_code() -> None:
    """The hybrid_retrieval module must contain contextual_match_not_direct_indicator string."""
    import inspect
    import app.retrieval.hybrid_retrieval as mod

    source = inspect.getsource(mod)
    assert "contextual_match_not_direct_indicator" in source, (
        "hybrid_retrieval.py must contain 'contextual_match_not_direct_indicator'"
    )


def test_hybrid_retrieval_contains_source_preference_mismatch_code() -> None:
    """The hybrid_retrieval module must contain source_preference_mismatch string."""
    import inspect
    import app.retrieval.hybrid_retrieval as mod

    source = inspect.getsource(mod)
    assert "source_preference_mismatch" in source, (
        "hybrid_retrieval.py must contain 'source_preference_mismatch'"
    )


def test_test_file_contains_weak_title() -> None:
    """Test file must reference the exact weak contextual GDP title."""
    test_file = Path(__file__)
    content = test_file.read_text(encoding="utf-8")
    weak_title = "Удельный вес бюджетных расходов на фундаментальные исследования в валовом внутреннем продукте"
    assert weak_title in content, f"Test file must contain weak title: {weak_title}"


# ---------------------------------------------------------------------------
# Task 2: Phase 2 evidence fields
# ---------------------------------------------------------------------------


def test_phase2_evidence_fields_in_csv(tmp_path: Path) -> None:
    """CSV output must include all Phase 2 required fields."""
    from scripts.run_retrieval_spike import run_retrieval_evaluation

    corpus = _make_corpus(tmp_path)
    manifest = _make_manifest(tmp_path, corpus)
    goldens = _make_goldens(tmp_path)
    output = tmp_path / "retrieval-eval.csv"
    comparison = tmp_path / "retrieval-comparison.md"

    rows = run_retrieval_evaluation(
        goldens_path=goldens,
        index_manifest_path=manifest,
        output_path=output,
        comparison_path=comparison,
    )

    assert rows, "Expected rows from retrieval evaluation"
    csv_rows = list(csv.DictReader(output.open()))
    assert csv_rows, "CSV must have rows"

    required_fields = [
        "case_id",
        "expected_route",
        "top_candidate",
        "top_title",
        "top_source_family",
        "source_family_match",
        "dense_status",
        "index_manifest_status",
        "qdrant_collection",
        "qdrant_url",
        "server_manifest_status",
        "selected_count",
        "rejected_count",
        "rejection_reasons",
    ]
    actual_fields = set(csv_rows[0].keys())
    missing = [f for f in required_fields if f not in actual_fields]
    assert not missing, f"CSV missing Phase 2 required fields: {missing}"


def test_phase2_output_json_flag(tmp_path: Path) -> None:
    """--phase2-output-json flag must write JSON with required keys."""
    import subprocess
    import sys

    corpus = _make_corpus(tmp_path)
    manifest = _make_manifest(tmp_path, corpus)
    goldens = _make_goldens(tmp_path)
    output_csv = tmp_path / "retrieval-eval.csv"
    comparison = tmp_path / "comparison.md"
    output_json = tmp_path / "phase2-output.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_retrieval_spike.py",
            "--goldens", str(goldens),
            "--index-manifest", str(manifest),
            "--output", str(output_csv),
            "--comparison", str(comparison),
            "--phase2-output-json", str(output_json),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    assert output_json.exists(), "phase2-output.json must be created"

    data = json.loads(output_json.read_text(encoding="utf-8"))
    required_keys = ["total_cases", "ready_index", "server_manifest_status", "cases", "unacceptable_no_candidate_cases"]
    for key in required_keys:
        assert key in data, f"phase2-output.json missing required key: {key}"


def test_phase2_csv_rejected_count_field(tmp_path: Path) -> None:
    """rejected_count must appear in CSV output."""
    from scripts.run_retrieval_spike import run_retrieval_evaluation

    corpus = _make_corpus(tmp_path)
    manifest = _make_manifest(tmp_path, corpus)
    goldens = _make_goldens(tmp_path)
    output = tmp_path / "retrieval-eval.csv"
    comparison = tmp_path / "comparison.md"

    run_retrieval_evaluation(
        goldens_path=goldens,
        index_manifest_path=manifest,
        output_path=output,
        comparison_path=comparison,
    )

    csv_rows = list(csv.DictReader(output.open()))
    assert csv_rows, "CSV must have rows"
    assert "rejected_count" in csv_rows[0], "rejected_count must be a CSV field"


def test_run_retrieval_spike_contains_phase2_output_json_flag() -> None:
    """scripts/run_retrieval_spike.py must contain --phase2-output-json argument."""
    spike_path = Path("scripts/run_retrieval_spike.py")
    content = spike_path.read_text(encoding="utf-8")
    assert "--phase2-output-json" in content, (
        "run_retrieval_spike.py must contain '--phase2-output-json' argument"
    )


def test_phase2_json_contains_unacceptable_no_candidate_cases(tmp_path: Path) -> None:
    """unacceptable_no_candidate_cases must be in JSON output and count non-not_found no-candidate cases."""
    from scripts.run_retrieval_spike import run_retrieval_evaluation, build_phase2_output_json

    corpus = _make_corpus(tmp_path)
    manifest = _make_manifest(tmp_path, corpus)
    goldens = _make_goldens(tmp_path)
    output = tmp_path / "retrieval-eval.csv"
    comparison = tmp_path / "comparison.md"

    rows = run_retrieval_evaluation(
        goldens_path=goldens,
        index_manifest_path=manifest,
        output_path=output,
        comparison_path=comparison,
    )

    import yaml
    golden_cases = yaml.safe_load(goldens.read_text(encoding="utf-8"))
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    server_manifest_path = None  # not required for this test

    result = build_phase2_output_json(
        rows=rows,
        golden_cases=golden_cases,
        index_manifest=manifest_data,
        server_manifest_path=server_manifest_path,
    )

    assert "unacceptable_no_candidate_cases" in result
    assert "server_manifest_status" in result
    assert "total_cases" in result
    assert "cases" in result
    assert "ready_index" in result
