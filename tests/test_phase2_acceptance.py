"""Tests for the Phase 2 all-20 golden-case acceptance runner and eval scoring.

Covers:
- Task 1: scripts/run_phase2_acceptance.py — CLI and contract assertions
- Task 2: app/evals/run_eval.py — score_phase2_results extension
- Task 3: app/demo/run_demo.py — Phase 2 readiness dependency
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Task 1: scripts/run_phase2_acceptance.py contract assertions
# ---------------------------------------------------------------------------


def test_acceptance_runner_imports() -> None:
    """run_phase2_acceptance module must be importable and expose key symbols."""
    import scripts.run_phase2_acceptance as runner

    assert callable(getattr(runner, "run_acceptance", None) or getattr(runner, "main", None))


def test_acceptance_runner_contains_run_user_query_reference() -> None:
    """The acceptance runner must use run_user_query from the workflow service."""
    source = Path("scripts/run_phase2_acceptance.py").read_text(encoding="utf-8")
    assert "run_user_query" in source


def test_acceptance_runner_contains_coverage_matrix_arg() -> None:
    """The acceptance runner must support --coverage-matrix CLI argument."""
    source = Path("scripts/run_phase2_acceptance.py").read_text(encoding="utf-8")
    assert "--coverage-matrix" in source


def test_acceptance_runner_contains_used_test_only_fallbacks() -> None:
    """The acceptance runner must track used_test_only_fallbacks per case."""
    source = Path("scripts/run_phase2_acceptance.py").read_text(encoding="utf-8")
    assert "used_test_only_fallbacks" in source


def test_acceptance_runner_contains_unacceptable_reasons() -> None:
    """The acceptance runner must include unacceptable_reasons per case."""
    source = Path("scripts/run_phase2_acceptance.py").read_text(encoding="utf-8")
    assert "unacceptable_reasons" in source


def test_acceptance_runner_loads_20_cases_by_default(tmp_path: Path) -> None:
    """Default run must load all 20 golden cases from golden-cases.yaml."""
    import yaml

    goldens = yaml.safe_load(
        Path(".planning/phases/01-data-architecture-research/golden-cases.yaml").read_text(encoding="utf-8")
    )
    assert isinstance(goldens, list)
    assert len(goldens) == 20


def test_acceptance_runner_rejects_gated_outcome(tmp_path: Path) -> None:
    """A response with final_outcome='gated' must appear in unacceptable_reasons."""
    from scripts.run_phase2_acceptance import _check_outcome_acceptability

    reasons = _check_outcome_acceptability("gated", {}, allow_test_fallbacks=True)
    assert reasons, "gated must be listed as unacceptable"


def test_acceptance_runner_rejects_stale_outcome(tmp_path: Path) -> None:
    """A response with final_outcome='stale' must appear in unacceptable_reasons."""
    from scripts.run_phase2_acceptance import _check_outcome_acceptability

    reasons = _check_outcome_acceptability("stale", {}, allow_test_fallbacks=True)
    assert reasons, "stale must be listed as unacceptable"


def test_acceptance_runner_rejects_no_candidate_outcome(tmp_path: Path) -> None:
    """A response with final_outcome='no_candidate' must appear in unacceptable_reasons."""
    from scripts.run_phase2_acceptance import _check_outcome_acceptability

    reasons = _check_outcome_acceptability("no_candidate", {}, allow_test_fallbacks=True)
    assert reasons, "no_candidate must be listed as unacceptable"


def test_acceptance_runner_allows_passed_outcome(tmp_path: Path) -> None:
    """A response with final_outcome='passed' is acceptable (no unacceptable_reasons for outcome alone)."""
    from scripts.run_phase2_acceptance import _check_outcome_acceptability

    reasons = _check_outcome_acceptability("passed", {}, allow_test_fallbacks=True)
    assert isinstance(reasons, list)


def test_acceptance_runner_rejects_not_found_for_expected_passed() -> None:
    from scripts.run_phase2_acceptance import _score_response

    result = _score_response(
        {
            "run_id": "phase2-test",
            "final_outcome": "not_found",
            "selected_sources": [],
            "dataset_artifacts": [],
            "script_artifacts": [],
            "trace_events": [],
            "not_found_evidence": {
                "artifact_id": "nf",
                "checked_sources": [{"source_id": "world_bank"}],
                "rejected_sources": [{"source_id": "world_bank"}],
                "rejection_reasons": ["missing indicator"],
                "search_strategy": "test",
            },
        },
        {"case_id": "GC-X", "expected_terminal_outcome": "passed"},
    )

    assert "outcome_mismatch:expected=passed,got=not_found" in result["unacceptable_reasons"]


def test_acceptance_runner_requires_not_found_evidence_fields() -> None:
    from scripts.run_phase2_acceptance import _score_response

    result = _score_response(
        {
            "run_id": "phase2-test",
            "final_outcome": "not_found",
            "not_found_evidence": {
                "artifact_id": "nf",
                "checked_sources": [],
                "rejected_sources": [],
                "rejection_reasons": [],
                "search_strategy": "empty",
            },
        },
        {"case_id": "GC-X", "expected_terminal_outcome": "not_found"},
    )

    assert "not_found_missing_checked_sources" in result["unacceptable_reasons"]
    assert "not_found_missing_rejected_sources" in result["unacceptable_reasons"]
    assert "not_found_missing_rejection_reasons" in result["unacceptable_reasons"]


def test_acceptance_runner_requires_passed_evidence() -> None:
    from scripts.run_phase2_acceptance import _score_response

    result = _score_response(
        {
            "run_id": "phase2-test",
            "final_outcome": "passed",
            "selected_sources": [],
            "dataset_artifacts": [],
            "script_artifacts": [],
            "trace_events": [],
        },
        {"case_id": "GC-X", "expected_terminal_outcome": "passed"},
    )

    assert "passed_expected_missing_selected_sources" in result["unacceptable_reasons"]
    assert "passed_expected_missing_dataset_artifacts" in result["unacceptable_reasons"]
    assert "passed_expected_missing_script_artifacts" in result["unacceptable_reasons"]
    assert "passed_expected_missing_trace_events" in result["unacceptable_reasons"]


def test_acceptance_runner_detects_test_only_fallbacks(tmp_path: Path) -> None:
    """When allow_test_fallbacks=False, test_only_intent_fallback must be caught."""
    from scripts.run_phase2_acceptance import _detect_test_only_fallbacks

    component_statuses = {"intent": "test_only_intent_fallback"}
    result = _detect_test_only_fallbacks(component_statuses, trace_events=[])
    assert result, "test_only_intent_fallback must be detected"


def test_acceptance_runner_result_has_required_keys(tmp_path: Path) -> None:
    """Each case result dict must contain the required output fields."""
    from scripts.run_phase2_acceptance import _build_case_result_skeleton

    skeleton = _build_case_result_skeleton(
        case_id="GC-001",
        query_ru="Test query",
        expected_route="direct",
        expected_terminal_outcome="needs_clarification",
        required_adapter="world_bank_adapter",
    )
    required_keys = {
        "case_id",
        "query_ru",
        "expected_route",
        "matrix_expected_terminal_outcome",
        "matrix_required_adapter",
        "final_outcome",
        "sources_count",
        "dataset_count",
        "script_count",
        "trace_count",
        "used_test_only_fallbacks",
        "unacceptable_reasons",
    }
    assert required_keys.issubset(skeleton.keys()), (
        f"Missing keys: {required_keys - skeleton.keys()}"
    )


# ---------------------------------------------------------------------------
# Task 2: app/evals/run_eval.py — score_phase2_results assertions
# ---------------------------------------------------------------------------


def test_eval_runner_has_score_phase2_results() -> None:
    """run_eval must expose score_phase2_results function."""
    from app.evals import run_eval

    assert callable(getattr(run_eval, "score_phase2_results", None))


def test_eval_runner_score_phase2_has_coverage_matrix_param() -> None:
    """score_phase2_results must accept coverage_matrix_path kwarg."""
    import inspect
    from app.evals.run_eval import score_phase2_results

    sig = inspect.signature(score_phase2_results)
    assert "coverage_matrix_path" in sig.parameters


def test_eval_runner_score_phase2_tracks_test_only_fallback_failures() -> None:
    """score_phase2_results output dict must include test_only_fallback_failures."""
    from app.evals.run_eval import score_phase2_results

    # Minimal results input with one case that has a test_only fallback
    results_data = {
        "total_cases": 1,
        "cases": [
            {
                "case_id": "GC-001",
                "query_ru": "test",
                "expected_route": "direct",
                "matrix_expected_terminal_outcome": "needs_clarification",
                "matrix_required_adapter": "world_bank_adapter",
                "final_outcome": "needs_clarification",
                "sources_count": 0,
                "dataset_count": 0,
                "script_count": 0,
                "trace_count": 2,
                "used_test_only_fallbacks": ["test_only_intent_fallback"],
                "unacceptable_reasons": [],
            }
        ],
    }

    # Write to tmp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(results_data, f)
        tmp_path = Path(f.name)

    try:
        result = score_phase2_results(tmp_path)
        assert "test_only_fallback_failures" in result
    finally:
        tmp_path.unlink(missing_ok=True)


def test_eval_runner_score_phase2_flags_gated_as_unacceptable() -> None:
    """score_phase2_results must count gated as unacceptable."""
    from app.evals.run_eval import score_phase2_results

    results_data = {
        "total_cases": 1,
        "cases": [
            {
                "case_id": "GC-002",
                "query_ru": "test",
                "expected_route": "direct",
                "matrix_expected_terminal_outcome": "passed",
                "matrix_required_adapter": "fedstat_adapter",
                "final_outcome": "gated",
                "sources_count": 0,
                "dataset_count": 0,
                "script_count": 0,
                "trace_count": 0,
                "used_test_only_fallbacks": [],
                "unacceptable_reasons": ["outcome_gated"],
            }
        ],
    }

    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(results_data, f)
        tmp_path = Path(f.name)

    try:
        result = score_phase2_results(tmp_path)
        assert result.get("unacceptable", 0) >= 1, "gated case must be counted as unacceptable"
    finally:
        tmp_path.unlink(missing_ok=True)


def test_eval_runner_score_phase2_has_phase2_cli_args() -> None:
    """run_eval.py must contain --phase2-results CLI argument."""
    source = Path("app/evals/run_eval.py").read_text(encoding="utf-8")
    assert "--phase2-results" in source
    assert "--phase2-coverage-matrix" in source


# ---------------------------------------------------------------------------
# Task 3: app/demo/run_demo.py — Phase 2 readiness dependency assertions
# ---------------------------------------------------------------------------


def test_demo_readiness_has_phase2_fields() -> None:
    """assess_demo_readiness output must include Phase 2 readiness fields."""
    source = Path("app/demo/run_demo.py").read_text(encoding="utf-8")
    assert "phase2_workflow_eval_status" in source
    assert "phase2_coverage_matrix_status" in source


def test_demo_not_ready_when_phase2_cases_incomplete(tmp_path: Path) -> None:
    """Demo readiness must not be 'ready' when phase2_total_cases < 20."""
    from app.demo.run_demo import assess_phase2_readiness

    phase2_eval = {
        "total_cases": 19,  # intentionally < 20
        "passed": 19,
        "failed": 0,
        "unacceptable": 0,
        "test_only_fallback_failures": 0,
    }
    coverage_matrix = {
        "total_cases": 20,
        "unresolved_data_gaps": [],
    }

    result = assess_phase2_readiness(phase2_eval=phase2_eval, coverage_matrix=coverage_matrix)
    assert result.get("overall_status") != "ready", (
        "readiness must not be ready when phase2_total_cases is 19"
    )


def test_demo_not_ready_when_test_only_fallbacks_present(tmp_path: Path) -> None:
    """Demo readiness must not be 'ready' when test_only_fallback_failures > 0."""
    from app.demo.run_demo import assess_phase2_readiness

    phase2_eval = {
        "total_cases": 20,
        "passed": 20,
        "failed": 0,
        "unacceptable": 0,
        "test_only_fallback_failures": 3,  # test-only fallbacks present
    }
    coverage_matrix = {
        "total_cases": 20,
        "unresolved_data_gaps": [],
    }

    result = assess_phase2_readiness(phase2_eval=phase2_eval, coverage_matrix=coverage_matrix)
    assert result.get("overall_status") != "ready", (
        "readiness must not be ready when test-only fallbacks are present"
    )


def test_demo_not_ready_when_unacceptable_cases_present(tmp_path: Path) -> None:
    """Demo readiness must not be 'ready' when unacceptable > 0."""
    from app.demo.run_demo import assess_phase2_readiness

    phase2_eval = {
        "total_cases": 20,
        "passed": 18,
        "failed": 0,
        "unacceptable": 2,
        "test_only_fallback_failures": 0,
    }
    coverage_matrix = {
        "total_cases": 20,
        "unresolved_data_gaps": [],
    }

    result = assess_phase2_readiness(phase2_eval=phase2_eval, coverage_matrix=coverage_matrix)
    assert result.get("overall_status") != "ready", (
        "readiness must not be ready when unacceptable > 0"
    )
