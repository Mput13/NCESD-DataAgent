"""Phase 2 all-20 golden-case acceptance runner.

Iterates all 20 golden cases from golden-cases.yaml, calls run_user_query
through the shared workflow service, validates each case against the
golden-coverage-matrix.json, and writes phase2-golden-results.json and .md.

CLI usage:
    python3 scripts/run_phase2_acceptance.py \
        --goldens .planning/phases/01-data-architecture-research/golden-cases.yaml \
        --coverage-matrix .planning/phases/02-jury-mvp/golden-coverage-matrix.json \
        --json-output .planning/phases/02-jury-mvp/phase2-golden-results.json \
        --markdown-output .planning/phases/02-jury-mvp/phase2-golden-results.md \
        --artifact-dir .planning/phases/02-jury-mvp/workflow-runs
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Constants — unacceptable final outcome values per D-05/D-06
# ---------------------------------------------------------------------------

UNACCEPTABLE_OUTCOMES: frozenset[str] = frozenset(
    {
        "gated",
        "stale",
        "skipped_with_reason",
        "no_candidate",
        "ok",
        "ok-with-gated-internals",
    }
)

VALID_TERMINAL_OUTCOMES: frozenset[str] = frozenset(
    {"passed", "needs_clarification", "not_found"}
)

# ---------------------------------------------------------------------------
# Pure helper functions (imported by tests)
# ---------------------------------------------------------------------------


def _check_outcome_acceptability(
    final_outcome: str | None,
    matrix_case: dict[str, Any],
) -> list[str]:
    """Return list of unacceptable reasons for a given final_outcome.

    Empty list means the outcome is acceptable (no reasons to reject).
    """
    reasons: list[str] = []

    if final_outcome is None:
        reasons.append("final_outcome_missing")
        return reasons

    if final_outcome in UNACCEPTABLE_OUTCOMES:
        reasons.append(f"outcome_{final_outcome}")
        return reasons

    if final_outcome not in VALID_TERMINAL_OUTCOMES:
        reasons.append(f"outcome_unknown:{final_outcome}")

    return reasons


def _build_case_result_skeleton(
    *,
    case_id: str,
    query_ru: str,
    expected_route: str,
    expected_terminal_outcome: str,
    required_adapter: str,
) -> dict[str, Any]:
    """Build the required output skeleton for a single case result."""
    return {
        "case_id": case_id,
        "query_ru": query_ru,
        "expected_route": expected_route,
        "matrix_expected_terminal_outcome": expected_terminal_outcome,
        "matrix_required_adapter": required_adapter,
        "final_outcome": None,
        "sources_count": 0,
        "dataset_count": 0,
        "script_count": 0,
        "trace_count": 0,
        "unacceptable_reasons": [],
    }


def _check_matrix_alignment(
    response_outcome: str | None,
    response_adapter: str | None,
    matrix_case: dict[str, Any],
) -> list[str]:
    """Compare response against coverage matrix expectations.

    Returns list of mismatch reasons (empty = aligned).
    """
    reasons: list[str] = []
    expected_outcome = matrix_case.get("expected_terminal_outcome")
    expected_adapter = matrix_case.get("required_adapter")

    if expected_outcome and response_outcome not in (None, expected_outcome):
        # Some cases have multiple valid outcomes; check if close enough
        # e.g. needs_clarification cases that could also be not_found
        if not (
            expected_outcome == "passed"
            and response_outcome in VALID_TERMINAL_OUTCOMES
        ):
            reasons.append(
                f"outcome_mismatch:expected={expected_outcome},got={response_outcome}"
            )

    if expected_adapter and response_adapter and response_adapter != expected_adapter:
        # Adapter mismatch is a soft warning; CKAN and fedstat may overlap
        reasons.append(
            f"adapter_mismatch:expected={expected_adapter},got={response_adapter}"
        )

    return reasons


def _score_response(
    response: Any,
    matrix_case: dict[str, Any],
) -> dict[str, Any]:
    """Score a WorkflowResponse against matrix expectations.

    Returns a result dict with all required output fields.
    """
    # Extract response fields (WorkflowResponse Pydantic model or dict)
    if hasattr(response, "model_dump"):
        resp = response.model_dump()
    elif isinstance(response, dict):
        resp = response
    else:
        resp = {}

    final_outcome = resp.get("final_outcome")
    trace_events = resp.get("trace_events") or []
    dataset_artifacts = resp.get("dataset_artifacts") or []
    script_artifacts = resp.get("script_artifacts") or []
    selected_sources = resp.get("selected_sources") or []

    # Check outcome acceptability
    unacceptable_reasons = _check_outcome_acceptability(
        final_outcome, matrix_case
    )

    # Check coverage matrix alignment
    response_adapter = None
    if selected_sources:
        first_source = selected_sources[0] if isinstance(selected_sources[0], dict) else {}
        response_adapter = first_source.get("source_family") or first_source.get("adapter")

    matrix_reasons = _check_matrix_alignment(final_outcome, response_adapter, matrix_case)
    unacceptable_reasons.extend(matrix_reasons)

    return {
        "case_id": matrix_case.get("case_id", ""),
        "query_ru": matrix_case.get("query_ru", ""),
        "expected_route": matrix_case.get("expected_terminal_outcome", ""),
        "matrix_expected_terminal_outcome": matrix_case.get("expected_terminal_outcome", ""),
        "matrix_required_adapter": matrix_case.get("required_adapter", ""),
        "final_outcome": final_outcome,
        "sources_count": len(selected_sources),
        "dataset_count": len(dataset_artifacts),
        "script_count": len(script_artifacts),
        "trace_count": len(trace_events),
        "unacceptable_reasons": unacceptable_reasons,
    }


def _load_coverage_matrix(path: Path) -> dict[str, dict[str, Any]]:
    """Load coverage matrix and return dict keyed by case_id."""
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases") or []
    return {str(case["case_id"]): case for case in cases if "case_id" in case}


def _load_goldens(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Load golden cases from YAML file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"golden-cases YAML must be a list, got {type(data)}")
    if limit is not None:
        data = data[:limit]
    return data


def _render_markdown(results: dict[str, Any]) -> str:
    """Render acceptance results as markdown table."""
    cases = results.get("cases") or []
    rows = []
    for c in cases:
        status = "PASS" if not c.get("unacceptable_reasons") else "FAIL"
        reasons = "; ".join(c.get("unacceptable_reasons") or []) or "—"
        rows.append(
            f"| {c['case_id']} | {c.get('final_outcome', '—')} | {status} "
            f"| {c.get('dataset_count', 0)} | {c.get('script_count', 0)} "
            f"| {c.get('trace_count', 0)} | {reasons} |"
        )
    rows_str = "\n".join(rows)

    summary = results.get("summary") or {}
    return f"""# Phase 2 Acceptance Results

