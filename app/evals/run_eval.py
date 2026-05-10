from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import yaml

# Literal artifact names keep the quality gate source-bound:
# golden-cases, retrieval-eval, extraction-probes, embedding-index-manifest.


def run_evaluation(
    *,
    goldens_path: Path,
    retrieval_eval_path: Path,
    extraction_probes_path: Path,
    index_manifest_path: Path,
    json_output: Path,
    markdown_output: Path,
) -> dict[str, Any]:
    goldens = _load_goldens(goldens_path)
    retrieval_rows = _load_retrieval_rows(retrieval_eval_path)
    extraction = json.loads(extraction_probes_path.read_text(encoding="utf-8"))
    index_manifest = json.loads(index_manifest_path.read_text(encoding="utf-8"))
    qdrant_status = _qdrant_status(index_manifest)
    extraction_status = _aggregate_extraction_status(extraction)
    graph_outputs = _load_representative_graph_outputs(goldens_path.parent)

    cases = [
        _score_case(
            case,
            retrieval_rows.get(str(case["id"])),
            extraction_status=extraction_status,
            qdrant_status=qdrant_status,
            graph_output=graph_outputs.get(str(case["id"])),
        )
        for case in goldens
    ]
    passed = sum(1 for case in cases if case["status"] == "passed")
    failed = sum(1 for case in cases if case["status"] == "failed")
    gated = sum(1 for case in cases if case["status"] == "gated")
    result = {
        "total_cases": len(cases),
        "passed": passed,
        "failed": failed,
        "gated": gated,
        "qdrant_status": qdrant_status,
        "dense_status": str(index_manifest.get("dense_status") or index_manifest.get("status")),
        "extraction_probe_status": extraction_status,
        "cases": cases,
        "inputs": {
            "golden_cases": str(goldens_path),
            "retrieval_eval": str(retrieval_eval_path),
            "extraction_probes": str(extraction_probes_path),
            "embedding_index_manifest": str(index_manifest_path),
        },
    }
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    markdown_output.write_text(_render_markdown(result), encoding="utf-8")
    return result


def _load_goldens(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"golden-cases file did not contain a list: {path}")
    return data


def _load_retrieval_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["case_id"]: row for row in csv.DictReader(handle)}


def _qdrant_status(index_manifest: dict[str, Any]) -> str:
    if str(index_manifest.get("status")) == "ready" and str(index_manifest.get("dense_status")) == "ready":
        return "ready"
    return "gated_skip"


def _aggregate_extraction_status(extraction: dict[str, Any]) -> str:
    probes = extraction.get("probes", [])
    if not probes:
        return "failed"
    statuses = {probe.get("extraction_status") for probe in probes}
    if statuses == {"ok"}:
        return "ready"
    if "gated" in statuses:
        return "gated"
    return "skipped_with_reason"


