# Technology Stack

**Analysis Date:** 2026-05-10

## Languages

**Primary:**
- Python 3.11.9 - application code, scripts, tests, and local data tooling in `app/`, `scripts/`, and `tests/`.

**Secondary:**
- Markdown - planning, evidence, and architecture artifacts in `.planning/`, `.planning/phases/01-data-architecture-research/`, `.planning/phases/02-jury-mvp/`, and `docs/`.
- YAML - golden-case input data in `.planning/phases/01-data-architecture-research/golden-cases.yaml`.
- JSON/JSONL - generated manifests and local prepared artifacts in `.planning/phases/01-data-architecture-research/*.json` and `.local/dataagent/phase1/*.jsonl`.
- SQL - deterministic extraction probe SQL files in `.planning/phases/01-data-architecture-research/extraction-probe-artifacts/*.sql`.

## Runtime

**Environment:**
- Python 3.11.9 from the local `python3` runtime.
- `pip` 24.0 is available for dependency installation.
- No `pyproject.toml`, `setup.cfg`, `setup.py`, `Pipfile`, `poetry.lock`, or container config detected. Treat the repo as a lightweight Python application launched with module/script commands from the repository root.

**Package Manager:**
- `pip` via `requirements.txt`.
- Lockfile: missing. Dependency versions in `requirements.txt` are lower bounds, so exact transitive versions are not pinned.

## Frameworks

**Core:**
- Pydantic v2 (`pydantic>=2.12.0`) - typed source-card, workflow, UI, and dataset artifacts in `app/artifacts/source_cards.py`, `app/artifacts/workflow_artifacts.py`, `app/workflow/graph_contract.py`, and `app/ui/trace_models.py`.
- Streamlit (`streamlit>=1.45.0`) - first demo UI target in `app/ui/streamlit_app.py`. The current UI is diagnostic Phase 1 infrastructure, not the Phase 2 jury workflow UI.
- Qdrant client (`qdrant-client>=1.16.0`) - vector-store abstraction in `app/retrieval/embedding_index.py`, `scripts/build_embedding_index.py`, and `scripts/build_partial_embedding_snapshot.py`.
- DuckDB (`duckdb>=1.4.0`) - deterministic SQL-first extraction utilities in `app/data/deterministic_tools.py` and probe scripts in `scripts/run_extraction_probes.py`.
- PyArrow (`pyarrow>=22.0.0`) - optional Parquet export path in `app/data/deterministic_tools.py`; FedStat/World Bank dumps are Parquet-backed.
- Requests (`requests>=2.32.0`) - HTTP client for Yandex AI Studio, Yandex embeddings, and CKAN calls in `app/llm/yandex_ai_studio.py`, `app/retrieval/embedding_index.py`, `app/data/deterministic_tools.py`, and `scripts/build_source_cards.py`.

**Testing:**
- Pytest is the active test runner by convention and evidence, with tests in `tests/`. No pytest config file is detected.
- Test command: `python3 -m pytest -q`.
- Phase 1 acceptance records 26 passed / 1 failed in `.planning/phases/01-data-architecture-research/phase1-test-acceptance.md`; Phase 2 must pass the full suite before MVP readiness is claimed.

**Build/Dev:**
- No separate build system detected.
- CLI scripts under `scripts/` build and validate local artifacts:
  - `scripts/build_source_cards.py`
  - `scripts/build_source_catalog.py`
  - `scripts/build_embedding_corpus.py`
  - `scripts/build_embedding_index.py`
  - `scripts/build_partial_embedding_snapshot.py`
  - `scripts/monitor_embedding_build.py`
  - `scripts/run_retrieval_spike.py`
  - `scripts/run_extraction_probes.py`
- Application entrypoints are module/script based:
  - `python3 -m app.workflow.run_graph`
  - `python3 -m app.demo.run_demo`
  - `streamlit run app/ui/streamlit_app.py`

## Key Dependencies

