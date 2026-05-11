# Phase 1 Actual State Verification

Observed at: 2026-05-10T09:08:39Z

## Purpose

Answer the resume question directly: what was actually built in Phase 1, what starts today, which interface is usable, and which parts are still gated, stale, simplified, or stubbed.

Primary reference: `.planning/ARCHITECTURE_STACK.md`.

## Current Verdict

Phase 1 produced a real prepared-data and diagnostic execution foundation, but not a complete end-user DataAgent yet.

Working today:

- Full local source-card corpus is built for FedStat and World Bank: 36,321 source cards / embedding chunks.
- SQLite source catalog exists and passes its manifest queryability check.
- Hybrid retrieval interface runs over the prepared corpus.
- A partial Qdrant snapshot exists for development/smoke testing.
- The narrow workflow graph starts from a golden case, emits structured state and trace artifacts, selects source candidates, and withholds numeric narration when deterministic extraction is not complete.
- Streamlit diagnostic UI starts and exposes readiness, trace, artifacts, rejected sources, selected sources, and feedback/fix-request payloads.
- Deterministic extraction probe scripts and artifacts exist for source-family probes.

Not complete today:

- The full Qdrant dense index is still being populated in the background.
- `embedding-index-manifest.json` is stale relative to the rebuilt 36,321-chunk corpus.
- Demo readiness is therefore `blocked` for the main full index, not `ready`.
- Numeric answer generation is intentionally withheld in the graph; deterministic extraction is represented as gated planning/probe evidence, not a completed answer pipeline.
- The hierarchical multi-agent system from the architecture reference is implemented as typed contracts and a narrow runnable slice, not as a full LangGraph supervisor with live LLM-powered subagents.
- CKAN/NSED is treated as a trusted source path but is not included in the current full local corpus.

## Background Embedding Build

Current handoff stated that the full embedding build was running. This was confirmed.

Observed command state:

- PID file: `.local/dataagent/phase1/embedding-build.pid`
- PID: `77528`
- Process command: `scripts/build_embedding_index.py --corpus-manifest .planning/phases/01-data-architecture-research/embedding-corpus-manifest.json --manifest .planning/phases/01-data-architecture-research/embedding-index-manifest.json --build-log .planning/phases/01-data-architecture-research/embedding-index-build.md --cache .local/dataagent/phase1/embedding-cache.jsonl --batch-size 64 --workers 3`
- Cache progress at observation time: 17,595 / 36,321 lines
- Heartbeat automation: `/Users/a/.codex/automations/monitor-full-embedding-build/automation.toml`
- Heartbeat status: `ACTIVE`
- Heartbeat schedule: `FREQ=MINUTELY;INTERVAL=5`

Important: do not treat full dense retrieval as complete until the cache reaches 36,321 chunks and `embedding-index-manifest.json` is refreshed with the current corpus hash, vector count, and ready status.

## Artifact Status

Current prepared-data manifests:

- `source-cards-manifest.json`
  - `card_count`: 36,321
  - `embedding_chunk_count`: 36,321
  - `artifact_path`: `.local/dataagent/phase1/source-cards.json`
- `source-catalog-manifest.json`
  - `source_cards_count`: 36,321
  - `catalog_path`: `.local/dataagent/phase1/source-catalog.sqlite`
- `embedding-corpus-manifest.json`
  - `chunk_count`: 36,321
  - `artifact_path`: `.local/dataagent/phase1/embedding-corpus.jsonl`
- `embedding-index-manifest.json`
  - `status`: `gated_skip`
  - `chunk_count`: 11
  - `vector_count`: 0
  - `corpus_hash`: old 11-card demo corpus hash
  - Current problem: stale relative to the rebuilt 36,321-chunk corpus.
- `partial-embedding-index-manifest.json`
  - `status`: `partial_ready`
  - `collection_name`: `phase1_source_cards_partial`
  - `vector_count`: 5,748
  - Use this for smoke/development only.

## Verification Commands Run

### Test Suite

Command:

```bash
python3 -m pytest -q
```

Result:

- 26 passed
- 1 failed

Failure:

- `tests/test_demo_readiness.py::test_demo_readiness_reports_gates_without_dense_success`
- The test expects `qdrant_status` in `{ready, gated_skip}`.
- Actual status is `stale`, because the full source-card corpus was rebuilt to 36,321 chunks while the main `embedding-index-manifest.json` still points at the old 11-card corpus hash.

Interpretation: this is useful evidence, not a random breakage. It proves readiness artifacts must be refreshed after the background embedding build finishes.

### Demo Readiness Runner

Direct script path fails:

```bash
python3 app/demo/run_demo.py ...
```

Failure:

```text
ModuleNotFoundError: No module named 'app'
```

Working invocation:

```bash
python3 -m app.demo.run_demo \
  --source-cards-manifest .planning/phases/01-data-architecture-research/source-cards-manifest.json \
  --source-catalog-manifest .planning/phases/01-data-architecture-research/source-catalog-manifest.json \
  --embedding-corpus-manifest .planning/phases/01-data-architecture-research/embedding-corpus-manifest.json \
  --index-manifest .planning/phases/01-data-architecture-research/embedding-index-manifest.json \
  --retrieval-eval .planning/phases/01-data-architecture-research/retrieval-eval.csv \
  --extraction-probes .planning/phases/01-data-architecture-research/extraction-probes.json \
  --data-relevance-eval .planning/phases/01-data-architecture-research/data-relevance-eval.json \
  --json-output .planning/phases/01-data-architecture-research/demo-readiness.current.json
```

Result:

```json
{
  "overall_status": "blocked",
  "qdrant_status": "stale",
  "dense_retrieval_ready": false
}
```

### Workflow Graph Smoke

Direct script path fails:

```bash
python3 app/workflow/run_graph.py ...
```

Failure:

```text
ModuleNotFoundError: No module named 'app'
```

Working invocation:

```bash
python3 -m app.workflow.run_graph \
  --goldens .planning/phases/01-data-architecture-research/golden-cases.yaml \
  --case-index 0 \
  --index-manifest .planning/phases/01-data-architecture-research/partial-embedding-index-manifest.json \
  --json-output .planning/phases/01-data-architecture-research/run-graph-smoke.current.json
```

Result:

- `status`: `ok`
- `route`: `Ambiguous lookup`
- `qdrant_status`: `partial_ready`
- selected sources: 5
- `coverage_status`: `gated`
- `extraction_status`: `gated`
- trace states: `received`, `triage`, `parallel_scouts`, `coverage_and_extraction`, `critic_and_narrator`, `checkpoint`

Important behavior: the graph chooses candidates and emits trace/evidence, but the final answer explicitly says numeric narration is withheld until deterministic extraction returns data.

Observed candidate quality issue in GC-001:

- Top candidate for "Какой ВВП России в 2024 году?" was `fedstat:62470`, "Удельный вес бюджетных расходов на фундаментальные исследования в валовом внутреннем продукте".
- More directly relevant GDP candidates were present below it, for example `fedstat:40578`, `fedstat:40579`, `fedstat:57395`.

Interpretation: retrieval works, but ranking is not good enough to trust as a final source selector yet.

### Hybrid Retrieval Smoke

Using `partial-embedding-index-manifest.json`, retrieval returned meaningful candidates:

- Query: `ВВП России`
  - FedStat GDP PPP and GDP per capita candidates surfaced.
- Query: `инвестиции в основной капитал`
  - FedStat investment candidates surfaced.
- Query: `population Russia`
  - World Bank population candidates surfaced, but a FedStat "российских ученых" candidate ranked above them.

Status:

- `dense_status`: `partial_ready`
- retrieval mode shown on candidates: `hybrid_lexical_dense_gated`

Interpretation: partial retrieval is usable for smoke and debugging, but ranking and dense/full-index state remain incomplete.

### Streamlit Interface

Working invocation:

```bash
PYTHONPATH=. python3 -m streamlit run app/ui/streamlit_app.py \
  --server.headless true \
  --server.port 8501 \
  --browser.gatherUsageStats false
```

HTTP check:

```bash
curl -I --max-time 5 http://localhost:8501
```

Result:

```text
HTTP/1.1 200 OK
```

Current interface:

- URL: `http://localhost:8501`
- Type: Streamlit diagnostic shell, not a polished product UI.
- It exposes:
  - example prompts and chat input;
  - state machine metrics;
  - index readiness;
  - prepared artifact counts;
  - trace events;
  - selected/rejected sources;
  - feedback and fix-request payloads.

