# Trace UI Demo Contract

## State machine

The diagnostic Streamlit surface shows the workflow state from query receipt through triage, source scouting, coverage/extraction planning, critic/narrator, and feedback. Index states are visible as `building`, `ready`, `stale`, and `gated_skip` so long-running builds and missing credential gates are not hidden.

The state machine starts from the prepared index rather than reprocessing source metadata by default. `app/demo/run_demo.py` loads `source-cards-manifest.json`, `source-catalog-manifest.json`, `embedding-corpus-manifest.json`, `embedding-index-manifest.json`, `retrieval-eval.csv`, `extraction-probes.json`, and `data-relevance-eval.json`, then emits `demo-readiness.json` for the UI.

## Trace timeline

The timeline consumes canonical `TraceEvent` objects from `app/artifacts/workflow_artifacts.py` via `WorkflowTraceViewModel`. Each event shows state, agent, decision, tool calls, warnings, and artifact id without redefining the trace schema in UI code.

Trace timeline events must include prepared index status, Qdrant status, dense retrieval readiness, data relevance status, extraction evidence status, and warnings when the flow is blocked or `gated_skip`.

## Artifacts panel

The artifacts panel lists selected sources, rejected sources, coverage reports, extraction plans, DatasetArtifact exports, visualization specs, and Qdrant/index readiness. It is intentionally diagnostic and minimal; visual polish is deferred until data relevance and deterministic extraction are verified.

Artifacts panel sections should expose source links, rejected source reasons, retrieval evidence, extraction probe evidence, `demo-readiness.json`, and the rebuild command recorded in the embedding-index manifest. The rebuild command is a recovery path only; the normal demo flow should not rebuild or re-embed all source metadata.

## Feedback and fix requests

The UI captures `FeedbackRequest` and `FixRequest` payloads for user corrections such as source, period, coverage, or explanation changes. Fix requests target the nearest workflow state instead of restarting the whole graph by default.

Feedback and fix requests are diagnostic artifacts. A fix request should identify whether the user is correcting relevance, Qdrant/index readiness, coverage, extraction, source rejection, or explanation, so the next run can target the right state instead of starting from scratch.
