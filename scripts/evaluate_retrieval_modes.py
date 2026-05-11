#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.retrieval.hybrid_retrieval import (  # noqa: E402
    DenseQdrantRetriever,
    GraphExpander,
    LexicalBM25Retriever,
    RetrievalCandidate,
    _make_candidate,
    _rrf_fuse,
    load_documents_from_index_manifest,
)
from app.retrieval.graph_store import (  # noqa: E402
    KnowledgeGraphStore,
    extract_canonical_ids,
    normalize_identifier,
)

DEFAULT_GOLDENS = Path(".planning/phases/01-data-architecture-research/golden-cases.yaml")
DEFAULT_MATRIX = Path(".planning/phases/02-jury-mvp/golden-coverage-matrix.json")
DEFAULT_INDEX_MANIFEST = Path(
    ".planning/phases/01-data-architecture-research/embedding-index-manifest.json"
)
DEFAULT_OUTPUT_CSV = Path(".planning/phases/02-jury-mvp/retrieval-mode-comparison.csv")
DEFAULT_OUTPUT_JSON = Path(".planning/phases/02-jury-mvp/retrieval-mode-comparison.json")
DEFAULT_OUTPUT_MD = Path(".planning/phases/02-jury-mvp/retrieval-mode-comparison.md")

MODES = (
    "dense_only",
    "lexical_only",
    "graph_first",
    "dense_plus_lexical",
    "hybrid_graph",
)
FIELDNAMES = [
    "case_id",
    "mode",
    "query",
    "expected_terminal_outcome",
    "expected_source_family",
    "expected_source_ids",
    "expected_id_in_corpus",
    "top1_card_id",
    "top1_title",
    "top1_source_family",
    "top1_score",
    "top1_canonical_ids",
    "top1_extraction_readiness",
    "source_family_hit_top1",
    "source_family_hit_top5",
    "expected_id_hit_top1",
    "expected_id_hit_top3",
    "expected_id_hit_top5",
    "retrieval_miss_type",
    "candidate_count",
    "dense_status",
    "graph_status",
    "top5_card_ids",
    "top5_titles",
]


@dataclass(frozen=True)
class CaseExpectation:
    case_id: str
    query: str
    expected_terminal_outcome: str
    expected_source_family: str
    expected_source_ids: list[str]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compare dense_only, lexical_only, graph_first, dense_plus_lexical, and hybrid_graph "
            "over offline-labeled queries."
        )
    )
    parser.add_argument("--goldens", type=Path, default=DEFAULT_GOLDENS)
    parser.add_argument("--coverage-matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--index-manifest", type=Path, default=DEFAULT_INDEX_MANIFEST)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--case-limit", type=int, default=0)
    args = parser.parse_args()

    result = evaluate_retrieval_modes(
        goldens_path=args.goldens,
        coverage_matrix_path=args.coverage_matrix,
        index_manifest_path=args.index_manifest,
        top_k=args.top_k,
        case_limit=args.case_limit or None,
    )
    write_outputs(
        result=result,
        output_csv=args.output_csv,
        output_json=args.output_json,
        output_md=args.output_md,
    )
    print(f"Wrote retrieval mode comparison CSV to {args.output_csv}")
    print(f"Wrote retrieval mode comparison JSON to {args.output_json}")
    print(f"Wrote retrieval mode comparison report to {args.output_md}")