**Critical:**
- `pydantic>=2.12.0` - all source-bound contracts depend on `BaseModel` serialization/validation in `app/artifacts/source_cards.py`, `app/artifacts/workflow_artifacts.py`, and `app/workflow/graph_contract.py`.
- `qdrant-client>=1.16.0` - Phase 2 must keep Qdrant as the vector-store abstraction; do not replace it with an ad hoc local vector search. Current implementation supports local persistent mode via `.local/qdrant` and remote mode via `QDRANT_URL`.
- `duckdb>=1.4.0` - numeric extraction must route through deterministic SQL/tooling in `app/data/deterministic_tools.py`; LLM-generated numeric claims are not accepted.
- `requests>=2.32.0` - real HTTP integration layer for Yandex and CKAN.
- `streamlit>=1.45.0` - jury UI target, currently only diagnostic.

**Infrastructure:**
- `python-dotenv>=1.0.1` - local `.env` loading in `app/llm/yandex_ai_studio.py` and `app/retrieval/embedding_index.py`. `.env` exists and must remain local; do not read or commit secret values.
- `PyYAML>=6.0.2` - loads golden cases in `app/workflow/run_graph.py`, `app/evals/run_eval.py`, and `scripts/run_retrieval_spike.py`.
- `altair>=5.5.0` - preferred deterministic visualization metadata renderer in `app/data/deterministic_tools.py`.
- `polars>=1.36.0` - listed in `requirements.txt`, but current deterministic extraction code does not actively use it; code comments record DuckDB/PyArrow as sufficient for Phase 1 probes.
- `openai>=1.109.0` - listed for OpenAI-compatible API direction, but current Yandex chat client uses raw `requests` in `app/llm/yandex_ai_studio.py`; no source import of `openai` detected in `app/`, `scripts/`, or `tests/`.

## Configuration

**Environment:**
- Local secrets and runtime settings are expected in `.env`; `.env` and `.env.example` are present, but their contents must not be read into committed docs.
- Yandex chat env vars are read by `app/llm/yandex_ai_studio.py`:
  - `YANDEX_AI_STUDIO_QWEN_API_KEY` or fallback `YANDEX_AI_STUDIO_API_KEY` / `YANDEX_API_KEY`
  - `YANDEX_AI_STUDIO_QWEN_MODEL` or fallback `YANDEX_AI_STUDIO_MODEL` / `YANDEX_QWEN_MODEL`
  - `YANDEX_AI_STUDIO_BASE_URL`, defaulting to `https://llm.api.cloud.yandex.net/v1`
- Yandex embedding and Qdrant env vars are read by `app/retrieval/embedding_index.py`:
  - `YANDEX_EMBEDDING_API_KEY` or fallback `YANDEX_AI_STUDIO_API_KEY` / `YANDEX_API_KEY`
  - `YANDEX_FOLDER_ID`
  - `YANDEX_EMBEDDING_DOC_MODEL`
  - `YANDEX_EMBEDDING_QUERY_MODEL`
  - `YANDEX_EMBEDDING_DIMENSIONS`, defaulting to `256`
  - `YANDEX_EMBEDDING_BASE_URL`, defaulting to Yandex Foundation Models text embedding endpoint
  - `YANDEX_EMBEDDING_TIMEOUT`
  - `YANDEX_EMBEDDING_RETRIES`
  - `QDRANT_MODE`
  - `QDRANT_PATH`
  - `QDRANT_URL`
  - `QDRANT_API_KEY`
  - `QDRANT_COLLECTION`
  - `BGE_RERANKER_URL` for the reranker seam in `app/retrieval/hybrid_retrieval.py`

**Build:**
- No compiled build config detected.
- Runtime dependency config is only `requirements.txt`.
- Generated evidence and manifests live under `.planning/phases/01-data-architecture-research/`.
- Local generated data and vector storage live under `.local/` and are ignored by `.gitignore`.

## Local Data and Runtime Assumptions

