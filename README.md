# DataAgent

Source-bound economic data assistant. Accepts a natural-language query, routes it through a deterministic LangGraph pipeline, and returns a structured response where every number is traced to an extraction artifact — never to LLM memory.

Built for the НЦСЭД / Yandex Cloud jury MVP (Spring 2026).

---

## Architecture

```
User query
  │
  ▼
Supervisor ──────────────────────────────────────────────────────┐
  │  triage: direct | research | no_data                         │
  ▼                                                              │
Intent Analyst (Qwen structured output)                          │
  │  → IntentFrame: category, known_fields, missing_fields       │
  │                                                              │
  ├─ needs_clarification ──────────────────────────────────────► Narrator
  ├─ direct ──────────────────────────────────┐                  │
  └─ research ──► Research Designer           │                  │
                   → ResearchDesignArtifact   │                  │
                                              ▼                  │
                                       Source Scouts             │
                                  (FedStat · World Bank · CKAN)  │
                                       → EvidenceBundleArtifact  │
                                              │                  │
                                              ▼                  │
                                       Coverage & Schema         │
                                       → CoverageReport[]        │
                                              │                  │
                                              ▼                  │
                                       Extraction Planner        │
                                       → ExtractionPlan          │
                                              │                  │
                                              ▼                  │
                                       Deterministic Tools       │
                                       → DatasetArtifact[]       │
                                         ScriptArtifact[]        │
                                              │                  │
                              ┌───────────────┘                  │
                              ▼                                  │
                       Methodology Critic                        │
                       → CritiqueReport                          │
                              │                                  │
                              ▼                                  │
                       Visualization (optional)                  │
                       → VisualizationSpec                       │
                              │                                  │
                              └──────────────────────────────────┘
                                             │
                                             ▼
                                    WorkflowResponse
                           outcome: passed | needs_clarification | not_found
```

**Invariants:**
- All numeric values come from `DatasetArtifact` records, never from LLM text generation.
- Extraction is restricted to an explicit allowlist of operations (no free-form LLM SQL).
- Every response block carries a `source_id` provenance reference.
- CKAN is used as a bounded НЦСЭД catalog API, not general web search.

---

## Data Sources

| Source | Coverage | Access |
|--------|----------|--------|
| **FedStat (ЕМИСС)** | Russian federal statistics, 600 k+ indicators | Local parquet via `FEDSTAT_ROOT` |
| **World Bank** | 29 k+ indicators, 296 countries | Local parquet + metadata via `WORLD_BANK_ROOT` |
| **CKAN (НЦСЭД)** | Promoted datasets from repository.nsedc.ru | Network API, opt-in via `--ckan` |

---

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in credentials
```

Minimum viable `.env` for offline tests (no Yandex or Qdrant required):

```env
FEDSTAT_ROOT=/path/to/fedstat
WORLD_BANK_ROOT=/path/to/world_bank
```

Full Phase 2 pipeline requires Yandex AI Studio (Qwen) and a shared Qdrant server.

---

## Tutorial: From Zero to First Query

### Step 1 — Install dependencies

```bash
python -m pip install -r requirements.txt
```

Requires Python 3.11+. No virtual environment is enforced but recommended:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2 — Configure credentials

```bash
cp .env.example .env
```

Edit `.env` and fill in your values. The minimum for a working offline run (no LLM, no Qdrant):

```env
FEDSTAT_ROOT=/absolute/path/to/fedstat-data
WORLD_BANK_ROOT=/absolute/path/to/world-bank-data
```

For the full Phase 2 pipeline add:

```env
YANDEX_API_KEY=your_service_account_key
YANDEX_FOLDER_ID=your_folder_id
YANDEX_QWEN_MODEL=gpt://your_folder_id/qwen3.6-35b-a3b/latest
YANDEX_EMBEDDING_BASE_URL=https://llm.api.cloud.yandex.net:443/foundationModels/v1/textEmbedding
YANDEX_EMBEDDING_DOC_MODEL=emb://your_folder_id/text-search-doc/latest
YANDEX_EMBEDDING_QUERY_MODEL=emb://your_folder_id/text-search-query/latest
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=phase1_source_cards
```

### Step 3 — Verify the setup (no LLM required)

```bash
PYTHONPATH=. python -m pytest tests/test_source_bound_skeleton.py -v
```

Expected output:

```
PASSED tests/test_source_bound_skeleton.py::test_empty_query_needs_clarification
PASSED tests/test_source_bound_skeleton.py::test_no_configured_sources_returns_not_found
PASSED tests/test_source_bound_skeleton.py::test_world_bank_adapter_uses_metadata_fixture
PASSED tests/test_source_bound_skeleton.py::test_app_contains_no_mock_or_old_demo_markers
```

### Step 4 — Run a lightweight query (no LLM, local sources only)

```bash
PYTHONPATH=. python scripts/run_query.py "ВВП России 2024"
```

This runs intent detection and lexical source search against your local data, then writes
a `WorkflowResponse` JSON to stdout. If no local data roots are configured, the response
will be `not_found` — that is correct behaviour.

To also search the CKAN network catalog:

```bash
PYTHONPATH=. python scripts/run_query.py "ВВП России 2024" --ckan
```

### Step 5 — Start Qdrant (required for Phase 2 embedding retrieval)

```bash
docker compose -f docker-compose.qdrant.yml up -d qdrant
```

Verify it is up:

```bash
curl http://localhost:6333/healthz
# {"title":"qdrant - vector search engine","version":"..."}
```

Then register the server and populate the collection manifest:

```bash
PYTHONPATH=. python scripts/promote_qdrant_server.py \
    --start-server \
    --manifest-output .planning/phases/02-jury-mvp/qdrant-server-manifest.json
