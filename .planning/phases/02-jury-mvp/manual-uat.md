---
phase: 02-jury-mvp
plan: 08
status: pending-human-approval
created: 2026-05-10
updated: 2026-05-10
streamlit_url: http://localhost:8501
acceptance_reference: .planning/phases/02-jury-mvp/phase2-golden-results.json
---

# Phase 2 Manual UAT

This file records the required Streamlit manual UAT checkpoint for plan 02-08. The UI must run the real workflow service and expose response, sources, trace, artifacts, and feedback/fix actions.

## Checklist

### Pipeline traversal

- 2026-05-10 GC-001: Enter `Какой ВВП России в 2024 году?`; expect the workflow path to run from user query through final response and preserve trace events.
- 2026-05-10 GC-003: Enter `Сравни динамику ВВП стран БРИКС за 2015-2024 годы.`; expect selected World Bank/FedStat evidence, deterministic dataset, script, and visualization when available.
- 2026-05-10 GC-009: Enter `Дай данные по инфляции.`; expect `needs_clarification` with a concrete question.
- 2026-05-10 GC-009 follow-up: Answer the clarification with geography and period; expect `continue_user_query` path and a terminal `passed` or `not_found` outcome.
- 2026-05-10 GC-011: Enter `Найди официальную инфляцию в Северной Корее за 2024 год.`; expect honest `not_found` evidence.
- 2026-05-10 GC-013: Enter `Найди показатель ЕМИСС 57319 и покажи доступные ресурсы.`; expect CKAN/scout evidence and a terminal accepted outcome.

### Trace readability

- 2026-05-10: Confirm Streamlit displays trace events with state, agent, decision, artifact, warnings, and payload details.

### Source selection/rejection

- 2026-05-10: Confirm selected and rejected source cards are visible for cases with retrieval evidence, including rejection reasons.

### Deterministic provenance

- 2026-05-10: Confirm numeric answers are backed by `DatasetArtifact` records/provenance and no unsupported numeric text is presented as final evidence.

### Dataset/script downloads

- 2026-05-10: Confirm CSV/Parquet and script artifacts render with `st.download_button` when artifact paths exist.

### Frontend response format

- 2026-05-10: Confirm the UI renders `WorkflowResponse` sections: message, answer blocks, citations, coverage, extraction plan, visualization, limitations, clarification, not-found evidence, trace, and feedback actions.

### Clarification behavior and follow-up answer

- 2026-05-10: Confirm a `needs_clarification` response sets pending clarification state and the next chat input calls `continue_user_query` instead of starting a fresh run.

### Not-found honesty

- 2026-05-10: Confirm GC-011 returns `not_found` with checked/rejected sources or clear limitations and no invented numeric values.

### Feedback/fix-request flow

- 2026-05-10: Confirm rating/comment persists a feedback artifact linked to `run_id`, unsupported fix requests create a `fix_requested` artifact, and executable actions rerun through the service path.

## Observations

- 2026-05-10: Implementation checkpoint prepared. Human approval remains required after interacting with Streamlit at `http://localhost:8501`.
