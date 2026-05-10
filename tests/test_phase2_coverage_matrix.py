"""Tests for the all-20 golden coverage matrix generator.

TDD RED: These tests assert required structure and completeness.
They fail before scripts/build_phase2_coverage_matrix.py exists.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SCRIPT = REPO_ROOT / "scripts" / "build_phase2_coverage_matrix.py"
GOLDENS = REPO_ROOT / ".planning" / "phases" / "01-data-architecture-research" / "golden-cases.yaml"
SOURCE_CATALOG_MANIFEST = (
    REPO_ROOT / ".planning" / "phases" / "01-data-architecture-research" / "source-catalog-manifest.json"
)
SOURCE_CARDS_MANIFEST = (
    REPO_ROOT / ".planning" / "phases" / "01-data-architecture-research" / "source-cards-manifest.json"
)
JSON_OUTPUT = REPO_ROOT / ".planning" / "phases" / "02-jury-mvp" / "golden-coverage-matrix.json"
MARKDOWN_OUTPUT = REPO_ROOT / ".planning" / "phases" / "02-jury-mvp" / "golden-coverage-matrix.md"

VALID_ADAPTERS = {"fedstat_adapter", "world_bank_adapter", "ckan_adapter"}
VALID_OUTCOMES = {"passed", "needs_clarification", "not_found"}
FORBIDDEN_PLACEHOLDER = {"todo", "unknown", "tbd", ""}


# ---------------------------------------------------------------------------
# Script existence
# ---------------------------------------------------------------------------


def test_script_exists():
    """The generator script must exist before we can run any other tests."""
    assert SCRIPT.exists(), f"Missing: {SCRIPT}"


# ---------------------------------------------------------------------------
# Module-level import / CLI smoke-test
# ---------------------------------------------------------------------------


def test_script_is_importable():
    """The script must not raise on import (syntax/module-level errors)."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"--help failed:\n{result.stderr}"


# ---------------------------------------------------------------------------
# JSON artifact structure
# ---------------------------------------------------------------------------


def _load_json() -> dict:
    assert JSON_OUTPUT.exists(), f"Missing JSON output: {JSON_OUTPUT}"
    return json.loads(JSON_OUTPUT.read_text(encoding="utf-8"))


def test_json_has_required_top_level_keys():
    data = _load_json()
    for key in ("total_cases", "generated_at", "cases", "unresolved_data_gaps"):
        assert key in data, f"Missing top-level key: {key!r}"


def test_json_total_cases_is_20():
    data = _load_json()
    assert data["total_cases"] == 20, f"Expected 20, got {data['total_cases']}"


def test_json_cases_count_equals_20():
    data = _load_json()
    assert len(data["cases"]) == 20, f"Expected 20 cases, got {len(data['cases'])}"


def test_json_case_ids_are_gc001_to_gc020():
    data = _load_json()
    ids = {c["case_id"] for c in data["cases"]}
    expected = {f"GC-{i:03d}" for i in range(1, 21)}
    missing = expected - ids
    extra = ids - expected
    assert not missing, f"Missing case IDs: {missing}"
    assert not extra, f"Unexpected case IDs: {extra}"


def test_json_each_case_has_required_fields():
    data = _load_json()
    required_fields = {
        "case_id",
        "source_family",
        "source_id",
        "card_id",
        "filters",
        "expected_terminal_outcome",
        "required_adapter",
        "artifact_expectations",
        "missing_data_evidence",
    }
    for case in data["cases"]:
        missing = required_fields - set(case.keys())
        assert not missing, f"Case {case.get('case_id')} missing fields: {missing}"


def test_json_no_gated_terminal_outcome():
    """expected_terminal_outcome must never be 'gated'."""
    data = _load_json()
    gated = [c["case_id"] for c in data["cases"] if c.get("expected_terminal_outcome") == "gated"]
    assert not gated, f"Cases with forbidden 'gated' outcome: {gated}"


def test_json_valid_terminal_outcomes():
    data = _load_json()
    for case in data["cases"]:
        outcome = case.get("expected_terminal_outcome", "")
        assert outcome in VALID_OUTCOMES, (
            f"Case {case['case_id']}: invalid expected_terminal_outcome={outcome!r}"
        )


def test_json_required_adapter_not_placeholder():
    """required_adapter must be a real adapter name, not a placeholder."""
    data = _load_json()
    for case in data["cases"]:
        adapter = str(case.get("required_adapter") or "").strip().lower()
        assert adapter not in FORBIDDEN_PLACEHOLDER, (
            f"Case {case['case_id']}: required_adapter is placeholder={adapter!r}"
        )


def test_json_required_adapter_is_known():
    """required_adapter must be one of the three known adapters (or a comma-separated combo)."""
    data = _load_json()
    for case in data["cases"]:
        raw = str(case.get("required_adapter") or "")
        adapters = [a.strip() for a in raw.split(",")]
        for adapter in adapters:
            assert adapter in VALID_ADAPTERS, (
                f"Case {case['case_id']}: unknown required_adapter={adapter!r}; "
                f"must be one of {VALID_ADAPTERS}"
            )


def test_json_not_found_cases_have_missing_data_evidence():
    """not_found and needs_clarification cases must have non-empty missing_data_evidence."""
    data = _load_json()
    for case in data["cases"]:
        outcome = case.get("expected_terminal_outcome", "")
        if outcome in ("not_found", "needs_clarification"):
            evidence = case.get("missing_data_evidence")
            assert evidence, (
                f"Case {case['case_id']} ({outcome}) must have non-empty missing_data_evidence"
            )


def test_json_passed_cases_have_artifact_expectations():
    """passed cases must specify non-empty artifact_expectations."""
    data = _load_json()
    for case in data["cases"]:
        outcome = case.get("expected_terminal_outcome", "")
        if outcome == "passed":
            expectations = case.get("artifact_expectations")
            assert expectations, (
                f"Case {case['case_id']} (passed) must have non-empty artifact_expectations"
            )


# ---------------------------------------------------------------------------
# Markdown artifact structure
# ---------------------------------------------------------------------------


def _load_md() -> str:
    assert MARKDOWN_OUTPUT.exists(), f"Missing markdown output: {MARKDOWN_OUTPUT}"
    return MARKDOWN_OUTPUT.read_text(encoding="utf-8")


def test_markdown_contains_gc001():
    assert "GC-001" in _load_md()


def test_markdown_contains_gc020():
    assert "GC-020" in _load_md()


def test_markdown_contains_all_case_ids():
    md = _load_md()
    missing = [f"GC-{i:03d}" for i in range(1, 21) if f"GC-{i:03d}" not in md]
    assert not missing, f"Markdown missing case IDs: {missing}"


def test_markdown_contains_source_family_column():
    md = _load_md()
    assert "source_family" in md.lower() or "source family" in md.lower(), (
        "Markdown must include a 'Source Family' column"
    )


def test_markdown_contains_expected_outcome_column():
    md = _load_md()
    assert "expected_terminal_outcome" in md.lower() or "terminal outcome" in md.lower(), (
        "Markdown must include an 'Expected Terminal Outcome' column"
    )
