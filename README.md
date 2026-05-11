# DataAgent

Source-bound economic data assistant for the jury MVP. The system routes a user query through live Qwen intent analysis, source scouting, coverage checks, deterministic extraction, methodology critique, visualization, and narration.

## Setup

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest -q
```

Keep local credentials in `.env`. Do not commit API keys.

## Run Qdrant Server

```bash
docker compose -f docker-compose.qdrant.yml up -d qdrant
python3 scripts/promote_qdrant_server.py --start-server --manifest-output .planning/phases/02-jury-mvp/qdrant-server-manifest.json
```

Phase 2 jury readiness expects server Qdrant through `QDRANT_URL`, not embedded local mode, so evals and workflow runs can share the same collection.

## Run One Workflow Query Without UI

```bash
PYTHONPATH=. python3 scripts/run_workflow_query.py "Какой ВВП России в 2024 году?"
```

The command calls `app.workflow.service.run_user_query` and writes the full `WorkflowResponse` JSON under `.planning/phases/02-jury-mvp/manual-runs/<run_id>/response.json`. Live Yandex AI Studio / Qwen credentials are required.

For clarification flows:

```bash
PYTHONPATH=. python3 scripts/run_workflow_query.py "Дай данные по инфляции." --follow-up "Россия, 2024 год"
```

## Run All-20 Golden Acceptance

```bash
python3 scripts/run_phase2_acceptance.py --goldens .planning/phases/01-data-architecture-research/golden-cases.yaml --coverage-matrix .planning/phases/02-jury-mvp/golden-coverage-matrix.json --json-output .planning/phases/02-jury-mvp/phase2-golden-results.json --markdown-output .planning/phases/02-jury-mvp/phase2-golden-results.md --artifact-dir .planning/phases/02-jury-mvp/workflow-runs
```

Acceptance is all 20 golden cases with terminal outcomes limited to `passed`, `needs_clarification`, or `not_found`.

## Source-Bound Architecture

The workflow is:

`User query -> Supervisor -> Intent Analyst -> Research Designer / Direct path -> FedStat/WB/CKAN Scouts -> Coverage & Schema -> Extraction Planner -> Deterministic Tools -> Methodology Critic -> Visualization -> Narrator -> answer + dataset + script + sources + trace`.

Numbers must come from deterministic adapters or trusted source artifacts, never from LLM memory. CKAN is used as a bounded NSED catalog API, not general web search.

## Secrets

Use `.env` for local secrets such as `YANDEX_API_KEY`, Qwen model settings, embedding credentials, and `QDRANT_URL`. `.env.example` documents expected variable names.
