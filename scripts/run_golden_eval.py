"""Run all golden cases through the live workflow and print metrics."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.workflow.service import WorkflowRunConfig, run_user_query, _finalize_state


GOLDENS_PATH = Path(".planning/phases/01-data-architecture-research/golden-cases.yaml")
RESULTS_PATH = Path("/tmp/golden-live-results.json")


def _score(case: dict, response) -> dict:
    outcome = getattr(response, "final_outcome", "not_found") or "not_found"
    datasets = getattr(response, "dataset_artifacts", []) or []
    sources  = getattr(response, "selected_sources", []) or []
    trace    = getattr(response, "trace_events", []) or []

    has_data     = any(getattr(d, "rows", 0) and (getattr(d, "rows", 0) or 0) > 0 for d in datasets)
    has_sources  = len(sources) > 0
    has_trace    = len(trace) >= 4
    passed_flag  = outcome == "passed"
    not_found_ok = outcome == "not_found" and case.get("category") == "no_data"

    expected_src_families = {s.lower() for s in case.get("expected_sources", [])}
    found_families = {(s.get("source_family") or "").lower() for s in sources}
    source_match = bool(expected_src_families & found_families) if expected_src_families else True

    score = {
        "passed":        int(passed_flag or not_found_ok),
        "has_data":      int(has_data),
        "has_sources":   int(has_sources),
        "source_match":  int(source_match),
        "has_trace":     int(has_trace),
    }
    total = sum(score.values())
    status = "passed" if (passed_flag or not_found_ok) else ("partial" if total >= 3 else "failed")

    return {
        "case_id":   case["id"],
        "category":  case.get("category"),
        "query":     case.get("query_ru", ""),
        "outcome":   outcome,
        "status":    status,
        "score":     score,
        "total":     total,
        "rows":      sum((getattr(d, "rows", 0) or 0) for d in datasets),
        "sources":   [s.get("title", s.get("card_id", ""))[:50] for s in sources[:3]],
    }


def main() -> None:
    cases = yaml.safe_load(GOLDENS_PATH.read_text(encoding="utf-8"))
    config = WorkflowRunConfig.default()

    results = []
    counts = {"passed": 0, "partial": 0, "failed": 0}

    print(f"\nRunning {len(cases)} golden cases...\n")

    for i, case in enumerate(cases, 1):
        query = case.get("query_ru", "").strip()
        if not query:
            continue
        print(f"[{i:02d}/{len(cases)}] {case['id']} — {query[:60]}")
        t0 = time.time()
        try:
            state = run_user_query.__wrapped__(query, run_config=config) if hasattr(run_user_query, "__wrapped__") else None
            # use the standard path
            from app.workflow.graph import build_phase2_graph
            from app.workflow.state import new_run_id
            run_id = new_run_id()
            initial = {
                "run_id": run_id, "query": query, "intent": None,
                "research_design": None, "evidence": None,
                "coverage_reports": [], "extraction_plan": None,
                "dataset_artifacts": [], "script_artifacts": [],
                "final_outcome": None, "finalization_pending": False,
                "pending_reason": None, "trace_events": [], "component_statuses": {},
                "_live_llm_required": True, "_live_embeddings_required": True,
                "_artifact_dir": str(config.artifact_dir),
                "_index_manifest_path": str(config.phase1_index_manifest),
            }
            graph = build_phase2_graph()
            state = graph.invoke(initial)
            response = _finalize_state(state, config=config)
            elapsed = round(time.time() - t0, 1)
            row = _score(case, response)
            row["elapsed_s"] = elapsed
            results.append(row)
            counts[row["status"]] += 1
            flag = "✓" if row["status"] == "passed" else ("~" if row["status"] == "partial" else "✗")
            print(f"  {flag} {row['status']:7} | outcome={row['outcome']:18} | rows={row['rows']:4} | {elapsed}s")
        except Exception as exc:
            elapsed = round(time.time() - t0, 1)
            print(f"  ✗ ERROR: {exc}")
            results.append({
                "case_id": case["id"], "category": case.get("category"),
                "query": query, "outcome": "error", "status": "failed",
                "score": {}, "total": 0, "rows": 0, "sources": [],
                "error": str(exc), "elapsed_s": elapsed,
            })
            counts["failed"] += 1

    total = len(results)
    print(f"\n{'='*60}")
    print(f"  TOTAL: {total}  |  ✓ passed: {counts['passed']}  "
          f"~ partial: {counts['partial']}  ✗ failed: {counts['failed']}")
    print(f"  Pass rate: {counts['passed']/total*100:.0f}%  "
          f"| Partial+Pass: {(counts['passed']+counts['partial'])/total*100:.0f}%")
    print(f"{'='*60}\n")

    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Results saved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