def evaluate_retrieval_modes(
    *,
    goldens_path: Path,
    coverage_matrix_path: Path,
    index_manifest_path: Path,
    top_k: int = 5,
    case_limit: int | None = None,
) -> dict[str, Any]:
    goldens = yaml.safe_load(goldens_path.read_text(encoding="utf-8"))
    if not isinstance(goldens, list) or not goldens:
        raise RuntimeError(f"No golden cases found in {goldens_path}")

    matrix = json.loads(coverage_matrix_path.read_text(encoding="utf-8"))
    index_manifest = json.loads(index_manifest_path.read_text(encoding="utf-8"))
    documents = load_documents_from_index_manifest(index_manifest)
    corpus_ids = _corpus_ids(documents)

    expectations = _load_expectations(goldens=goldens, matrix=matrix)
    if case_limit is not None:
        expectations = expectations[:case_limit]

    lexical = LexicalBM25Retriever(documents)
    dense = DenseQdrantRetriever(index_manifest)
    graph = KnowledgeGraphStore(documents)
    graph_expander = GraphExpander(graph, dense)
    doc_by_card = {str(document.get("card_id") or ""): document for document in documents}

    rows: list[dict[str, Any]] = []
    for exp in expectations:
        pool = max(top_k, 20)
        lexical_cands = lexical.search(exp.query, limit=pool)
        dense_cands = dense.search(exp.query, limit=pool)
        graph_first_cands = _graph_first_candidates(
            graph,
            doc_by_card,
            exp.query,
            pool=pool,
        )

        dense_plus_lexical = _rrf_fuse(
            [("lexical", lexical_cands, 0.55), ("dense", dense_cands, 4.0)],
            limit=pool,
        )
        graph_cands = _graph_neighbours_from_dense(graph_expander, dense_cands, pool=pool)
        hybrid_graph = _rrf_fuse(
            [
                ("lexical", lexical_cands, 0.55),
                ("dense", dense_cands, 4.0),
                ("graph_first", graph_first_cands, 2.5),
                ("graph", graph_cands, 1.5),
            ],
            limit=pool,
        )

        mode_results = {
            "dense_only": dense_cands,
            "lexical_only": lexical_cands,
            "graph_first": graph_first_cands,
            "dense_plus_lexical": dense_plus_lexical,
            "hybrid_graph": hybrid_graph,
        }
        for mode, candidates in mode_results.items():
            rows.append(
                _score_row(
                    expectation=exp,
                    mode=mode,
                    candidates=candidates[:top_k],
                    dense_status=dense.status,
                    graph_status=graph_expander.status,
                    top_k=top_k,
                    corpus_ids=corpus_ids,
                )
            )

    summary = _summarize(rows)
    return {
        "metadata": {
            "goldens_path": str(goldens_path),
            "coverage_matrix_path": str(coverage_matrix_path),
            "index_manifest_path": str(index_manifest_path),
            "top_k": top_k,
            "case_count": len(expectations),
            "dense_status": dense.status,
            "graph_status": graph_expander.status,
            "index_status": index_manifest.get("status"),
            "qdrant_collection": index_manifest.get("collection_name"),
        },
        "summary": summary,
        "rows": rows,
    }


def write_outputs(
    *,
    result: dict[str, Any],
    output_csv: Path,
    output_json: Path,
    output_md: Path,
) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(result["rows"])

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown_report(result), encoding="utf-8")


