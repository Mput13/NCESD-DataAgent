from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from app.artifacts.workflow_artifacts import (
    CoverageReport,
    DatasetArtifact,
    EvidenceBundleArtifact,
    ExtractionPlan,
    FinalAnswer,
    IntentFrame,
    ResearchDesignArtifact,
    SourceRejectionRecord,
)
from app.retrieval.hybrid_retrieval import HybridRetriever
from app.workflow.graph_contract import (
    GraphState,
    append_trace,
    build_checkpoint_graph,
    build_initial_state,
    route_from_category,
)

VALID_CATEGORIES = {"simple", "comparative", "research", "derived_metric", "ambiguous", "no_data"}


def run_golden_case(
    *,
    goldens_path: Path,
    case_index: int,
    index_manifest_path: Path,
) -> dict[str, Any]:
    cases = yaml.safe_load(goldens_path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"No golden cases found in {goldens_path}")
    case = cases[case_index]
    state = build_initial_state(str(case["query_ru"]), case_id=str(case["id"]))
    state.intent = _intent_from_case(case)
    state.route = route_from_category(
        state.intent.category,
        needs_clarification=state.intent.needs_clarification,
    )
    append_trace(
        state,
        state_name="triage",
        agent="Supervisor",
        decision=state.route,
        output_artifact="IntentFrame",
        payload={"category": state.intent.category},
    )
    if state.route in {"Research query", "Comparative query", "No-data check"}:
        state.research_design = ResearchDesignArtifact(
            artifact_id=f"{state.run_id}:research-design",
            route=state.route,
            hypotheses=["Use source-card retrieval before deterministic extraction."],
            dimensions=["geography", "period", "indicator"],
            indicators=list(case.get("expected_sources", [])),
            assumptions=["Representative Phase 1 slice uses prepared retrieval artifacts."],
        )
        append_trace(
            state,
            state_name="research_design",
            agent="Research Designer",
            decision="design_ready",
            output_artifact=state.research_design.artifact_id,
        )
    _run_retrieval(state, case, index_manifest_path=index_manifest_path)
    _plan_coverage_and_extraction(state)
    graph = build_checkpoint_graph()
    state = graph.invoke(state)
    return _state_to_output(state)


def _intent_from_case(case: dict[str, Any]) -> IntentFrame:
    missing_fields: list[str] = []
    if case.get("needs_clarification"):
        missing_fields = ["source/methodology choice or missing query bounds"]
    raw_category = str(case.get("category", "simple"))
    category = raw_category if raw_category in VALID_CATEGORIES else "simple"
    return IntentFrame(
        query=str(case["query_ru"]),
        category=category,
        known_fields={
            "expected_route": case.get("expected_route"),
            "expected_sources": case.get("expected_sources", []),
        },
        missing_fields=missing_fields,
        needs_clarification=bool(case.get("needs_clarification")),
        source_preferences=list(case.get("expected_sources", [])),
        open_reasoning=["Source selection must be backed by retrieval and coverage evidence."],
    )


