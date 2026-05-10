# Trace UI Demo Contract

## State machine

The diagnostic Streamlit surface should show the workflow state from query receipt through triage, source scouting, coverage/extraction planning, critic/narrator, and feedback. Index states are visible as `building`, `ready`, `stale`, and `gated_skip` so long-running builds and missing credential gates are not hidden.

## Trace timeline

The timeline consumes canonical `TraceEvent` objects from `app/artifacts/workflow_artifacts.py` via `WorkflowTraceViewModel`. Each event shows state, agent, decision, tool calls, warnings, and artifact id without redefining the trace schema in UI code.

## Artifacts panel

The artifacts panel lists selected sources, rejected sources, coverage reports, extraction plans, DatasetArtifact exports, visualization specs, and Qdrant/index readiness. It is intentionally diagnostic and minimal; visual polish is deferred until data relevance and deterministic extraction are verified.

## Feedback and fix requests

The UI captures `FeedbackRequest` and `FixRequest` payloads for user corrections such as source, period, coverage, or explanation changes. Fix requests target the nearest workflow state instead of restarting the whole graph by default.
