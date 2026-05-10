"""Run one Phase 2 workflow query without Streamlit.

This is the direct CLI wrapper around app.workflow.service.run_user_query.
Use it for manual UAT when the browser UI gets in the way.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.workflow.service import WorkflowRunConfig, continue_user_query, run_user_query


def _response_to_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if isinstance(response, dict):
        return response
    return {"response": str(response)}


def _print_summary(response: dict[str, Any]) -> None:
    print(f"run_id: {response.get('run_id')}")
    print(f"outcome: {response.get('final_outcome')}")
    print()
    print(response.get("message") or "")
    print()
    print(f"selected_sources: {len(response.get('selected_sources') or [])}")
    print(f"rejected_sources: {len(response.get('rejected_sources') or [])}")
    print(f"dataset_artifacts: {len(response.get('dataset_artifacts') or [])}")
    print(f"script_artifacts: {len(response.get('script_artifacts') or [])}")
    print(f"trace_events: {len(response.get('trace_events') or [])}")

    questions = response.get("clarification_questions") or []
    if questions:
        print()
        print("clarification_questions:")
        for question in questions:
            print(f"- {question}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one DataAgent Phase 2 workflow query without Streamlit."
    )
    parser.add_argument("query", help="User query to run through the workflow.")
    parser.add_argument(
        "--follow-up",
        help="Optional clarification answer. Only used when the first response needs clarification.",
    )
    parser.add_argument(
        "--case-id",
        help="Optional golden case id, e.g. GC-001. Useful when reproducing acceptance runs.",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path(".planning/phases/02-jury-mvp/manual-runs"),
        help="Directory for workflow state, datasets, scripts, and response JSON.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Where to write the final WorkflowResponse JSON. Defaults to artifact-dir/<run_id>/response.json.",
    )
    parser.add_argument(
        "--no-live-llm-required",
        action="store_true",
        help="Allow configured test/local fallback behavior when live LLM credentials are unavailable.",
    )
    parser.add_argument(
        "--no-live-embeddings-required",
        action="store_true",
        help="Allow configured test/local fallback behavior when live embeddings are unavailable.",
    )
    args = parser.parse_args()

    config = WorkflowRunConfig.default().model_copy(
        update={
            "artifact_dir": args.artifact_dir,
            "case_id": args.case_id,
            "live_llm_required": not args.no_live_llm_required,
            "live_embeddings_required": not args.no_live_embeddings_required,
        }
    )

    response = run_user_query(args.query, run_config=config)
    if args.follow_up and response.final_outcome == "needs_clarification":
        response = continue_user_query(response.run_id, args.follow_up, run_config=config)

    response_dict = _response_to_dict(response)
    run_id = str(response_dict.get("run_id") or "unknown")
    json_output = args.json_output or args.artifact_dir / run_id / "response.json"
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(response_dict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    _print_summary(response_dict)
    print()
    print(f"json_output: {json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