def _run_retrieval(
    state: GraphState,
    case: dict[str, Any],
    *,
    index_manifest_path: Path,
) -> None:
    manifest = json.loads(index_manifest_path.read_text(encoding="utf-8"))
    state.qdrant_status = str(manifest.get("status") or manifest.get("dense_status") or "unknown")
    try:
        result = HybridRetriever(index_manifest_path).search(
            state.query,
            expected_sources=list(case.get("expected_sources", [])),
            limit=5,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        state.status = "gated"
        state.evidence = EvidenceBundleArtifact(
            retrieval_status="gated",
            qdrant_status=state.qdrant_status,
            dense_status=str(manifest.get("dense_status") or state.qdrant_status),
        )
        state.no_data_reason = f"prepared index gated: {exc}"
        append_trace(
            state,
            state_name="parallel_scouts",
            agent="Supervisor",
            decision="gated_index",
            tool_calls=["HybridRetriever"],
            warnings=[state.no_data_reason],
            payload={"qdrant_status": state.qdrant_status},
        )
        return

    selected = [_candidate_to_dict(candidate) for candidate in result.candidates]
    rejected = [_candidate_to_dict(candidate) for candidate in result.rejected_candidates]
    state.qdrant_status = result.index_manifest_status
    state.evidence = EvidenceBundleArtifact(
        selected_sources=selected,
        rejected_sources=rejected,
        retrieval_status="ok" if selected else "no_candidate",
        qdrant_status=result.index_manifest_status,
        dense_status=result.dense_status,
    )
    state.source_rejections = [
        SourceRejectionRecord(
            candidate_id=item.get("card_id", ""),
            source_family=item.get("source_family"),
            title=item.get("title"),
            rejection_reason="; ".join(item.get("rejection_reasons") or ["not selected"]),
        )
        for item in rejected
    ]
    if not selected and not rejected:
        state.status = "gated" if result.dense_status != "ready" else "no_data"
        state.no_data_reason = "No selected source-card candidates were returned."
    append_trace(
        state,
        state_name="parallel_scouts",
        agent="FedStat Scout, World Bank Scout, CKAN Scout",
        decision="retrieval_complete",
        tool_calls=["HybridRetriever", "Qdrant status check"],
        output_artifact="EvidenceBundleArtifact",
        payload={
            "selected_sources": selected,
            "rejected_sources": rejected,
            "qdrant_status": state.qdrant_status,
        },
    )


def _plan_coverage_and_extraction(state: GraphState) -> None:
    selected = state.evidence.selected_sources
    first_source = selected[0].get("card_id", "") if selected else None
    if not first_source:
        state.coverage_report = CoverageReport(
            source_id="none",
            status="gated" if state.status == "gated" else "no_data",
            checks=["selected_sources", "qdrant_status"],
            evidence={"qdrant_status": state.qdrant_status},
            gated_reason=state.no_data_reason,
        )
        state.extraction_plan = ExtractionPlan(
            artifact_id=f"{state.run_id}:extraction-plan",
            source_id=None,
            status="gated" if state.status == "gated" else "skipped_with_reason",
            operations=[],
            skip_reason=state.no_data_reason or "No candidate selected for extraction.",
        )
    else:
        state.coverage_report = CoverageReport(
            source_id=first_source,
            status="gated",
            checks=["coverage_preview", "schema_preview", "source_bound_extraction"],
            evidence={"selected_source": first_source, "reason": "deterministic probe pending"},
            gated_reason="Plan 01-04 narrow graph records coverage planning before extraction probes.",
        )
        state.extraction_plan = ExtractionPlan(
            artifact_id=f"{state.run_id}:extraction-plan",
            source_id=first_source,
            status="gated",
            operations=["coverage_preview", "DuckDB SQL-first extraction planning"],
            skip_reason="Deterministic extraction executes through Plan 01-04 probes.",
        )
    state.dataset_artifact = DatasetArtifact(
        artifact_id=f"{state.run_id}:dataset",
        status=state.extraction_plan.status,
        source_id=first_source,
        provenance=[{"source_id": first_source}] if first_source else [],
        quality_flags=["no_numeric_values_without_deterministic_extraction"],
    )
    append_trace(
        state,
        state_name="coverage_and_extraction",
        agent="Coverage & Schema, Extraction Planner, Deterministic Tools",
        decision=state.extraction_plan.status,
        tool_calls=["coverage_preview", "run_duckdb_query"],
        output_artifact=state.extraction_plan.artifact_id,
        payload={
            "coverage_status": state.coverage_report.status,
            "extraction_status": state.extraction_plan.status,
        },
    )
    final_status = state.status if state.status == "gated" else "ok"
    state.final_answer = FinalAnswer(
        artifact_id=f"{state.run_id}:final-answer",
        status=final_status,
        summary="Phase 1 graph emitted source-bound trace artifacts; numeric narration is withheld until deterministic extraction returns data.",
        source_ids=[first_source] if first_source else [],
        dataset_artifact_id=state.dataset_artifact.artifact_id,
        no_data_reason=state.no_data_reason,
        clarification_question=(
            "Уточните недостающие параметры запроса."
            if state.intent and state.intent.needs_clarification
            else None
        ),
    )
    append_trace(
        state,
        state_name="critic_and_narrator",
        agent="Methodology Critic, Narrator, Visualization",
        decision=final_status,
        output_artifact=state.final_answer.artifact_id,
    )


def _candidate_to_dict(candidate: Any) -> dict[str, Any]:
    return {
        "card_id": candidate.card_id,
        "chunk_id": candidate.chunk_id,
        "source_family": candidate.source_family,
        "title": candidate.title,
        "retrieval_mode": candidate.retrieval_mode,
        "relevance_score": candidate.relevance_score,
        "evidence_keywords": candidate.evidence_keywords,
        "rejection_reasons": candidate.rejection_reasons,
        "provenance_url": candidate.metadata.get("provenance_url"),
    }


def _state_to_output(state: GraphState) -> dict[str, Any]:
    return {
        "run_id": state.run_id,
        "case_id": state.case_id,
        "status": "gated" if state.status == "gated" else "ok",
        "route": state.route,
        "qdrant_status": state.qdrant_status,
        "intent": state.intent.model_dump() if state.intent else None,
        "selected_sources": state.evidence.selected_sources,
        "rejected_sources": state.evidence.rejected_sources,
        "source_rejections": [item.model_dump() for item in state.source_rejections],
        "coverage_status": state.coverage_report.status if state.coverage_report else None,
        "extraction_status": state.extraction_plan.status if state.extraction_plan else None,
        "dataset_artifact": state.dataset_artifact.model_dump() if state.dataset_artifact else None,
        "final_answer": state.final_answer.model_dump() if state.final_answer else None,
        "no_data_reason": state.no_data_reason,
        "trace_events": [event.model_dump() for event in state.trace_events],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 1 narrow workflow graph.")
    parser.add_argument("--goldens", required=True, type=Path)
    parser.add_argument("--case-index", required=True, type=int)
    parser.add_argument("--index-manifest", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    args = parser.parse_args()

    result = run_golden_case(
        goldens_path=args.goldens,
        case_index=args.case_index,
        index_manifest_path=args.index_manifest,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps({"status": result["status"], "output": str(args.json_output)}))


if __name__ == "__main__":
    main()
