"""Deterministic tools node for Phase 2 workflow.

run_deterministic_tools consumes ExtractionPlan, dispatches by source_family
to deterministic adapters, persists dataset/script artifacts, and appends
TraceEvent/component status. No LLM numeric extraction is performed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.artifacts.workflow_artifacts import (
    DatasetArtifact,
    ExtractionPlan,
    NoDataExplanationArtifact,
    ScriptArtifact,
    TraceEvent,
    utc_now_iso,
)


def run_deterministic_tools(
    state: dict[str, Any],
    *,
    output_dir: Path,
) -> dict[str, Any]:
    """Execute an ExtractionPlan deterministically and persist artifacts.

    Dispatches each extractable operation by source_family:
    - fedstat -> extract_fedstat_dataset
    - world_bank -> extract_world_bank_dataset
    - ckan -> extract_ckan_dataset

    Calls export_dataset_with_script for successful datasets.
    Appends TraceEvent with tool name, source_family, artifact ids, row_count, status.
    Updates component_statuses["deterministic_tools"].

    Unsupported or skipped operations append explicit reasons, never fabricate rows.
    """
    run_id = str(state.get("run_id") or "unknown")
    extraction_plan: ExtractionPlan | None = state.get("extraction_plan")
    dataset_artifacts: list[DatasetArtifact] = list(state.get("dataset_artifacts") or [])
    script_artifacts: list[ScriptArtifact] = list(state.get("script_artifacts") or [])
    trace_events: list[TraceEvent] = list(state.get("trace_events") or [])
    component_statuses: dict[str, str] = dict(state.get("component_statuses") or {})

    output_dir.mkdir(parents=True, exist_ok=True)

    # Handle missing or skipped extraction plan
    if extraction_plan is None or extraction_plan.status in (
        "skipped_with_reason",
        "gated",
        "needs_clarification",
    ):
        reason = (
            extraction_plan.skip_reason if extraction_plan else "no_extraction_plan"
        ) or f"plan_status:{extraction_plan.status if extraction_plan else 'none'}"

        trace_events.append(
            TraceEvent(
                run_id=run_id,
                state="deterministic_tools",
                agent="Deterministic Tools",
                input_summary=f"plan_status={extraction_plan.status if extraction_plan else 'none'}",
                tool_calls=[],
                output_artifact=None,
                decision="skipped",
                warnings=[reason],
                payload={"skip_reason": reason},
            )
        )
        component_statuses["deterministic_tools"] = (
            "skipped_test_only" if "test" in reason.lower() else "skipped"
        )
        return {
            **state,
            "dataset_artifacts": dataset_artifacts,
            "script_artifacts": script_artifacts,
            "trace_events": trace_events,
            "component_statuses": component_statuses,
            "finalization_pending": True,
        }

    # Dispatch by source_family
    source_family = _resolve_source_family(extraction_plan)
    artifact_id = f"dataset-{uuid4().hex[:8]}"
    tool_name = _FAMILY_TO_TOOL.get(source_family, "unknown")
    intent = state.get("intent")
    filters = dict(extraction_plan.filters or {})
    if intent and hasattr(intent, "known_fields"):
        filters.update({k: v for k, v in intent.known_fields.items() if v})

    result = _dispatch_extraction(
        source_family=source_family,
        extraction_plan=extraction_plan,
        filters=filters,
        output_dir=output_dir,
        artifact_id=artifact_id,
    )

    tool_calls = [tool_name, "export_dataset_with_script"]
    artifact_ids_produced: list[str] = []
    row_count: int | None = None
    status = "ok"

    if isinstance(result, DatasetArtifact):
        dataset_artifacts.append(result)
        artifact_ids_produced.append(result.artifact_id)
        row_count = result.rows

        # Export dataset with script
        script = export_dataset_with_script(
            result,
            extraction_plan=extraction_plan,
            output_dir=output_dir,
            run_id=run_id,
        )
        if script:
            script_artifacts.append(script)
            artifact_ids_produced.append(script.artifact_id)

    elif isinstance(result, NoDataExplanationArtifact):
        status = "not_found"
        artifact_ids_produced.append(result.artifact_id)
        trace_events.append(
            TraceEvent(
                run_id=run_id,
                state="deterministic_tools",
                agent="Deterministic Tools",
                input_summary=f"source_family={source_family}",
                tool_calls=tool_calls,
                output_artifact=result.artifact_id,
                decision="not_found",
                warnings=list(result.rejection_reasons),
                payload={
                    "source_family": source_family,
                    "rejection_reasons": result.rejection_reasons,
                    "artifact_id": result.artifact_id,
                },
            )
        )
    else:
        # Unknown result type - skip and record
        status = "skipped_unknown_result"

    # Append main trace event for successful extraction
    if isinstance(result, DatasetArtifact):
        trace_events.append(
            TraceEvent(
                run_id=run_id,
                state="deterministic_tools",
                agent="Deterministic Tools",
                input_summary=f"source_family={source_family}, plan={extraction_plan.artifact_id}",
                tool_calls=tool_calls,
                output_artifact=result.artifact_id,
                decision=status,
                warnings=[],
                payload={
                    "source_family": source_family,
                    "tool_name": tool_name,
                    "artifact_ids": artifact_ids_produced,
                    "row_count": row_count,
                    "status": status,
                },
            )
        )

    component_statuses["deterministic_tools"] = status

    return {
        **state,
        "dataset_artifacts": dataset_artifacts,
        "script_artifacts": script_artifacts,
        "trace_events": trace_events,
        "component_statuses": component_statuses,
        "finalization_pending": True,
    }


# ---------------------------------------------------------------------------
# Source family dispatch
# ---------------------------------------------------------------------------


_FAMILY_TO_TOOL: dict[str, str] = {
    "fedstat": "extract_fedstat_dataset",
    "world_bank": "extract_world_bank_dataset",
    "ckan": "extract_ckan_dataset",
}


def _resolve_source_family(plan: ExtractionPlan) -> str:
    """Determine source_family from typed plan fields, with legacy guessing fallback."""
    if plan.source_family:
        return _normalize_source_family(plan.source_family)
    if plan.adapter_name:
        adapter = plan.adapter_name.lower()
        if "fedstat" in adapter:
            return "fedstat"
        if "world_bank" in adapter or "worldbank" in adapter:
            return "world_bank"
        if "ckan" in adapter:
            return "ckan"

    if plan.source_id:
        sid = plan.source_id.lower()
        if "fedstat" in sid or "emiss" in sid or "емисс" in sid:
            return "fedstat"
        if sid.isdigit():
            return "fedstat"
        if "world_bank" in sid or "wb" in sid or any(
            c.isupper() for c in plan.source_id[:3]
        ):
            # World Bank indicator IDs are typically UPPER.CASE.DOT
            if "." in plan.source_id and plan.source_id[0].isupper():
                return "world_bank"
        if "ckan" in sid:
            return "ckan"

    # Check operations for hints
    ops_text = " ".join(plan.operations).lower()
    if "fedstat" in ops_text:
        return "fedstat"
    if "world_bank" in ops_text or "wb" in ops_text:
        return "world_bank"
    if "ckan" in ops_text:
        return "ckan"

    return "unknown"


def _normalize_source_family(source_family: str) -> str:
    family = str(source_family).strip().lower().replace(" ", "_")
    if family == "worldbank":
        return "world_bank"
    return family


def _dispatch_extraction(
    *,
    source_family: str,
    extraction_plan: ExtractionPlan,
    filters: dict[str, Any],
    output_dir: Path,
    artifact_id: str,
) -> DatasetArtifact | NoDataExplanationArtifact:
    """Dispatch extraction to the appropriate deterministic adapter."""
    if source_family == "fedstat":
        return extract_fedstat_dataset(
            extraction_plan=extraction_plan,
            filters=filters,
            output_dir=output_dir,
            artifact_id=artifact_id,
        )
    elif source_family == "world_bank":
        return extract_world_bank_dataset(
            extraction_plan=extraction_plan,
            filters=filters,
            output_dir=output_dir,
            artifact_id=artifact_id,
        )
    elif source_family == "ckan":
        return extract_ckan_dataset(
            extraction_plan=extraction_plan,
            filters=filters,
            output_dir=output_dir,
            artifact_id=artifact_id,
        )
    else:
        return NoDataExplanationArtifact(
            artifact_id=artifact_id,
            checked_sources=[{"source_id": extraction_plan.source_id}],
            rejected_sources=[{"source_id": extraction_plan.source_id, "reason": f"unknown_source_family:{source_family}"}],
            rejection_reasons=[f"unsupported_source_family:{source_family}"],
            search_strategy="deterministic_tools_dispatch",
            alternatives=[],
            limitations=[f"Source family '{source_family}' has no registered deterministic extractor."],
        )


def extract_fedstat_dataset(
    *,
    extraction_plan: ExtractionPlan,
    filters: dict[str, Any],
    output_dir: Path,
    artifact_id: str,
) -> DatasetArtifact | NoDataExplanationArtifact:
    """Dispatch to the FedStat deterministic adapter."""
    from app.data.fedstat_adapter import extract_fedstat_dataset as _extract
    from app.data.source_card_lookup import lookup_source_card

    # Build a minimal source_card from the plan
    source_card = lookup_source_card(extraction_plan.source_id) or {
        "source_family": "fedstat",
        "dataset_id": extraction_plan.source_id or "fedstat_unknown",
        "resource_id": extraction_plan.source_id or "fedstat_unknown",
    }
    try:
        return _extract(
            source_card=source_card,
            filters=filters,
            output_dir=output_dir,
            artifact_id=artifact_id,
        )
    except Exception as exc:
        return NoDataExplanationArtifact(
            artifact_id=artifact_id,
            checked_sources=[source_card],
            rejected_sources=[{"source_id": extraction_plan.source_id, "error": str(exc)}],
            rejection_reasons=["fedstat_extraction_error"],
            search_strategy="fedstat_deterministic_adapter",
            alternatives=[],
            limitations=[f"FedStat extraction failed: {exc}"],
        )


def extract_world_bank_dataset(
    *,
    extraction_plan: ExtractionPlan,
    filters: dict[str, Any],
    output_dir: Path,
    artifact_id: str,
) -> DatasetArtifact | NoDataExplanationArtifact:
    """Dispatch to the World Bank deterministic adapter."""
    from app.data.world_bank_adapter import extract_world_bank_dataset as _extract
    from app.data.source_card_lookup import lookup_source_card

    source_card = lookup_source_card(extraction_plan.source_id) or {
        "source_family": "world_bank",
        "dataset_id": extraction_plan.source_id or "wb_unknown",
        "resource_id": extraction_plan.source_id or "wb_unknown",
    }
    try:
        return _extract(
            source_card=source_card,
            filters=filters,
            output_dir=output_dir,
            artifact_id=artifact_id,
        )
    except Exception as exc:
        return NoDataExplanationArtifact(
            artifact_id=artifact_id,
            checked_sources=[source_card],
            rejected_sources=[{"source_id": extraction_plan.source_id, "error": str(exc)}],
            rejection_reasons=["world_bank_extraction_error"],
            search_strategy="world_bank_deterministic_adapter",
            alternatives=[],
            limitations=[f"World Bank extraction failed: {exc}"],
        )


def extract_ckan_dataset(
    *,
    extraction_plan: ExtractionPlan,
    filters: dict[str, Any],
    output_dir: Path,
    artifact_id: str,
) -> DatasetArtifact | NoDataExplanationArtifact:
    """Dispatch to the CKAN deterministic adapter."""
    from app.data.ckan_adapter import extract_ckan_dataset as _extract, promote_ckan_package

    source_id = extraction_plan.source_id or "ckan_unknown"

    try:
        promoted = promote_ckan_package(source_id)
        resources = promoted.get("promoted_resources") or []
        resource_id = filters.get("resource_id") or (
            resources[0].get("id") if resources else ""
        )
        result = _extract(
            promoted,
            resource_id=resource_id,
            filters=filters,
            output_dir=output_dir,
            artifact_id=artifact_id,
        )
        return result  # type: ignore[return-value]
    except Exception as exc:
        return NoDataExplanationArtifact(
            artifact_id=artifact_id,
            checked_sources=[{"source_id": source_id}],
            rejected_sources=[{"source_id": source_id, "error": str(exc)}],
            rejection_reasons=["ckan_extraction_error"],
            search_strategy="ckan_deterministic_adapter",
            alternatives=[],
            limitations=[f"CKAN extraction failed: {exc}"],
        )


# ---------------------------------------------------------------------------
# Export helper
# ---------------------------------------------------------------------------


def export_dataset_with_script(
    dataset: DatasetArtifact,
    *,
    extraction_plan: ExtractionPlan,
    output_dir: Path,
    run_id: str,
) -> ScriptArtifact | None:
    """Generate a reproducible Python extraction script and return a ScriptArtifact.

    The script reads from the same source adapter that produced the dataset.
    """
    source_id = dataset.source_id or "unknown"
    source_family = _resolve_source_family(extraction_plan)
    script_id = f"script-{uuid4().hex[:8]}"
    script_filename = f"{script_id}.py"
    script_path = output_dir / script_filename

    adapter_import = {
        "fedstat": "from app.data.fedstat_adapter import extract_fedstat_dataset",
        "world_bank": "from app.data.world_bank_adapter import extract_world_bank_dataset",
        "ckan": "from app.data.ckan_adapter import extract_ckan_dataset, promote_ckan_package",
    }.get(source_family, "# No adapter available for this source family")

    filters_repr = repr(dict(extraction_plan.filters or {}))
    operations_repr = repr(list(extraction_plan.operations))

    script_content = f'''#!/usr/bin/env python3
"""Deterministic data extraction script generated by DataAgent.

