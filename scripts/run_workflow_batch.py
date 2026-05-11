"""Run many DataAgent queries headlessly and save analysis artifacts.

Input formats:
- .txt: one query per non-empty line
- .json/.yaml: list of strings or objects with query/follow_up/id
- .jsonl: one string or object per line

Each query uses app.workflow.service.run_user_query. The service writes the
full workflow state under artifact_dir/<run_id>/; this runner writes batch-level
request, response, and summary files around those run artifacts.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.workflow.service import WorkflowRunConfig, continue_user_query, run_user_query


DEFAULT_OUTPUT_DIR = Path(".planning/phases/02-jury-mvp/batch-runs")


@dataclass(frozen=True)
class BatchItem:
    item_id: str
    query: str
    follow_up: str | None = None


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_items(path: Path) -> list[BatchItem]:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        raw_items: list[Any] = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    elif suffix == ".jsonl":
        raw_items = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    elif suffix in {".yaml", ".yml"}:
        import yaml

        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        raw_items = loaded if isinstance(loaded, list) else loaded.get("queries", [])
    else:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        raw_items = loaded if isinstance(loaded, list) else loaded.get("queries", [])

    items: list[BatchItem] = []
    for idx, raw in enumerate(raw_items, start=1):
        if isinstance(raw, str):
            query = raw.strip()
            item_id = f"q{idx:03d}"
            follow_up = None
        elif isinstance(raw, dict):
            query = str(raw.get("query") or raw.get("query_ru") or "").strip()
            item_id = str(raw.get("id") or raw.get("case_id") or f"q{idx:03d}")
            follow_up = raw.get("follow_up") or raw.get("clarification_answer")
            follow_up = str(follow_up).strip() if follow_up else None
        else:
            raise ValueError(f"Unsupported query item at index {idx}: {raw!r}")
        if not query:
            raise ValueError(f"Empty query at index {idx}")
        items.append(BatchItem(item_id=item_id, query=query, follow_up=follow_up))
    return items


def _dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _response_to_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if isinstance(response, dict):
        return response
    return {"response": str(response)}


def _summarize_response(
    *,
    item: BatchItem,
    response: dict[str, Any],
    item_dir: Path,
    workflow_artifact_dir: Path,
    error: str | None = None,
    initial_response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = str(response.get("run_id") or "")
    clarification_questions = list(response.get("clarification_questions") or [])
    selected_sources = list(response.get("selected_sources") or [])
    rejected_sources = list(response.get("rejected_sources") or [])
    dataset_artifacts = list(response.get("dataset_artifacts") or [])
    script_artifacts = list(response.get("script_artifacts") or [])
    trace_events = list(response.get("trace_events") or [])
    return {
        "item_id": item.item_id,
        "query": item.query,
        "follow_up": item.follow_up,
        "run_id": run_id,
        "final_outcome": response.get("final_outcome"),
        "error": error,
        "needs_clarification": response.get("final_outcome") == "needs_clarification",
        "clarification_questions": clarification_questions,
        "clarification_answered": bool(initial_response and item.follow_up),
        "selected_sources": len(selected_sources),
        "rejected_sources": len(rejected_sources),
        "dataset_artifacts": len(dataset_artifacts),
        "script_artifacts": len(script_artifacts),
        "trace_events": len(trace_events),
        "component_statuses": response.get("component_statuses") or {},
        "item_dir": str(item_dir),
        "response_path": str(item_dir / "response.json"),
        "initial_response_path": str(item_dir / "initial-response.json")
        if initial_response
        else None,
        "run_artifact_dir": str(workflow_artifact_dir / run_id) if run_id else None,
    }


def _render_markdown(summary: dict[str, Any]) -> str:
    rows = []
    for item in summary["items"]:
        status = "ERROR" if item.get("error") else item.get("final_outcome") or "unknown"
        rows.append(
            "| {item_id} | {status} | {selected} | {rejected} | {datasets} | {scripts} | {trace} | {clarify} |".format(
                item_id=item["item_id"],
                status=status,
                selected=item["selected_sources"],
                rejected=item["rejected_sources"],
                datasets=item["dataset_artifacts"],
                scripts=item["script_artifacts"],
                trace=item["trace_events"],
                clarify="yes" if item["needs_clarification"] else "no",
            )
        )
    return """# DataAgent Batch Run

