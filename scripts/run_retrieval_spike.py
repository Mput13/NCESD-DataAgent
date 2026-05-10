#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.retrieval.hybrid_retrieval import HybridRetriever

DEFAULT_GOLDENS = Path(".planning/phases/01-data-architecture-research/golden-cases.yaml")
DEFAULT_INDEX_MANIFEST = Path(
    ".planning/phases/01-data-architecture-research/embedding-index-manifest.json"
)
DEFAULT_OUTPUT = Path(".planning/phases/01-data-architecture-research/retrieval-eval.csv")
DEFAULT_COMPARISON = Path(".planning/phases/01-data-architecture-research/retrieval-comparison.md")
DEFAULT_SERVER_MANIFEST = Path(".planning/phases/02-jury-mvp/qdrant-server-manifest.json")

FIELDNAMES = [
    "case_id",
    "expected_route",
    "query",
    "retrieval_mode",
    "top_candidate",
    "top_title",
    "top_source_family",
    "relevance_score",
    "source_family_match",
    "dense_status",
    "index_manifest_status",
    "qdrant_collection",
    "qdrant_url",
    "server_manifest_status",
    "selected_count",
    "rejected_count",
    "rejection_reasons",
    "rerank_status",
    "evidence_keywords",
    "provenance_url",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate hybrid retrieval over the prepared Qdrant index contract."
    )
    parser.add_argument("--goldens", type=Path, default=DEFAULT_GOLDENS)
    parser.add_argument("--index-manifest", type=Path, default=DEFAULT_INDEX_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument(
        "--server-manifest",
        type=Path,
        default=DEFAULT_SERVER_MANIFEST,
        help="Path to the Qdrant server manifest JSON (for server_manifest_status field).",
    )
    parser.add_argument(
        "--phase2-output-json",
        type=Path,
        default=None,
        help="If set, write a Phase 2 retrieval evidence JSON to this path.",
    )
    args = parser.parse_args()

    goldens = yaml.safe_load(args.goldens.read_text(encoding="utf-8"))
    index_manifest = json.loads(args.index_manifest.read_text(encoding="utf-8"))

    rows = run_retrieval_evaluation(
        goldens_path=args.goldens,
        index_manifest_path=args.index_manifest,
        output_path=args.output,
        comparison_path=args.comparison,
        case_limit=args.limit,
        server_manifest_path=args.server_manifest if args.server_manifest.exists() else None,
    )
    print(f"Wrote {len(rows)} retrieval eval rows to {args.output}")

    if args.phase2_output_json is not None:
        server_manifest_path = args.server_manifest if args.server_manifest.exists() else None
        phase2_data = build_phase2_output_json(
            rows=rows,
            golden_cases=goldens,
            index_manifest=index_manifest,
            server_manifest_path=server_manifest_path,
        )
        args.phase2_output_json.parent.mkdir(parents=True, exist_ok=True)
        args.phase2_output_json.write_text(
            json.dumps(phase2_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Wrote Phase 2 output JSON to {args.phase2_output_json}")


def run_retrieval_evaluation(
    *,
    goldens_path: Path,
    index_manifest_path: Path,
    output_path: Path,
    comparison_path: Path,
    case_limit: int = 8,
    server_manifest_path: Path | None = None,
) -> list[dict[str, Any]]:
    goldens = yaml.safe_load(goldens_path.read_text(encoding="utf-8"))
    if not isinstance(goldens, list) or not goldens:
        raise RuntimeError(f"No golden cases found in {goldens_path}")

    server_manifest_status = _load_server_manifest_status(server_manifest_path)
    retriever = HybridRetriever(index_manifest_path)
    qdrant_url = str(retriever.index_manifest.get("qdrant_url", ""))

    rows: list[dict[str, Any]] = []
    for case in _bounded_cases(goldens, limit=case_limit):
        query = str(case.get("query_ru", ""))
        expected_sources = [str(source) for source in case.get("expected_sources", [])]
        expected_route = _expected_route(case)
        result = retriever.search(query, expected_sources=expected_sources, limit=5)
        top = result.candidates[0] if result.candidates else None
        rejected_reasons = _rejection_summary(result.rejected_candidates)
        rows.append(
            {
                "case_id": case.get("id"),
                "expected_route": expected_route,
                "query": query,
                "retrieval_mode": top.retrieval_mode if top else "no_candidate",
                "top_candidate": top.card_id if top else "",
                "top_title": top.title if top else "",
                "top_source_family": top.source_family if top else "",
                "relevance_score": f"{top.relevance_score:.4f}" if top else "0.0000",
                "source_family_match": str(
                    _source_family_match(top.source_family, expected_sources) if top else False
                ).lower(),
                "dense_status": result.dense_status,
                "index_manifest_status": result.index_manifest_status,
                "qdrant_collection": result.qdrant_collection,
                "qdrant_url": qdrant_url,
                "server_manifest_status": server_manifest_status,
                "selected_count": len(result.candidates),
                "rejected_count": len(result.rejected_candidates),
                "rejection_reasons": rejected_reasons,
                "rerank_status": result.rerank_status,
                "evidence_keywords": ";".join(top.evidence_keywords) if top else "",
                "provenance_url": str((top.metadata if top else {}).get("provenance_url") or ""),
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    comparison_path.parent.mkdir(parents=True, exist_ok=True)
    comparison_path.write_text(
        render_retrieval_comparison(
            index_manifest_path=index_manifest_path,
            retriever=retriever,
            rows=rows,
        ),
        encoding="utf-8",
    )
    return rows


def build_phase2_output_json(
    *,
    rows: list[dict[str, Any]],
    golden_cases: list[dict[str, Any]],
    index_manifest: dict[str, Any],
    server_manifest_path: Path | None,
) -> dict[str, Any]:
    """Build a Phase 2 retrieval evidence JSON object.

    Keys:
    - total_cases: number of evaluated cases
    - ready_index: whether the index manifest status is ready
    - server_manifest_status: status from the Qdrant server manifest
    - cases: per-case evidence dicts
    - unacceptable_no_candidate_cases: cases with no candidate where expected terminal is not 'not_found'
    """
    server_manifest_status = _load_server_manifest_status(server_manifest_path)

    # Build a lookup of golden-case expected terminal behaviors
    golden_by_id: dict[str, dict[str, Any]] = {
        str(case.get("id")): case for case in golden_cases
    }

    index_status = str(index_manifest.get("status", ""))
    ready_index = index_status == "ready"

    case_dicts: list[dict[str, Any]] = []
    unacceptable: list[str] = []

    for row in rows:
        case_id = str(row.get("case_id", ""))
        top_candidate = str(row.get("top_candidate", ""))
        no_candidate = not top_candidate

        # Determine if the golden case expects a not_found terminal
        golden = golden_by_id.get(case_id, {})
        expected_terminal = str(golden.get("expected_terminal_behavior", "")).lower()
        is_not_found_case = expected_terminal == "not_found"

        if no_candidate and not is_not_found_case:
            unacceptable.append(case_id)

        case_dicts.append(
            {
                "case_id": case_id,
                "expected_route": row.get("expected_route", ""),
                "top_candidate": top_candidate,
                "top_title": row.get("top_title", ""),
                "top_source_family": row.get("top_source_family", ""),
                "source_family_match": row.get("source_family_match", ""),
                "dense_status": row.get("dense_status", ""),
                "index_manifest_status": row.get("index_manifest_status", ""),
                "qdrant_collection": row.get("qdrant_collection", ""),
                "qdrant_url": row.get("qdrant_url", ""),
                "server_manifest_status": server_manifest_status,
                "selected_count": row.get("selected_count", 0),
                "rejected_count": row.get("rejected_count", 0),
                "rejection_reasons": row.get("rejection_reasons", ""),
                "no_candidate": no_candidate,
                "is_acceptable": not no_candidate or is_not_found_case,
            }
        )

    return {
        "total_cases": len(rows),
        "ready_index": ready_index,
        "server_manifest_status": server_manifest_status,
        "cases": case_dicts,
        "unacceptable_no_candidate_cases": unacceptable,
    }


def render_retrieval_comparison(
    *,
    index_manifest_path: Path,
    retriever: HybridRetriever,
    rows: list[dict[str, Any]],
) -> str:
    manifest = retriever.index_manifest
    return "\n".join(
        [
            "# Retrieval Comparison",
            "",
            "This artifact compares the retrieval stack over the prepared index. Dense retrieval is not optional: when credentials or vectors are unavailable, the row records the skipped evidence explicitly as a credential-aware fallback while preserving the Qdrant collection contract.",
            "",
            "| Path | Implementation | Status | Evidence |",
            "|---|---|---|---|",
            "| lexical BM25/FTS | Local BM25/FTS approximation over source-card embedding_text with RU/EN keyword evidence | ready | `retrieval-eval.csv` records `retrieval_mode`, `evidence_keywords`, and `relevance_score` |",
            f"| Qdrant dense collection | Prepared index manifest `{index_manifest_path}` with Qdrant collection `{manifest.get('collection_name')}` | {manifest.get('dense_status')} | `dense_status`, `index_manifest_status`, and `qdrant_collection` stay present on every eval row |",
            "| rerank | bge-reranker-v2-m3-compatible interface | fallback_keyword_overlap unless endpoint is configured | `rerank_status` records the bge-compatible path or deterministic fallback |",
            f"| local-vs-remote Qdrant config | `QDRANT_MODE={manifest.get('qdrant_mode')}`, path `{manifest.get('qdrant_path', '')}`, URL `{manifest.get('qdrant_url', '')}` | configured | Retrieval code reads the same prepared index manifest for local or server Qdrant |",
            "| skipped evidence | Missing credentials/index artifacts are represented as gated rows, not silent drops | credential-aware fallback | `missing_env_vars`, `dense_status`, and rejection reasons explain what did not run |",
            "",
            "## Evaluation Snapshot",
            "",
            f"- Evaluated rows: `{len(rows)}`",
            f"- Prepared index status: `{manifest.get('status')}`",
            f"- Qdrant collection: `{manifest.get('collection_name')}`",
            f"- Dense status: `{manifest.get('dense_status')}`",
            "",
            "## Rejection Handling",
            "",
            "Weak candidates are not hidden. The CSV records `rejection_reasons`, `source_family_match`, and top-candidate provenance so later UI trace work can expose selected and rejected source cards.",
            "",
        ]
    )


def _bounded_cases(goldens: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    priority_ids = {"GC-001", "GC-002", "GC-003", "GC-009", "GC-011", "GC-013", "GC-019", "GC-020"}
    selected = [case for case in goldens if case.get("id") in priority_ids]
    if len(selected) < min(limit, len(goldens)):
        selected_ids = {case.get("id") for case in selected}
        selected.extend(case for case in goldens if case.get("id") not in selected_ids)
    return selected[:limit]


def _source_family_match(source_family: str, expected_sources: list[str]) -> bool:
    expected = {source.lower().replace(" ", "_") for source in expected_sources}
    return source_family.lower().replace(" ", "_") in expected


def _rejection_summary(rejected: list[Any]) -> str:
    parts: list[str] = []
    for candidate in rejected:
        if candidate.rejection_reasons:
            parts.append(f"{candidate.card_id}:{'|'.join(candidate.rejection_reasons)}")
    return "; ".join(parts)


def _expected_route(case: dict[str, Any]) -> str:
    """Derive expected_route from golden case metadata."""
    category = str(case.get("category", "")).lower()
    expected_sources = case.get("expected_sources", [])
    terminal = str(case.get("expected_terminal_behavior", "")).lower()
    if terminal == "not_found":
        return "not_found"
    if expected_sources:
        return f"source:{','.join(str(s) for s in expected_sources)}"
    return category or "unknown"


def _load_server_manifest_status(server_manifest_path: Path | None) -> str:
    """Load server manifest status from the given path, or return 'not_loaded'."""
    if server_manifest_path is None or not server_manifest_path.exists():
        return "not_loaded"
    try:
        data = json.loads(server_manifest_path.read_text(encoding="utf-8"))
        return str(data.get("status", "unknown"))
    except Exception:
        return "error_reading_manifest"


if __name__ == "__main__":
    main()