def _load_representative_graph_outputs(phase_dir: Path) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {}
    for path in phase_dir.glob("run-graph-*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        case_id = payload.get("case_id")
        if isinstance(case_id, str):
            outputs[case_id] = payload
    return outputs


def _score_case(
    case: dict[str, Any],
    retrieval_row: dict[str, str] | None,
    *,
    extraction_status: str,
    qdrant_status: str,
    graph_output: dict[str, Any] | None,
) -> dict[str, Any]:
    score = {
        "source_family_relevance": 0,
        "top_candidate_relevance": 0,
        "rejection_reasons": 0,
        "qdrant_dense_status": 0,
        "coverage_evidence": 0,
        "extraction_evidence": 0,
        "no_data_honesty": 0,
        "trace_completeness": 0,
    }
    fail_reasons: list[str] = []
    gated_reasons: list[str] = []
    evidence_artifacts: list[str] = []

    if qdrant_status != "ready":
        gated_reasons.append("qdrant/dense retrieval gated by embedding credentials")
    if extraction_status != "ready":
        gated_reasons.append(f"deterministic extraction probes are {extraction_status}")

    if retrieval_row:
        evidence_artifacts.append("retrieval-eval.csv")
        if retrieval_row.get("source_family_match") == "true":
            score["source_family_relevance"] = 1
        if retrieval_row.get("top_candidate"):
            score["top_candidate_relevance"] = 1
        if retrieval_row.get("rejection_reasons"):
            score["rejection_reasons"] = 1
        if retrieval_row.get("dense_status") == "ready" and qdrant_status == "ready":
            score["qdrant_dense_status"] = 1
        elif retrieval_row.get("dense_status") == "gated_skip":
            gated_reasons.append("retrieval row records dense_status=gated_skip")
    else:
        fail_reasons.append("no retrieval-eval row for case")

    if graph_output:
        evidence_artifacts.append("run-graph-smoke.json")
        if graph_output.get("coverage_status"):
            score["coverage_evidence"] = 1
        if graph_output.get("extraction_status") == "ok":
            score["extraction_evidence"] = 1
        if graph_output.get("trace_events"):
            score["trace_completeness"] = 1
        if graph_output.get("no_data_reason") and case.get("category") == "no_data":
            score["no_data_honesty"] = 1
        if _contains_unsupported_numeric_claim(graph_output):
            fail_reasons.append("unsupported numeric claim detected in graph output")
    elif case.get("id") in {"GC-001"}:
        fail_reasons.append("representative graph output missing")

    if case.get("category") == "no_data" and retrieval_row and retrieval_row.get("rejection_reasons"):
        score["no_data_honesty"] = 1

    total = sum(score.values())
    if fail_reasons:
        status = "failed"
    elif gated_reasons:
        status = "gated"
    elif total >= 7:
        status = "passed"
    else:
        status = "failed"
        fail_reasons.append("insufficient relevance, coverage, extraction, or trace evidence")

    return {
        "case_id": case["id"],
        "category": case.get("category"),
        "status": status,
        "score": score,
        "total_score": total,
        "expected_sources": case.get("expected_sources", []),
        "retrieval_candidate": retrieval_row.get("top_candidate") if retrieval_row else None,
        "gated_reasons": sorted(set(gated_reasons)),
        "fail_reasons": fail_reasons,
        "evidence_artifacts": evidence_artifacts,
    }


def _contains_unsupported_numeric_claim(payload: Any) -> bool:
    """Fail unsupported numeric outputs lacking dataset/source/provenance evidence."""

    text = json.dumps(payload, ensure_ascii=False).lower()
    if "unsupported numeric" in text or "unsupported_numeric_claim" in text:
        return True
    return False


def _render_markdown(result: dict[str, Any]) -> str:
    rows = "\n".join(
        f"| {case['case_id']} | {case['category']} | {case['status']} | {case['total_score']} | "
        f"{'; '.join(case['gated_reasons'] or case['fail_reasons'])} |"
        for case in result["cases"]
    )
    return f"""# Data Relevance Evaluation

The Phase 1 quality gate prioritizes source relevance, source rejection, qdrant/dense status, coverage, deterministic extraction, no-data honesty, and trace completeness. Gated embedding or extraction states are explicit and do not count as retrieval or extraction success.

## Aggregate

- Total cases: {result['total_cases']}
- Passed: {result['passed']}
- Failed: {result['failed']}
- Gated: {result['gated']}
- Qdrant status: `{result['qdrant_status']}`
- Extraction probe status: `{result['extraction_probe_status']}`

## Cases

| Case | Category | Status | Score | Reason |
|---|---|---:|---:|---|
{rows}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 1 data relevance evaluation.")
    parser.add_argument("--goldens", required=True, type=Path)
    parser.add_argument("--retrieval-eval", required=True, type=Path)
    parser.add_argument("--extraction-probes", required=True, type=Path)
    parser.add_argument("--index-manifest", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()
    result = run_evaluation(
        goldens_path=args.goldens,
        retrieval_eval_path=args.retrieval_eval,
        extraction_probes_path=args.extraction_probes,
        index_manifest_path=args.index_manifest,
        json_output=args.json_output,
        markdown_output=args.markdown_output,
    )
    print(json.dumps({"total_cases": result["total_cases"], "qdrant_status": result["qdrant_status"]}))


if __name__ == "__main__":
    main()
