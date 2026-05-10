"""Phase 2 workflow graph CLI.

Usage:
    python -m app.workflow.run_graph --query "ВВП России 2024" --json-output result.json
    python -m app.workflow.run_graph --case-index 0 --goldens path/to/cases.yaml --json-output result.json

Delegates to run_user_query_to_pending_finalization from service.py.
Writes Phase2State as JSON with status="finalization_pending".

Plan 02-06 will change this CLI to emit a final WorkflowResponse once
critic, visualization, and narrator nodes are wired.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.workflow.service import WorkflowRunConfig, run_user_query_to_pending_finalization


def _load_golden_case(goldens_path: Path, case_index: int) -> dict[str, Any]:
    """Load a golden case by index from a YAML file."""
    try:
        import yaml
        cases = yaml.safe_load(goldens_path.read_text(encoding="utf-8"))
        if not isinstance(cases, list) or not cases:
            raise ValueError(f"No golden cases in {goldens_path}")
        if case_index >= len(cases):
            raise IndexError(
                f"Case index {case_index} out of range (0..{len(cases)-1}) in {goldens_path}"
            )
        return cases[case_index]
    except ImportError:
        # yaml not available - try JSON
        cases = json.loads(goldens_path.read_text(encoding="utf-8"))
        return cases[case_index]


def _load_matrix_hint(case_id: str) -> dict[str, Any] | None:
    """Load a matrix hint for a case from the golden-coverage-matrix.json."""
    matrix_path = Path(".planning/phases/02-jury-mvp/golden-coverage-matrix.json")
    if not matrix_path.exists():
        return None
    try:
        matrix_data = json.loads(matrix_path.read_text(encoding="utf-8"))
        for case in matrix_data.get("cases", []):
            if case.get("case_id") == case_id:
                return {
                    "source_family": case.get("source_family"),
                    "source_id": case.get("source_id"),
                    "filters": case.get("filters"),
                    "expected_terminal_outcome": case.get("expected_terminal_outcome"),
                }
    except Exception:
        pass
    return None


def _state_to_serializable(state: dict[str, Any]) -> dict[str, Any]:
    """Convert Phase2State to a JSON-serializable dict."""
    result: dict[str, Any] = {}
    for key, value in state.items():
        if str(key).startswith("_"):
            continue  # Skip internal runtime keys
        if hasattr(value, "model_dump"):
            result[key] = value.model_dump()
        elif isinstance(value, list):
            result[key] = [
                item.model_dump() if hasattr(item, "model_dump") else item
                for item in value
            ]
        elif isinstance(value, dict):
            result[key] = value
        else:
            result[key] = value

    # Ensure status field is present for callers expecting it
    result["status"] = "finalization_pending" if result.get("finalization_pending") else "ok"
    return result


def run_golden_case(
    *,
    goldens_path: Path,
    case_index: int,
    json_output: Path,
    live_llm: bool,
    live_embeddings: bool,
    artifact_dir: Path,
) -> dict[str, Any]:
    """Load a golden case and run it through the Phase 2 workflow."""
    case = _load_golden_case(goldens_path, case_index)
    query = str(case.get("query_ru") or case.get("query") or "")
    case_id = str(case.get("id") or case.get("case_id") or f"case-{case_index}")

    config = WorkflowRunConfig.default().model_copy(
        update={
            "goldens_path": goldens_path,
            "artifact_dir": artifact_dir,
            "live_llm_required": live_llm,
            "live_embeddings_required": live_embeddings,
            "case_id": case_id,
        }
    )

    state = run_user_query_to_pending_finalization(query, run_config=config)
    result = _state_to_serializable(state)

    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return result


def run_query(
    *,
    query: str,
    json_output: Path,
    live_llm: bool,
    live_embeddings: bool,
    artifact_dir: Path,
) -> dict[str, Any]:
    """Run a single user query through the Phase 2 workflow."""
    config = WorkflowRunConfig.default().model_copy(
        update={
            "artifact_dir": artifact_dir,
            "live_llm_required": live_llm,
            "live_embeddings_required": live_embeddings,
        }
    )

    state = run_user_query_to_pending_finalization(query, run_config=config)
    result = _state_to_serializable(state)

    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Phase 2 workflow graph through extraction (finalization_pending)."
    )

    # Query input - either direct --query or --case-index from goldens
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--query",
        type=str,
        help="Natural language query to run through the workflow.",
    )
    input_group.add_argument(
        "--case-index",
        type=int,
        help="Index of a golden case to run (requires --goldens).",
    )

    # Goldens path (optional, used with --case-index)
    parser.add_argument(
        "--goldens",
        type=Path,
        default=Path(".planning/phases/01-data-architecture-research/golden-cases.yaml"),
        help="Path to golden cases YAML file.",
    )

    # Output
    parser.add_argument(
        "--json-output",
        type=Path,
        required=True,
        help="Path to write the Phase2State JSON output.",
    )

    # Artifact dir
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path(".planning/phases/02-jury-mvp/workflow-runs"),
        help="Directory for run artifacts.",
    )

    # LLM/embeddings gating
    parser.add_argument(
        "--no-live-llm",
        action="store_true",
        default=False,
        help="Disable live LLM calls (use deterministic fallback for tests).",
    )
    parser.add_argument(
        "--no-live-embeddings",
        action="store_true",
        default=False,
        help="Disable live embedding calls (use index manifest only).",
    )

    args = parser.parse_args()

    live_llm = not args.no_live_llm
    live_embeddings = not args.no_live_embeddings

    if args.query is not None:
        result = run_query(
            query=args.query,
            json_output=args.json_output,
            live_llm=live_llm,
            live_embeddings=live_embeddings,
            artifact_dir=args.artifact_dir,
        )
    else:
        if args.case_index is None:
            parser.error("--case-index requires --goldens to be specified")
        result = run_golden_case(
            goldens_path=args.goldens,
            case_index=args.case_index,
            json_output=args.json_output,
            live_llm=live_llm,
            live_embeddings=live_embeddings,
            artifact_dir=args.artifact_dir,
        )

    # Print status summary to stdout
    print(json.dumps({
        "status": result.get("status", "unknown"),
        "finalization_pending": result.get("finalization_pending", False),
        "run_id": result.get("run_id"),
        "output": str(args.json_output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