def render_markdown_report(result: dict[str, Any]) -> str:
    metadata = result["metadata"]
    summary = result["summary"]
    lines = [
        "# Retrieval Mode Comparison",
        "",
        "Compares dense Qdrant search, lexical BM25 search, graph-first concept lookup, RRF hybrid without graph, and the live graph-expansion hybrid path.",
        "",
        "## Run Metadata",
        "",
        f"- Cases: `{metadata['case_count']}`",
        f"- Top-k: `{metadata['top_k']}`",
        f"- Dense status: `{metadata['dense_status']}`",
        f"- Graph status: `{metadata['graph_status']}`",
        f"- Index status: `{metadata['index_status']}`",
        f"- Qdrant: `{metadata.get('qdrant_collection')}`",
        "",
        "## Summary",
        "",
        "| Mode | Cases | Top-1 family | Top-5 family | Top-1 id | Top-3 id | Top-5 id |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for mode in MODES:
        item = summary.get(mode, {})
        lines.append(
            "| {mode} | {cases} | {f1:.1%} | {f5:.1%} | {i1:.1%} | {i3:.1%} | {i5:.1%} |".format(
                mode=mode,
                cases=item.get("cases", 0),
                f1=item.get("source_family_hit_top1_rate", 0.0),
                f5=item.get("source_family_hit_top5_rate", 0.0),
                i1=item.get("expected_id_hit_top1_rate", 0.0),
                i3=item.get("expected_id_hit_top3_rate", 0.0),
                i5=item.get("expected_id_hit_top5_rate", 0.0),
            )
        )
    lines.extend(
        [
            "",
            "## Per-Case Top Results",
            "",
            "| Case | Mode | Top source | Top card | Family hit | ID hit@5 | Miss type | Top title |",
            "|---|---|---|---|---:|---:|---|---|",
        ]
    )
    for row in result["rows"]:
        lines.append(
            "| {case} | {mode} | {family} | `{card}` | {fhit} | {ihit} | {miss} | {title} |".format(
                case=row["case_id"],
                mode=row["mode"],
                family=row["top1_source_family"],
                card=row["top1_card_id"],
                fhit=row["source_family_hit_top1"],
                ihit=row["expected_id_hit_top5"],
                miss=row["retrieval_miss_type"],
                title=_escape_md(row["top1_title"])[:120],
            )
        )
    lines.append("")
    return "\n".join(lines)


def _load_expectations(
    *,
    goldens: list[dict[str, Any]],
    matrix: dict[str, Any],
) -> list[CaseExpectation]:
    matrix_by_id = {str(c.get("case_id")): c for c in matrix.get("cases", [])}
    result: list[CaseExpectation] = []
    for case in goldens:
        case_id = str(case.get("id"))
        mc = matrix_by_id.get(case_id, {})
        expected_ids = _split_ids(mc.get("source_id") or mc.get("card_id") or "")
        card_id = str(mc.get("card_id") or "")
        if card_id:
            expected_ids.extend(_split_ids(card_id))
        result.append(
            CaseExpectation(
                case_id=case_id,
                query=str(case.get("query_ru") or mc.get("query_ru") or ""),
                expected_terminal_outcome=str(
                    mc.get("expected_terminal_outcome")
                    or case.get("expected_terminal_behavior")
                    or ""
                ),
                expected_source_family=str(mc.get("source_family") or ""),
                expected_source_ids=sorted(set(expected_ids)),
            )
        )
    return result


def _score_row(
    *,
    expectation: CaseExpectation,
    mode: str,
    candidates: list[RetrievalCandidate],
    dense_status: str,
    graph_status: str,
    top_k: int,
    corpus_ids: set[str],
) -> dict[str, Any]:
    top = candidates[0] if candidates else None
    top3 = candidates[: min(3, top_k)]
    top5 = candidates[:top_k]
    ef = expectation.expected_source_family
    return {
        "case_id": expectation.case_id,
        "mode": mode,
        "query": expectation.query,
        "expected_terminal_outcome": expectation.expected_terminal_outcome,
        "expected_source_family": ef,
        "expected_source_ids": ";".join(expectation.expected_source_ids),
        "expected_id_in_corpus": _bool(_expected_id_in_corpus(expectation.expected_source_ids, corpus_ids)),
        "top1_card_id": top.card_id if top else "",
        "top1_title": top.title if top else "",
        "top1_source_family": top.source_family if top else "",
        "top1_score": f"{top.score:.6f}" if top else "0.000000",
        "top1_canonical_ids": ";".join(str(i) for i in _cand_ids(top)[:20]) if top else "",
        "top1_extraction_readiness": _readiness(top),
        "source_family_hit_top1": _bool(_family_hit([top] if top else [], ef)),
        "source_family_hit_top5": _bool(_family_hit(top5, ef)),
        "expected_id_hit_top1": _bool(_id_hit([top] if top else [], expectation.expected_source_ids)),
        "expected_id_hit_top3": _bool(_id_hit(top3, expectation.expected_source_ids)),
        "expected_id_hit_top5": _bool(_id_hit(top5, expectation.expected_source_ids)),
        "retrieval_miss_type": _miss_type(
            candidates=top5,
            expected_family=ef,
            expected_ids=expectation.expected_source_ids,
            family_hit_top1=_family_hit([top] if top else [], ef),
            family_hit_top5=_family_hit(top5, ef),
            id_hit_top1=_id_hit([top] if top else [], expectation.expected_source_ids),
            id_hit_top5=_id_hit(top5, expectation.expected_source_ids),
            expected_id_in_corpus=_expected_id_in_corpus(expectation.expected_source_ids, corpus_ids),
        ),
        "candidate_count": len(candidates),
        "dense_status": dense_status,
        "graph_status": graph_status,
        "top5_card_ids": ";".join(c.card_id for c in top5),
        "top5_titles": " || ".join(c.title for c in top5),
    }


def _graph_neighbours_from_dense(
    graph_expander: GraphExpander,
    dense_cands: list[RetrievalCandidate],
    *,
    pool: int,
) -> list[RetrievalCandidate]:
    """Return graph neighbour candidates using the same expansion layer as runtime retrieval."""

    if not dense_cands or graph_expander.status != "ready":
        return []
    seed_card_ids = [candidate.card_id for candidate in dense_cands[:20]]
    neighbour_cands, _subgraph = graph_expander.expand(seed_card_ids, hops=2)
    return neighbour_cands[:pool]


def _graph_first_candidates(
    graph: KnowledgeGraphStore,
    doc_by_card: dict[str, dict[str, Any]],
    query: str,
    *,
    pool: int,
) -> list[RetrievalCandidate]:
    candidates: list[RetrievalCandidate] = []
    for rank, card_id in enumerate(graph.graph_first_card_ids(query, limit=pool), start=1):
        doc = doc_by_card.get(card_id)
        if doc:
            candidates.append(
                _make_candidate(
                    doc,
                    retrieval_mode="graph_first",
                    score=1.0 / rank,
                    evidence=["graph_first"],
                )
            )
    return candidates


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_mode: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_mode[str(row["mode"])].append(row)
    summary: dict[str, Any] = {}
    for mode, mode_rows in by_mode.items():
        n = len(mode_rows)
        corpus_rows = [r for r in mode_rows if r.get("expected_id_in_corpus") == "true"]
        summary[mode] = {
            "cases": n,
            "source_family_hit_top1_rate": _rate(mode_rows, "source_family_hit_top1"),
            "source_family_hit_top5_rate": _rate(mode_rows, "source_family_hit_top5"),
            "expected_id_hit_top1_rate": _rate(mode_rows, "expected_id_hit_top1"),
            "expected_id_hit_top3_rate": _rate(mode_rows, "expected_id_hit_top3"),
            "expected_id_hit_top5_rate": _rate(mode_rows, "expected_id_hit_top5"),
            "corpus_present_cases": len(corpus_rows),
            "corpus_present_expected_id_hit_top1_rate": _rate(corpus_rows, "expected_id_hit_top1"),
            "corpus_present_expected_id_hit_top5_rate": _rate(corpus_rows, "expected_id_hit_top5"),
        }
    return summary


def _corpus_ids(documents: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for doc in documents:
        ids.update(_normalize_id(i) for i in extract_canonical_ids(doc) if i)
    return ids


def _cand_ids(cand: RetrievalCandidate | None) -> list[str]:
    if cand is None:
        return []
    meta_ids = [str(i) for i in cand.metadata.get("canonical_ids", []) if i]
    raw = [
        cand.card_id, cand.chunk_id,
        str(cand.metadata.get("provenance_url") or ""),
        str(cand.metadata.get("resource_url") or ""),
    ]
    return sorted({_normalize_id(v) for v in meta_ids + raw if v})


def _readiness(cand: RetrievalCandidate | None) -> str:
    if cand is None:
        return ""
    return str((cand.metadata.get("extraction_readiness") or {}).get("status") or "")


def _family_hit(candidates: list[RetrievalCandidate], expected: str) -> bool:
    if not expected:
        return False
    exp = expected.strip().casefold().replace(" ", "_")
    return any(c.source_family.casefold().replace(" ", "_") == exp for c in candidates)


def _id_hit(candidates: list[RetrievalCandidate], expected_ids: list[str]) -> bool:
    if not expected_ids:
        return False
    norm_exp = {_normalize_id(i) for i in expected_ids if i}
    for cand in candidates:
        haystack = set(_cand_ids(cand))
        if norm_exp & haystack:
            return True
    return False


def _expected_id_in_corpus(expected_ids: list[str], corpus_ids: set[str]) -> bool:
    if not expected_ids:
        return False
    return any(_normalize_id(i) in corpus_ids for i in expected_ids if i)


def _miss_type(
    *,
    candidates: list[RetrievalCandidate],
    expected_family: str,
    expected_ids: list[str],
    family_hit_top1: bool,
    family_hit_top5: bool,
    id_hit_top1: bool,
    id_hit_top5: bool,
    expected_id_in_corpus: bool,
) -> str:
    if not candidates:
        return "no_candidates"
    if id_hit_top1:
        return "exact_id_top1"
    if id_hit_top5:
        return "exact_id_in_top5_needs_rerank"
    if expected_ids and not expected_id_in_corpus:
        return "expected_id_absent_from_corpus"
    if not family_hit_top5:
        return "wrong_source_family"
    if family_hit_top5 and not family_hit_top1:
        return "right_family_in_top5_needs_rerank"
    if expected_family and family_hit_top1:
        return "neighbor_indicator_or_alias_mismatch"
    return "unclassified_miss"


def _split_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        parts = [str(i) for i in value]
    else:
        parts = str(value).split(",")
    return [p.strip() for p in parts if p.strip()]


def _normalize_id(value: str) -> str:
    return normalize_identifier(value)


def _rate(rows: list[dict[str, Any]], field: str) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if r.get(field) == "true") / len(rows)


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    main()