- Batch ID: `{batch_id}`
- Total: `{total}`
- Errors: `{errors}`
- Needs clarification: `{needs_clarification}`
- Output dir: `{output_dir}`

| Item | Outcome | Selected | Rejected | Datasets | Scripts | Trace | Clarification |
|---|---|---:|---:|---:|---:|---:|---|
{rows}
""".format(
        batch_id=summary["batch_id"],
        total=summary["total"],
        errors=summary["errors"],
        needs_clarification=summary["needs_clarification"],
        output_dir=summary["output_dir"],
        rows="\n".join(rows),
    )


def run_batch(
    *,
    items: list[BatchItem],
    output_dir: Path,
    limit: int | None = None,
) -> dict[str, Any]:
    batch_id = output_dir.name
    workflow_artifact_dir = output_dir / "workflow-runs"
    results_dir = output_dir / "items"
    selected_items = items[:limit] if limit else items

    rows: list[dict[str, Any]] = []
    for position, item in enumerate(selected_items, start=1):
        item_dir = results_dir / f"{position:03d}-{item.item_id}"
        _dump_json(item_dir / "request.json", item.__dict__)

        config = WorkflowRunConfig.default().model_copy(
            update={
                "artifact_dir": workflow_artifact_dir,
                "case_id": item.item_id,
                "live_llm_required": True,
                "live_embeddings_required": True,
            }
        )

        try:
            response = run_user_query(item.query, run_config=config)
            response_dict = _response_to_dict(response)
            initial_response = None
            _dump_json(item_dir / "response.json", response_dict)

            if response.final_outcome == "needs_clarification" and item.follow_up:
                initial_response = response_dict
                _dump_json(item_dir / "initial-response.json", initial_response)
                response = continue_user_query(response.run_id, item.follow_up, run_config=config)
                response_dict = _response_to_dict(response)
                _dump_json(item_dir / "response.json", response_dict)

            rows.append(
                _summarize_response(
                    item=item,
                    response=response_dict,
                    item_dir=item_dir,
                    workflow_artifact_dir=workflow_artifact_dir,
                    initial_response=initial_response,
                )
            )
        except Exception as exc:
            error_payload = {
                "item_id": item.item_id,
                "query": item.query,
                "error": f"{type(exc).__name__}: {exc}",
            }
            _dump_json(item_dir / "error.json", error_payload)
            rows.append(
                {
                    **error_payload,
                    "follow_up": item.follow_up,
                    "run_id": None,
                    "final_outcome": "error",
                    "needs_clarification": False,
                    "clarification_questions": [],
                    "clarification_answered": False,
                    "selected_sources": 0,
                    "rejected_sources": 0,
                    "dataset_artifacts": 0,
                    "script_artifacts": 0,
                    "trace_events": 0,
                    "component_statuses": {},
                    "item_dir": str(item_dir),
                    "response_path": None,
                    "initial_response_path": None,
                    "run_artifact_dir": None,
                }
            )

    outcome_counts: dict[str, int] = {}
    for row in rows:
        outcome = str(row.get("final_outcome") or "unknown")
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

    summary = {
        "batch_id": batch_id,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "output_dir": str(output_dir),
        "workflow_artifact_dir": str(workflow_artifact_dir),
        "total": len(rows),
        "errors": outcome_counts.get("error", 0),
        "needs_clarification": sum(1 for row in rows if row.get("needs_clarification")),
        "outcome_counts": outcome_counts,
        "items": rows,
    }
    _dump_json(output_dir / "summary.json", summary)
    (output_dir / "summary.md").write_text(_render_markdown(summary), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run many DataAgent queries headlessly.")
    parser.add_argument("queries", type=Path, help="Path to .txt, .json, .jsonl, or .yaml query list.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Batch output directory. Defaults to .planning/phases/02-jury-mvp/batch-runs/<timestamp>.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N queries.")
    args = parser.parse_args()

    items = _load_items(args.queries)
    output_dir = args.output_dir or DEFAULT_OUTPUT_DIR / f"batch-{_utc_stamp()}"
    summary = run_batch(items=items, output_dir=output_dir, limit=args.limit)
    print(
        json.dumps(
            {
                "batch_id": summary["batch_id"],
                "total": summary["total"],
                "errors": summary["errors"],
                "needs_clarification": summary["needs_clarification"],
                "summary": str(output_dir / "summary.json"),
                "markdown": str(output_dir / "summary.md"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
