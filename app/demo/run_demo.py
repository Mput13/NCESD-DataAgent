from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.artifacts.workflow_artifacts import TraceEvent
from app.ui.trace_models import (
    FeedbackRequest,
    FixRequest,
    IndexStatusView,
    WorkflowTraceViewModel,
)


@dataclass(frozen=True)
class DemoInputs:
    source_cards_manifest: Path
    source_catalog_manifest: Path
    embedding_corpus_manifest: Path
    index_manifest: Path
    retrieval_eval: Path
    extraction_probes: Path
    data_relevance_eval: Path


def assess_demo_readiness(inputs: DemoInputs) -> dict[str, Any]:
    """Assess the prepared-data demo path without rebuilding or re-embedding."""

    source_cards = _load_json(inputs.source_cards_manifest)
    source_catalog = _load_json(inputs.source_catalog_manifest)
    embedding_corpus = _load_json(inputs.embedding_corpus_manifest)
    index_manifest = _load_json(inputs.index_manifest)
    retrieval_rows = _load_csv(inputs.retrieval_eval)
    extraction_probes = _load_json(inputs.extraction_probes)
    data_relevance_eval = _load_json(inputs.data_relevance_eval)

    source_cards_status = _source_cards_status(source_cards)
    source_catalog_status = _source_catalog_status(source_catalog)
    embedding_corpus_status = _embedding_corpus_status(embedding_corpus, source_cards)
    qdrant_status, qdrant_reason = _qdrant_status(index_manifest, embedding_corpus)
    retrieval_eval_status = _retrieval_eval_status(retrieval_rows, qdrant_status)
    extraction_eval_status = _extraction_eval_status(extraction_probes)
    data_relevance_status = _data_relevance_status(data_relevance_eval)
    trace_ui_status = "ready"

    blocked = [
        name
        for name, status in {
            "source_cards": source_cards_status,
            "source_catalog": source_catalog_status,
            "embedding_corpus": embedding_corpus_status,
            "qdrant": qdrant_status,
            "retrieval_eval": retrieval_eval_status,
            "extraction_eval": extraction_eval_status,
            "data_relevance_eval": data_relevance_status,
        }.items()
        if status in {"missing", "stale", "blocked"}
    ]
    gated = [
        name
        for name, status in {
            "qdrant": qdrant_status,
            "retrieval_eval": retrieval_eval_status,
            "extraction_eval": extraction_eval_status,
            "data_relevance_eval": data_relevance_status,
        }.items()
        if status == "gated"
    ]
    if qdrant_status == "gated_skip":
        gated.append("qdrant")
    overall_status = "blocked" if blocked else "gated" if gated else "ready"
    dense_retrieval_ready = qdrant_status == "ready"

    view_model = build_trace_view_model(
        readiness={
            "run_id": "phase1-demo-readiness",
            "qdrant_status": qdrant_status,
            "dense_retrieval_ready": dense_retrieval_ready,
            "qdrant_collection": index_manifest.get("collection_name"),
            "qdrant_reason": qdrant_reason,
            "selected_sources": _selected_source_examples(retrieval_rows),
            "rejected_sources": _rejected_source_examples(retrieval_rows),
            "overall_status": overall_status,
            "retrieval_eval_status": retrieval_eval_status,
            "extraction_eval_status": extraction_eval_status,
        },
        index_manifest=index_manifest,
    )

    return {
        "overall_status": overall_status,
        "source_cards_status": source_cards_status,
        "source_catalog_status": source_catalog_status,
        "embedding_corpus_status": embedding_corpus_status,
        "qdrant_status": qdrant_status,
        "qdrant_reason": qdrant_reason,
        "dense_retrieval_ready": dense_retrieval_ready,
        "retrieval_eval_status": retrieval_eval_status,
        "extraction_eval_status": extraction_eval_status,
        "data_relevance_eval_status": data_relevance_status,
        "trace_ui_status": trace_ui_status,
        "blocked_components": blocked,
        "gated_components": sorted(set(gated)),
        "prepared": {
            "source_card_count": source_cards.get("card_count"),
            "catalog_source_cards_count": source_catalog.get("source_cards_count"),
            "embedding_chunk_count": embedding_corpus.get("chunk_count"),
            "qdrant_collection": index_manifest.get("collection_name"),
            "qdrant_vector_count": index_manifest.get("vector_count"),
            "vector_store": index_manifest.get("vector_store"),
            "corpus_hash": embedding_corpus.get("content_hash"),
            "index_corpus_hash": index_manifest.get("corpus_hash"),
        },
        "artifacts": {
            "source_cards_manifest": str(inputs.source_cards_manifest),
            "source_catalog_manifest": str(inputs.source_catalog_manifest),
            "embedding_corpus_manifest": str(inputs.embedding_corpus_manifest),
            "embedding_index_manifest": str(inputs.index_manifest),
            "retrieval_eval": str(inputs.retrieval_eval),
            "extraction_probes": str(inputs.extraction_probes),
            "data_relevance_eval": str(inputs.data_relevance_eval),
            "build_log_path": index_manifest.get("build_log_path"),
            "rebuild_command": index_manifest.get("rebuild_command"),
        },
        "evidence": {
            "retrieval_rows": len(retrieval_rows),
            "data_relevance_total_cases": data_relevance_eval.get("total_cases"),
            "data_relevance_gated": data_relevance_eval.get("gated"),
            "data_relevance_failed": data_relevance_eval.get("failed"),
            "extraction_probe_count": extraction_probes.get("probe_count"),
            "missing_env_vars": index_manifest.get("missing_env_vars", []),
        },
        "trace_view_model": view_model.model_dump(),
        "rebuild_policy": "Do not rebuild or re-embed by default; use the recorded rebuild_command only when a manifest is missing or stale.",
    }