**Local dumps:**
- FedStat dump default: `/Users/a/Downloads/dumps/fedstatru/fedstatru.zip`, used by `scripts/build_source_cards.py`.
- World Bank dump default: `/Users/a/Downloads/dumps/wb/data.zip`, used by `scripts/build_source_cards.py`.
- Broader local dump reference: `/Users/a/Downloads/dumps.zip`, recorded in `.planning/STATE.md`.
- Dump files are not committed; `.gitignore` excludes `dumps/`, `*.zip`, `*.parquet`, `*.jsonl`, `*.pdf`, and `.local/`.

**Prepared artifacts:**
- Source cards: `.local/dataagent/phase1/source-cards.json`, manifest `.planning/phases/01-data-architecture-research/source-cards-manifest.json`.
- SQLite catalog: `.local/dataagent/phase1/source-catalog.sqlite`, manifest `.planning/phases/01-data-architecture-research/source-catalog-manifest.json`.
- Embedding corpus: `.local/dataagent/phase1/embedding-corpus.jsonl`, manifest `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json`.
- Embedding cache/build state: `.local/dataagent/phase1/embedding-cache.jsonl`, `.local/dataagent/phase1/embedding-build.pid`, `.local/dataagent/phase1/embedding-build.stdout.log`, and `.local/dataagent/phase1/embedding-monitor.log`.
- Local Qdrant storage: `.local/qdrant`, `.local/qdrant-partial-dev`, and `.local/qdrant-method-check`.

**Current readiness state:**
- Source-card/catalog/corpus manifests record 36,321 source cards/chunks in `.planning/phases/01-data-architecture-research/source-cards-manifest.json`, `.planning/phases/01-data-architecture-research/source-catalog-manifest.json`, and `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json`.
- The current embedding index manifest `.planning/phases/01-data-architecture-research/embedding-index-manifest.json` is not aligned with the full corpus: it records `status=gated_skip`, `dense_status=gated_skip`, `chunk_count=11`, `vector_count=0`, and missing embedding credentials.
- The current demo readiness artifact `.planning/phases/01-data-architecture-research/demo-readiness.current.json` records `overall_status=blocked`, `qdrant_status=stale`, `dense_retrieval_ready=false`, and a corpus hash mismatch between the embedding corpus and index manifest.
- Phase 2 must treat these as infrastructure artifacts, not MVP-ready runtime state.

## Platform Requirements

**Development:**
- Run from repository root `/Users/a/MAI/matmod` so relative paths in `app/ui/streamlit_app.py`, `app/demo/run_demo.py`, and scripts resolve correctly.
- Install dependencies with `python3 -m pip install -r requirements.txt`.
- Keep `.env` local for Yandex/Qdrant credentials.
- Keep `.local/` available for generated artifacts and local Qdrant storage.

**Production:**
- Deployment target not detected.
- Phase 2 jury MVP should continue as a local Streamlit application unless the roadmap changes.
- Remote Qdrant is supported by env vars in `app/retrieval/embedding_index.py`, but current committed readiness evidence is local/gated/stale.

## Phase 2 Stack Guidance

- Use `app/llm/yandex_ai_studio.py` for Qwen/Yandex structured-output calls; preserve verified base URL and `Api-Key` auth.
- Use `app/retrieval/embedding_index.py` and `app/retrieval/hybrid_retrieval.py` for retrieval; keep Qdrant and the prepared corpus contract.
- Use `app/data/deterministic_tools.py` for numeric extraction/export/visualization artifacts; do not let LLM code invent or read numeric values directly.
- Use `app/workflow/run_graph.py` and `app/workflow/graph_contract.py` as current workflow seeds, but note they are a narrow Phase 1 graph and not a full LangGraph runtime.
- LangGraph is a target architecture in `.planning/ARCHITECTURE_STACK.md` and `.planning/phases/02-jury-mvp/02-SEED-CONTEXT.md`, but no `langgraph` dependency is present in `requirements.txt` and no `langgraph` import exists in current application code.

---

*Stack analysis: 2026-05-10*
