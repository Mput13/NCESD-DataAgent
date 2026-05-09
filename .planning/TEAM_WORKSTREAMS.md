# Team Workstreams: DataAgent

**Created:** 2026-05-09
**Status:** Coordination baseline for three-person GSD work

## Purpose

This document fixes the initial ownership model for parallel implementation. The goal is to let three people work through GSD independently while preserving one integrated source-bound DataAgent.

The split is by integration boundary, not by isolated demos. Every workstream must produce artifacts that fit the shared contracts and can be assembled into one end-to-end run.

## Workstream 1: Core / Integration Owner

Owns the application spine.

Responsibilities:

- Define and maintain shared typed contracts.
- Own the LangGraph/state-machine skeleton.
- Own the top-level `run_query(user_query) -> RunResult` integration API.
- Own Yandex AI Studio client integration boundaries.
- Keep trace propagation consistent across all nodes and tools.
- Run regular end-to-end integration checks.

Primary code areas:

- `app/contracts/` or `app/schemas.py`
- `app/workflow/`
- `app/llm/`
- integration tests and smoke runs

Key rule: changes to shared contracts go through the Core owner first. Other workstreams can propose contract changes, but should not silently reshape artifacts.

## Workstream 2: Data / Retrieval Owner

Owns real data, source discovery, coverage checks, and deterministic extraction.

Responsibilities:

- Build source adapters for World Bank, FedStat, and CKAN.
- Build catalog/search utilities over available metadata.
- Implement coverage preview before extraction.
- Implement deterministic numeric extraction via DuckDB/PyArrow/Polars.
- Emit source cards, rejection reasons, dataset artifacts, manifests, and source links.
- Ensure numbers come from code, not LLM memory or table reading.

Primary code areas:

- `app/data/`
- `app/retrieval/`
- `app/artifacts/manifest.py`
- data-focused tests and eval fixtures

MVP source stance:

- World Bank, FedStat, and CKAN are all in MVP scope.
- CKAN is a required source for discovery/catalog integration.
- Numeric extraction from CKAN resources is required only when the discovered resource is technically usable within the MVP timeline.

## Workstream 3: UI / Evaluation / Demo Owner

Owns the human-facing demonstration and quality harness.

Responsibilities:

- Build Streamlit demo UI.
- Show the state machine, trace, source choices, rejected sources, artifacts, and final answer.
- Provide example prompts and demo scenarios.
- Build golden eval cases and result summaries.
- Ensure README/run instructions are usable by a non-programmer evaluator.
- Surface user feedback and fix requests as artifacts.

Primary code areas:

- `app/ui/`
- `app/ui_state/`
- `app/artifacts/trace.py`
- `app/artifacts/feedback.py`
- `evals/`
- `README.md` / demo documentation

## Shared Contracts

The initial integration boundary should be Pydantic v2 artifacts. These are the minimum shared objects downstream planning should preserve:

- `IntentArtifact`
- `ResearchDesignArtifact`
- `SourceCandidateCard`
- `SourceRejection`
- `CoverageReport`
- `ExtractionPlan`
- `DatasetArtifact`
- `TraceEvent`
- `CritiqueReport`
- `FinalAnswer`
- `RunResult`

Plain dictionaries may be used internally inside a module, but cross-workstream APIs should use typed artifacts or JSON produced from those artifacts.

## GSD Coordination Rules

- Each person works through GSD for their workstream.
- Each plan declares touched paths before implementation.
- Shared files require extra care: contracts, requirements, README, `requirements.txt`, `.planning/STATE.md`, and phase context files.
- If a workstream needs a contract change, capture the reason in the relevant GSD context/plan before implementation.
- Integration owner regularly pulls the three streams together and verifies the end-to-end flow.
- A feature is not considered done until it preserves the source-bound invariant: numbers from deterministic code, source links attached, trace visible, and no-data cases handled honestly.

## Current Phase 1 Decisions Captured So Far

- Phase 1 should move from open-ended research to concrete architecture decisions and implementation planning.
- The team wants all three source families represented in MVP: World Bank, FedStat, and CKAN.
- CKAN should be treated as a required source, not merely a future option.
- The MVP eval target is broad: 15-20 test queries rather than only 5-8 curated prompts.
- The exact final `01-CONTEXT.md` is still in progress and should reference this coordination baseline.

---
*Created during Phase 1 discussion to prevent parallel GSD work from diverging.*