def build_trace_view_model(
    *, readiness: dict[str, Any], index_manifest: dict[str, Any]
) -> WorkflowTraceViewModel:
    """Create the diagnostic payload consumed by the Streamlit shell."""

    run_id = str(readiness.get("run_id") or "phase1-demo-readiness")
    qdrant_status = str(readiness.get("qdrant_status") or "gated_skip")
    index_state = "ready" if qdrant_status == "ready" else "gated_skip"
    events = [
        TraceEvent(
            run_id=run_id,
            state="prepared_index_check",
            agent="Demo readiness runner",
            tool_calls=[
                "source-cards-manifest",
                "source-catalog-manifest",
                "embedding-corpus-manifest",
                "embedding-index-manifest",
            ],
            output_artifact="demo-readiness.json",
            decision=qdrant_status,
            warnings=[str(readiness.get("qdrant_reason"))] if readiness.get("qdrant_reason") else [],
            payload={
                "prepared index": True,
                "Qdrant": qdrant_status,
                "data relevance": readiness.get("retrieval_eval_status"),
            },
        ),
        TraceEvent(
            run_id=run_id,
            state="evidence_gate",
            agent="Data relevance and deterministic extraction checks",
            tool_calls=["retrieval-eval.csv", "extraction-probes.json", "data-relevance-eval.json"],
            output_artifact="prepared-data-readiness.md",
            decision=str(readiness.get("overall_status")),
            payload={
                "retrieval_eval_status": readiness.get("retrieval_eval_status"),
                "extraction_eval_status": readiness.get("extraction_eval_status"),
                "dense_retrieval_ready": readiness.get("dense_retrieval_ready"),
            },
        ),
    ]
    return WorkflowTraceViewModel(
        run_id=run_id,
        index_status=IndexStatusView(
            state=index_state,  # type: ignore[arg-type]
            collection_name=str(index_manifest.get("collection_name") or ""),
            dense_status=qdrant_status,
            build_log_path=str(index_manifest.get("build_log_path") or ""),
            gated_reason=readiness.get("qdrant_reason"),
        ),
        trace_events=events,
        selected_sources=list(readiness.get("selected_sources") or []),
        rejected_sources=list(readiness.get("rejected_sources") or []),
        artifacts=[
            {"name": "demo-readiness.json", "kind": "readiness"},
            {"name": "retrieval-eval.csv", "kind": "retrieval"},
            {"name": "extraction-probes.json", "kind": "deterministic extraction"},
            {"name": "data-relevance-eval.json", "kind": "evaluation"},
        ],
        feedback=FeedbackRequest(run_id=run_id, artifact_id="demo-readiness.json"),
        fix_request=FixRequest(
            run_id=run_id,
            target_state="prepared_index_check",
            requested_change="Record source, coverage, or extraction correction before rerunning.",
        ),
    )


def _source_cards_status(manifest: dict[str, Any]) -> str:
    artifact = Path(str(manifest.get("artifact_path") or ""))
    if not artifact.exists():
        return "missing"
    if int(manifest.get("card_count") or 0) <= 0:
        return "blocked"
    return "ready"