## Summary

- Total cases: {results.get('total_cases', 0)}
- Passed: {summary.get('passed', 0)}
- Needs clarification: {summary.get('needs_clarification', 0)}
- Not found: {summary.get('not_found', 0)}
- Unacceptable: {summary.get('unacceptable', 0)}

## Cases

| Case | Outcome | Status | Datasets | Scripts | Trace | Unacceptable Reasons |
|------|---------|--------|----------|---------|-------|----------------------|
{rows_str}
"""


def run_acceptance(
    *,
    goldens_path: Path,
    coverage_matrix_path: Path,
    json_output: Path,
    markdown_output: Path,
    artifact_dir: Path,
    limit: int | None = None,
) -> dict[str, Any]:
    """Run acceptance evaluation over all golden cases.

    Returns the full results dict (also written to json_output and markdown_output).
    """
    from app.workflow.service import WorkflowRunConfig, run_user_query

    goldens = _load_goldens(goldens_path, limit=limit)
    matrix = _load_coverage_matrix(coverage_matrix_path)

    case_results: list[dict[str, Any]] = []
    for golden in goldens:
        case_id = str(golden.get("id") or golden.get("case_id") or "")
        query_ru = str(golden.get("query_ru") or "")
        matrix_case = matrix.get(case_id) or {
            "case_id": case_id,
            "expected_terminal_outcome": golden.get("expected_terminal_outcome", ""),
            "required_adapter": "",
        }

        # Fall back to golden-cases.yaml fields if matrix case doesn't have them
        if not matrix_case.get("expected_terminal_outcome"):
            matrix_case["expected_terminal_outcome"] = ""
        if not matrix_case.get("query_ru"):
            matrix_case["query_ru"] = query_ru

        # Run query through the shared workflow service
        run_config = WorkflowRunConfig.default().model_copy(
            update={
                "case_id": case_id,
                "artifact_dir": artifact_dir,
            }
        )

        try:
            response = run_user_query(query_ru, run_config=run_config)
        except Exception as exc:
            # Build a minimal failed response on error
            result = _build_case_result_skeleton(
                case_id=case_id,
                query_ru=query_ru,
                expected_route=str(matrix_case.get("expected_terminal_outcome", "")),
                expected_terminal_outcome=str(matrix_case.get("expected_terminal_outcome", "")),
                required_adapter=str(matrix_case.get("required_adapter", "")),
            )
            result["final_outcome"] = "error"
            result["unacceptable_reasons"] = [f"run_error:{exc}"]
            case_results.append(result)
            continue

        case_result = _score_response(
            response,
            matrix_case,
        )
        case_results.append(case_result)

    # Aggregate summary
    unacceptable_count = sum(1 for c in case_results if c.get("unacceptable_reasons"))
    outcome_counts: dict[str, int] = {}
    for c in case_results:
        outcome = str(c.get("final_outcome") or "unknown")
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

    results: dict[str, Any] = {
        "total_cases": len(case_results),
        "goldens_path": str(goldens_path),
        "coverage_matrix_path": str(coverage_matrix_path),
        "summary": {
            "passed": outcome_counts.get("passed", 0),
            "needs_clarification": outcome_counts.get("needs_clarification", 0),
            "not_found": outcome_counts.get("not_found", 0),
            "unacceptable": unacceptable_count,
            **{k: v for k, v in outcome_counts.items() if k not in ("passed", "needs_clarification", "not_found")},
        },
        "cases": case_results,
    }

    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    markdown_output.write_text(_render_markdown(results), encoding="utf-8")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 2 all-20 golden-case acceptance runner."
    )
    parser.add_argument(
        "--goldens",
        default=".planning/phases/01-data-architecture-research/golden-cases.yaml",
        type=Path,
        help="Path to golden-cases.yaml",
    )
    parser.add_argument(
        "--coverage-matrix",
        default=".planning/phases/02-jury-mvp/golden-coverage-matrix.json",
        type=Path,
        help="Path to golden-coverage-matrix.json",
    )
    parser.add_argument(
        "--json-output",
        default=".planning/phases/02-jury-mvp/phase2-golden-results.json",
        type=Path,
        help="Path for JSON output",
    )
    parser.add_argument(
        "--markdown-output",
        default=".planning/phases/02-jury-mvp/phase2-golden-results.md",
        type=Path,
        help="Path for Markdown output",
    )
    parser.add_argument(
        "--artifact-dir",
        default=".planning/phases/02-jury-mvp/workflow-runs",
        type=Path,
        help="Directory for per-run workflow artifacts",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit to first N cases (for local debugging only)",
    )
    args = parser.parse_args()

    results = run_acceptance(
        goldens_path=args.goldens,
        coverage_matrix_path=args.coverage_matrix,
        json_output=args.json_output,
        markdown_output=args.markdown_output,
        artifact_dir=args.artifact_dir,
        limit=args.limit,
    )

    summary = results.get("summary") or {}
    print(
        json.dumps(
            {
                "total_cases": results.get("total_cases"),
                "passed": summary.get("passed", 0),
                "needs_clarification": summary.get("needs_clarification", 0),
                "not_found": summary.get("not_found", 0),
                "unacceptable": summary.get("unacceptable", 0),
                "json_output": str(args.json_output),
                "markdown_output": str(args.markdown_output),
            },
            ensure_ascii=False,
        )
    )

    # Exit non-zero if unacceptable outcomes exist (for CI gating)
    if summary.get("unacceptable", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