```

### Step 6 — Build the embedding index (first time only)

If you have local FedStat/World Bank data, build the BM25 corpus and embed it into Qdrant:

```bash
PYTHONPATH=. python scripts/build_embedding_corpus.py
PYTHONPATH=. python scripts/build_embedding_index.py
```

This is a one-time operation. The index is stored in Qdrant and reused across runs.

### Step 7 — Run the full Phase 2 pipeline

```bash
PYTHONPATH=. python scripts/run_workflow_query.py "Какой ВВП России в 2024 году?"
```

The response JSON is written to:

```
.planning/phases/02-jury-mvp/workflow-runs/<run_id>/
  phase2-state.json          # internal graph state
  pending-clarification.json # clarification context for follow-up
```

To send a follow-up clarification:

```bash
PYTHONPATH=. python scripts/run_workflow_query.py "Дай данные по инфляции." \
    --follow-up "Россия, 2020–2024 годы"
```

### Step 8 — Launch the web UI

```bash
PYTHONPATH=. python app/web/server.py
```

Opens at `http://127.0.0.1:8787`. The UI streams agent steps live via SSE, shows the
full response with dataset preview, source cards, methodology critique, and optional chart.
Use `--host 0.0.0.0 --port 8080` to expose on a different address.

---

## Running

### Full Phase 2 pipeline (Qwen + Qdrant required)

```bash
PYTHONPATH=. python scripts/run_workflow_query.py "Какой ВВП России в 2024 году?"
```

Writes `WorkflowResponse` JSON to `.planning/phases/02-jury-mvp/workflow-runs/<run_id>/`.

With a clarification follow-up:

```bash
PYTHONPATH=. python scripts/run_workflow_query.py "Дай данные по инфляции." \
    --follow-up "Россия, 2024 год"
```

### Lightweight skeleton (local sources only, no LLM)

```bash
PYTHONPATH=. python scripts/run_query.py "GDP Russia 2024"
PYTHONPATH=. python scripts/run_query.py "ВВП России 2024" --ckan
```

Returns `WorkflowResponse` JSON to stdout. Runs intent detection and source search
without LLM calls. Useful for testing adapter configuration and local data availability.

### Qdrant server (required for Phase 2 embedding retrieval)

```bash
docker compose -f docker-compose.qdrant.yml up -d qdrant
python scripts/promote_qdrant_server.py \
    --start-server \
    --manifest-output .planning/phases/02-jury-mvp/qdrant-server-manifest.json
```

### Web UI

```bash
PYTHONPATH=. python app/web/server.py
# → http://127.0.0.1:8787
```

### Golden acceptance suite (20 cases)

```bash
python scripts/run_phase2_acceptance.py \
    --goldens .planning/phases/01-data-architecture-research/golden-cases.yaml \
    --coverage-matrix .planning/phases/02-jury-mvp/golden-coverage-matrix.json \
    --json-output .planning/phases/02-jury-mvp/phase2-golden-results.json \
    --markdown-output .planning/phases/02-jury-mvp/phase2-golden-results.md \
    --artifact-dir .planning/phases/02-jury-mvp/workflow-runs
```

All 20 cases must resolve to `passed`, `needs_clarification`, or `not_found`.

---

## Tests

```bash
python -m pytest -q
```

Key test files:

| File | What it covers |
|------|---------------|
| `tests/test_source_bound_skeleton.py` | Config, adapters, no-mock guard |
| `tests/test_phase2_acceptance.py` | Golden case runner |
| `tests/test_workflow_graph.py` | Graph node routing |
| `tests/test_phase2_workflow_nodes.py` | Individual node behavior |
| `tests/test_deterministic_tools_and_trace.py` | Extraction execution and trace |
| `tests/test_phase2_contracts.py` | Artifact schema contracts |
| `tests/test_hybrid_retrieval.py` | Lexical + dense retrieval |

---

## Project Layout

```
app/
├── config.py                  # Settings loaded from environment
├── contracts.py               # Shared Pydantic models (IntentFrame, WorkflowResponse, …)
├── artifacts/
│   ├── store.py               # JSON artifact persistence (ArtifactStore)
│   ├── workflow_artifacts.py  # Phase 2 artifact schemas
│   └── source_cards.py        # SourceCandidateCard model
├── catalog/
│   └── source_catalog.py      # SQLite build-time catalog (used by build scripts)
├── data/                      # Deterministic extraction adapters
│   ├── world_bank_adapter.py
│   ├── fedstat_adapter.py
│   ├── ckan_adapter.py
│   └── deterministic_tools.py
├── llm/
│   └── yandex_ai_studio.py    # Yandex AI Studio / Qwen client
├── observability/
│   └── workflow_audit.py      # Runtime JSONL audit trail
├── retrieval/
│   ├── catalog.py             # Runtime SourceCatalog (aggregates adapters)
│   ├── embedding_index.py     # Yandex embeddings + Qdrant
│   ├── hybrid_retrieval.py    # Lexical (BM25) + dense + graph retrieval
│   └── graph_store.py         # SQLite entity-link graph
├── sources/                   # Lightweight source adapters (lexical search on metadata)
│   ├── registry.py            # build_source_adapters() factory
│   ├── base.py                # tokenize(), lexical_score(), read_jsonl()
│   ├── fedstat.py             # FedStatAdapter
│   ├── world_bank.py          # WorldBankAdapter
│   └── ckan.py                # CkanAdapter (network, opt-in)
├── ui/
│   ├── trace_models.py        # Trace view, feedback, and fix-request models
│   └── streamlit_app.py       # Legacy Streamlit shell (not used in production)
├── web/
│   ├── server.py              # HTTP server with SSE streaming (port 8787)
│   └── static/                # HTML/CSS/JS frontend
└── workflow/
    ├── orchestrator.py        # Lightweight run_query() — intent + source search only
    ├── service.py             # Full pipeline: run_user_query(), continue_user_query(), apply_feedback()
    ├── graph.py               # LangGraph Phase 2 graph (8 nodes)
    ├── state.py               # Phase2State TypedDict + LLM intent/design functions
    ├── intent.py              # Rule-based intent fallback (no LLM)
    └── nodes/
        ├── scouts.py          # Source scouts
        ├── coverage.py        # Coverage assessment
        ├── extraction_planner.py
        ├── deterministic_tools.py
        ├── critic.py          # Methodology critique
        ├── visualization.py   # Chart spec generation
        └── narrator.py        # Response assembly + number validation

scripts/                       # CLI utilities and build scripts
tests/                         # 18+ test files
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FEDSTAT_ROOT` | For FedStat | — | Path to local FedStat parquet directory |
| `WORLD_BANK_ROOT` | For World Bank | — | Path to local World Bank parquet + indicators.json |
| `CKAN_BASE_URL` | No | `https://repository.nsedc.ru/api/3/action` | CKAN API base URL |
| `YANDEX_API_KEY` | Phase 2 LLM | — | Yandex Cloud service account API key |
| `YANDEX_FOLDER_ID` | Phase 2 LLM | — | Yandex Cloud folder ID |
| `YANDEX_QWEN_MODEL` | Phase 2 LLM | — | Qwen model URI (e.g. `gpt://<folder>/qwen3.6-35b-a3b/latest`) |
| `YANDEX_EMBEDDING_BASE_URL` | Phase 2 embeddings | — | Yandex embeddings endpoint |
| `QDRANT_URL` | Phase 2 embeddings | `http://localhost:6333` | Shared Qdrant server URL |
| `QDRANT_COLLECTION` | Phase 2 embeddings | `phase1_source_cards` | Qdrant collection name |
| `ARTIFACT_ROOT` | No | `.local/artifacts` | Directory for workflow artifact JSON files |
| `MAX_CANDIDATES_PER_SOURCE` | No | `5` | Max source candidates per adapter (1–50) |
| `REQUEST_TIMEOUT_SECONDS` | No | `20` | HTTP timeout for CKAN and external calls (1–120) |

See `.env.example` for a complete template.

---

## Secrets

Keep all credentials in `.env`. The file is gitignored. Do not commit API keys.