def _source_catalog_status(manifest: dict[str, Any]) -> str:
    catalog = Path(str(manifest.get("catalog_path") or ""))
    if not catalog.exists():
        return "missing"
    if manifest.get("queryability_check") != "passed":
        return "blocked"
    return "ready"


def _embedding_corpus_status(corpus: dict[str, Any], source_cards: dict[str, Any]) -> str:
    artifact = Path(str(corpus.get("artifact_path") or ""))
    if not artifact.exists():
        return "missing"
    if corpus.get("chunk_count") != source_cards.get("embedding_chunk_count"):
        return "stale"
    return "ready"


def _qdrant_status(index: dict[str, Any], corpus: dict[str, Any]) -> tuple[str, str | None]:
    if index.get("vector_store") != "qdrant":
        return "blocked", "embedding-index-manifest is not backed by Qdrant"
    if not index.get("collection_name"):
        return "blocked", "embedding-index-manifest has no Qdrant collection_name"
    if index.get("corpus_hash") != corpus.get("content_hash"):
        return "stale", "embedding-index-manifest corpus_hash differs from embedding-corpus-manifest"
    status = str(index.get("status") or index.get("dense_status") or "unknown")
    if status == "ready" and int(index.get("vector_count") or 0) > 0:
        return "ready", None
    if status == "ready":
        return "blocked", "dense retrieval cannot be ready with zero Qdrant vectors"
    if status == "gated_skip" or index.get("dense_status") == "gated_skip":
        return "gated_skip", str(index.get("gate_reason") or "dense retrieval gated")
    return "blocked", f"unrecognized Qdrant status: {status}"


def _retrieval_eval_status(rows: list[dict[str, str]], qdrant_status: str) -> str:
    if not rows:
        return "missing"
    if qdrant_status != "ready":
        return "gated"
    if any(row.get("dense_status") != "ready" for row in rows):
        return "gated"
    return "ready"


def _extraction_eval_status(payload: dict[str, Any]) -> str:
    probes = payload.get("probes") or []
    if not probes:
        return "missing"
    if any(probe.get("coverage_status") != "ok" for probe in probes):
        return "blocked"
    if any(probe.get("extraction_status") != "ok" for probe in probes):
        return "gated"
    return "ready"


def _data_relevance_status(payload: dict[str, Any]) -> str:
    if not payload.get("cases"):
        return "missing"
    if payload.get("failed", 0):
        return "gated"
    if payload.get("gated", 0):
        return "gated"
    return "ready"


def _selected_source_examples(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []
    for row in rows:
        if row.get("top_candidate"):
            examples.append(
                {
                    "case_id": row.get("case_id", ""),
                    "card_id": row.get("top_candidate", ""),
                    "source_family": row.get("top_source_family", ""),
                    "retrieval_mode": row.get("retrieval_mode", ""),
                    "provenance_url": row.get("provenance_url", ""),
                }
            )
        if len(examples) >= 5:
            break
    return examples


def _rejected_source_examples(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rejected: list[dict[str, str]] = []
    for row in rows:
        reasons = row.get("rejection_reasons", "")
        if reasons:
            rejected.append({"case_id": row.get("case_id", ""), "rejection_reasons": reasons})
        if len(rejected) >= 5:
            break
    return rejected


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing_path": str(path)}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description="Assess Phase 1 prepared-data demo readiness.")
    parser.add_argument("--source-cards-manifest", required=True, type=Path)
    parser.add_argument("--source-catalog-manifest", required=True, type=Path)
    parser.add_argument("--embedding-corpus-manifest", required=True, type=Path)
    parser.add_argument("--index-manifest", required=True, type=Path)
    parser.add_argument("--retrieval-eval", required=True, type=Path)
    parser.add_argument("--extraction-probes", required=True, type=Path)
    parser.add_argument("--data-relevance-eval", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    args = parser.parse_args()

    result = assess_demo_readiness(
        DemoInputs(
            source_cards_manifest=args.source_cards_manifest,
            source_catalog_manifest=args.source_catalog_manifest,
            embedding_corpus_manifest=args.embedding_corpus_manifest,
            index_manifest=args.index_manifest,
            retrieval_eval=args.retrieval_eval,
            extraction_probes=args.extraction_probes,
            data_relevance_eval=args.data_relevance_eval,
        )
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "overall_status": result["overall_status"],
                "qdrant_status": result["qdrant_status"],
                "dense_retrieval_ready": result["dense_retrieval_ready"],
                "output": str(args.json_output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