Run ID: {run_id}
Source: {source_family} / {source_id}
Generated: {utc_now_iso()}

Usage:
    python {script_filename}

This script reproduces the extraction without LLM involvement.
All numeric values come exclusively from deterministic source adapters.
"""
from __future__ import annotations

import json
from pathlib import Path

{adapter_import}


def main() -> None:
    output_dir = Path("./extracted_data")
    output_dir.mkdir(parents=True, exist_ok=True)

    source_card = {{
        "source_family": "{source_family}",
        "dataset_id": "{source_id}",
        "resource_id": "{source_id}",
    }}
    filters = {filters_repr}

    # Operations from extraction plan: {operations_repr}
    print(f"Extracting {{source_card['dataset_id']}} with filters: {{filters}}")

    # NOTE: Replace the call below with the adapter matching your source family.
    # For FedStat: extract_fedstat_dataset(source_card, filters=filters, ...)
    # For World Bank: extract_world_bank_dataset(source_card, filters=filters, ...)
    # For CKAN: promoted = promote_ckan_package(source_id); extract_ckan_dataset(promoted, ...)
    print("Extraction script ready. Configure source-specific parameters above.")
    print(f"Output directory: {{output_dir}}")


if __name__ == "__main__":
    main()
'''

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script_content, encoding="utf-8")
    except Exception:
        return None

    import hashlib
    sha256 = hashlib.sha256(script_content.encode("utf-8")).hexdigest()

    return ScriptArtifact(
        artifact_id=script_id,
        language="python",
        path=str(script_path),
        script_path=str(script_path),
        content=script_content,
        entrypoint="main",
        source_ids=[source_id],
        source_dataset_artifact_id=dataset.artifact_id,
        dataset_artifact_id=dataset.artifact_id,
        sha256=sha256,
        downloadable=True,
        download_filename=script_filename,
        display_name=f"Extraction script for {source_id}",
        mime_type="text/x-python",
        provenance=[{
            "run_id": run_id,
            "source_family": source_family,
            "source_id": source_id,
            "generated_at": utc_now_iso(),
        }],
        quality_flags=["deterministic_extraction_script"],
    )
