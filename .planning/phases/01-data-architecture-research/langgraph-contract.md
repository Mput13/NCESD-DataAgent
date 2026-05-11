# LangGraph Contract

This is an executable Phase 1 slice, not a bypass around plan verification. `app/workflow/run_graph.py` runs representative golden cases, moves typed artifacts through the graph contract, and emits machine-readable trace JSON for downstream Streamlit diagnostics.

## Supervisor

The Supervisor owns triage, route selection, checkpoint policy, and final trace coordination. It emits `IntentFrame` and canonical `TraceEvent` records from `app/artifacts/workflow_artifacts.py`. Simple direct lookup can stay on the bounded direct path; ambiguous requests block extraction until the missing fields are explicit.

## Parallel scouts

The full locked role set is preserved in the node contract: FedStat Scout, World Bank Scout, and CKAN Scout. The narrow runnable path calls the prepared hybrid retrieval contract and records selected and rejected source-card candidates with Qdrant/index status. Research and no-data routes keep the fan-out shape so source rejection remains visible.

## Coverage and extraction

Coverage & Schema and Extraction Planner run before any numeric narration. The narrow path creates `CoverageReport`, `ExtractionPlan`, and `DatasetArtifact` placeholders with gated status when deterministic probes or prepared indexes are unavailable. Numeric values remain withheld until deterministic DuckDB/source-adapter tools return evidence.

## Critic and narrator

Methodology Critic checks that source selection, rejection reasons, coverage planning, extraction status, and no-data or gated states are present. Narrator emits a `FinalAnswer` artifact only from existing structured evidence and never from LLM numeric memory.

## Visualization and final answer

Visualization is a role in the contract and renders only from `DatasetArtifact`/`VisualizationSpec` when a deterministic dataset exists. In this plan it remains diagnostic: trace, artifact, and index-readiness evidence matter more than visual polish.

## Budgets and tool scopes

`graph_contract.py` defines per-node `budget` and `tool_scope` entries plus query budgets for `Direct lookup`, `Ambiguous lookup`, `Comparative query`, `Research query`, and `No-data check`. Direct lookup has the lowest tool-call limit; research and no-data routes allow scout fan-out and critic passes.

## Checkpoint and trace rules

`TraceEvent` ownership stays in `app/artifacts/workflow_artifacts.py`. Streamlit trace payloads are fed from `run_graph.py` and `graph_contract.py` through `workflow_artifacts.py`, not through a duplicate UI-local trace schema. Every runnable graph output must include selected sources or no-data/gated reasoning, rejected candidates where available, coverage/extraction planning, and Qdrant/index status.
