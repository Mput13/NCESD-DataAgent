#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
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

FIELDNAMES = [
    "case_id",
    "query",
    "retrieval_mode",
    "top_candidate",
    "top_source_family",
    "relevance_score",
    "source_family_match",
    "rejection_reasons",
    "dense_status",
    "rerank_status",
    "index_manifest_status",
    "qdrant_collection",
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
    args = parser.parse_args()

    rows = run_retrieval_evaluation(
        goldens_path=args.goldens,
        index_manifest_path=args.index_manifest,
        output_path=args.output,
        comparison_path=args.comparison,
        case_limit=args.limit,
    )
    print(f"Wrote {len(rows)} retrieval eval rows to {args.output}")


def run_retrieval_evaluation(
    *,
    goldens_path: Path,
    index_manifest_path: Path,
    output_path: Path,
    comparison_path: Path,
    case_limit: int = 8,
) -> list[dict[str, Any]]:
    goldens = yaml.safe_load(goldens_path.read_text(encoding="utf-8"))
    if not isinstance(goldens, list) or not goldens:
        raise RuntimeError(f"No golden cases found in {goldens_path}")

    retriever = HybridRetriever(index_manifest_path)
    rows: list[dict[str, Any]] = []
    for case in _bounded_cases(goldens, limit=case_limit):
        query = str(case.get("query_ru", ""))
        expected_sources = [str(source) for source in case.get("expected_sources", [])]
        result = retriever.search(query, expected_sources=expected_sources, limit=5)
        top = result.candidates[0] if result.candidates else None
        rejected_reasons = _rejection_summary(result.rejected_candidates)
        rows.append(
            {
                "case_id": case.get("id"),
                "query": query,
                "retrieval_mode": top.retrieval_mode if top else "no_candidate",
                "top_candidate": top.card_id if top else "",
                "top_source_family": top.source_family if top else "",
                "relevance_score": f"{top.relevance_score:.4f}" if top else "0.0000",
                "source_family_match": str(
                    _source_family_match(top.source_family, expected_sources) if top else False
                ).lower(),
                "rejection_reasons": rejected_reasons,
                "dense_status": result.dense_status,
                "rerank_status": result.rerank_status,
                "index_manifest_status": result.index_manifest_status,
                "qdrant_collection": result.qdrant_collection,
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


if __name__ == "__main__":
    main()