Important limitation: the chat input does not currently execute the full workflow for arbitrary user input. It selects or displays the active query while the readiness view is built from existing Phase 1 artifacts.

## Implemented vs Simplified

Implemented as real code:

- Pydantic artifacts for intent, research design, source evidence, coverage, extraction plan, dataset artifact, final answer, feedback, and trace events.
- Source-card builders and manifests for FedStat and World Bank.
- SQLite catalog materialization.
- Embedding corpus generation.
- Qdrant embedding-index builder with Yandex embedding provider and resumable cache.
- Hybrid retrieval interface with lexical BM25, optional dense Qdrant retrieval, and deterministic rerank fallback.
- Demo readiness runner.
- Narrow workflow graph smoke runner.
- Streamlit diagnostic UI.
- Pytest coverage for contracts, catalog/corpus, retrieval, graph, eval runner, demo readiness, deterministic tools, and Yandex AI Studio gates.

Simplified or stub-like:

- `Phase1Graph.invoke()` only appends a checkpoint trace. It is not a full LangGraph multi-node orchestration.
- The "agents" in graph smoke are represented by trace labels and typed contracts, not live LLM subagents.
- Intent for `run_graph` comes from golden-case metadata, not from live LLM classification.
- Research design is a minimal canned artifact for complex routes.
- Coverage/extraction in graph smoke is gated and does not produce numeric datasets.
- Narrator withholds numeric answers instead of generating final economic conclusions.
- Reranker is a deterministic fallback unless `BGE_RERANKER_URL` is configured; even then the endpoint is recorded as configured-not-called in Phase 1.
- Main full-index readiness is stale until the background embedding build completes and manifests are refreshed.
- CKAN/NSED source preparation is not part of the current full local corpus.

## How To Run Today

Run tests:

```bash
python3 -m pytest -q
```

Expected current result before embedding/readiness refresh:

```text
26 passed, 1 failed
```

Run demo readiness:

```bash
python3 -m app.demo.run_demo \
  --source-cards-manifest .planning/phases/01-data-architecture-research/source-cards-manifest.json \
  --source-catalog-manifest .planning/phases/01-data-architecture-research/source-catalog-manifest.json \
  --embedding-corpus-manifest .planning/phases/01-data-architecture-research/embedding-corpus-manifest.json \
  --index-manifest .planning/phases/01-data-architecture-research/embedding-index-manifest.json \
  --retrieval-eval .planning/phases/01-data-architecture-research/retrieval-eval.csv \
  --extraction-probes .planning/phases/01-data-architecture-research/extraction-probes.json \
  --data-relevance-eval .planning/phases/01-data-architecture-research/data-relevance-eval.json \
  --json-output .planning/phases/01-data-architecture-research/demo-readiness.current.json
```

Run workflow smoke on the partial index:

```bash
python3 -m app.workflow.run_graph \
  --goldens .planning/phases/01-data-architecture-research/golden-cases.yaml \
  --case-index 0 \
  --index-manifest .planning/phases/01-data-architecture-research/partial-embedding-index-manifest.json \
  --json-output .planning/phases/01-data-architecture-research/run-graph-smoke.current.json
```

Run current UI:

```bash
PYTHONPATH=. python3 -m streamlit run app/ui/streamlit_app.py \
  --server.headless true \
  --server.port 8501 \
  --browser.gatherUsageStats false
```

Open:

```text
http://localhost:8501
```

Check embedding progress:

```bash
wc -l .local/dataagent/phase1/embedding-cache.jsonl .local/dataagent/phase1/embedding-corpus.jsonl
ps -p "$(cat .local/dataagent/phase1/embedding-build.pid)" -o pid,ppid,stat,etime,command
```

## Recommended Next Step

Wait for or supervise the full embedding build to completion. Then refresh:

- `embedding-index-manifest.json`
- `embedding-index-build.md`
- `demo-readiness.json`
- `prepared-data-readiness.md`
- retrieval smoke/eval artifacts

After that, rerun the full test suite and promote 2-3 golden cases into deterministic extraction smoke tests with real numeric outputs and source provenance.
