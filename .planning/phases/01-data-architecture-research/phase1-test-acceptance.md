# Phase 1 Test Acceptance

Observed at: 2026-05-10, after stopping MVP implementation work.

## Scope

This report freezes the exact Phase 1 result before starting any new MVP phase.

It covers:

- all pytest tests in `tests/`;
- current demo readiness;
- current retrieval evaluation over all 20 golden cases;
- current extraction probes;
- current data relevance evaluation;
- current workflow smoke output;
- embedding/index state.

No new MVP workflow code was added during this acceptance pass.

## Pytest Result

Command:

```bash
python3 -m pytest -vv
```

Result:

- Collected: 27 tests
- Passed: 26
- Failed: 1

### Full Test List

| Test | Result | What It Proves |
|---|---:|---|
| `tests/test_demo_readiness.py::test_demo_readiness_reports_gates_without_dense_success` | FAILED | Demo readiness no longer matches the old accepted gate expectation because the main Qdrant manifest is stale after full-corpus rebuild. |
| `tests/test_demo_readiness.py::test_streamlit_app_imports_without_streamlit_runtime` | PASSED | Streamlit module can be imported without starting Streamlit runtime. |
| `tests/test_deterministic_tools_and_trace.py::test_deterministic_tool_contracts_export_dataset_and_visualization` | PASSED | Deterministic DuckDB query, dataset artifact export, and table visualization contract work on a toy query. |
| `tests/test_deterministic_tools_and_trace.py::test_trace_models_reuse_canonical_trace_event` | PASSED | UI trace model reuses canonical workflow trace event. |
| `tests/test_deterministic_tools_and_trace.py::test_extraction_probe_runner_writes_machine_readable_evidence` | PASSED | Extraction probe runner writes machine-readable evidence for FedStat, World Bank, and CKAN probe paths. |
| `tests/test_embedding_index.py::test_yandex_embedding_config_uses_split_models` | PASSED | Embedding config separates document/query embedding models. |
| `tests/test_embedding_index.py::test_build_embedding_index_writes_gated_manifest_with_qdrant_config` | PASSED | Embedding index builder can write a credential-gated Qdrant manifest. |
| `tests/test_eval_runner.py::test_eval_runner_records_gated_components_without_silent_success` | PASSED | Eval runner records gated components explicitly. |
| `tests/test_hybrid_retrieval.py::test_lexical_bm25_returns_metadata_rich_source_cards` | PASSED | Lexical retrieval returns metadata-rich source candidates. |
| `tests/test_hybrid_retrieval.py::test_retrieval_spike_writes_eval_csv_with_dense_and_rerank_status` | PASSED | Retrieval spike writes CSV with dense/rerank status fields. |
| `tests/test_source_card_builders.py::SourceCardBuildersTest::test_ckan_builder_records_bounded_resource_inspection` | PASSED | CKAN builder records bounded resource inspection metadata. |
| `tests/test_source_card_builders.py::SourceCardBuildersTest::test_fedstat_builder_flags_wide_parquet_normalization` | PASSED | FedStat builder flags wide parquet normalization risk. |
| `tests/test_source_card_builders.py::SourceCardBuildersTest::test_world_bank_builder_uses_indicator_and_country_metadata` | PASSED | World Bank builder uses indicator and country metadata. |
| `tests/test_source_cards_contract.py::SourceCardsContractTest::test_embedding_corpus_manifest_records_durable_index_contract` | PASSED | Embedding corpus manifest records durable index contract. |
| `tests/test_source_cards_contract.py::SourceCardsContractTest::test_evidence_bundle_separates_candidates_rejections_and_intent` | PASSED | Evidence bundle separates selected candidates, rejected candidates, and intent. |
| `tests/test_source_cards_contract.py::SourceCardsContractTest::test_required_match_modes_are_available` | PASSED | Required match modes exist. |
| `tests/test_source_cards_contract.py::SourceCardsContractTest::test_source_candidate_card_captures_required_metadata` | PASSED | Source candidate card captures required metadata fields. |
| `tests/test_source_cards_contract.py::SourceCardsContractTest::test_source_card_builds_stable_embedding_chunk_contract` | PASSED | Source card builds stable embedding chunk contract. |
| `tests/test_source_catalog_and_corpus.py::SourceCatalogAndCorpusTest::test_embedding_corpus_manifest_uses_ordered_jsonl_hash` | PASSED | Embedding corpus hashing is deterministic. |
| `tests/test_source_catalog_and_corpus.py::SourceCatalogAndCorpusTest::test_embedding_text_is_bounded_for_provider_limits` | PASSED | Embedding text is bounded to avoid provider length failures. |
| `tests/test_source_catalog_and_corpus.py::SourceCatalogAndCorpusTest::test_source_catalog_materializes_cards_and_embedding_chunks` | PASSED | SQLite source catalog materializes cards and embedding chunks. |
| `tests/test_workflow_graph.py::test_workflow_artifacts_cover_graph_and_ui_contracts` | PASSED | Workflow/UI artifact types exist. |
| `tests/test_workflow_graph.py::test_graph_contract_names_roles_budgets_and_trace_owner` | PASSED | Node contracts, roles, budgets, and trace ownership exist. |
| `tests/test_workflow_graph.py::test_run_graph_emits_machine_readable_trace` | PASSED | Narrow graph smoke emits machine-readable trace in gated state. |
| `tests/test_yandex_ai_studio.py::test_qwen_client_uses_verified_base_url_and_api_key_header` | PASSED | Yandex AI Studio client uses verified OpenAI-compatible base URL and API-key header. |
| `tests/test_yandex_ai_studio.py::test_structured_output_helper_sends_json_schema` | PASSED | Structured output helper sends JSON schema format. |
| `tests/test_yandex_ai_studio.py::test_spike_report_records_credential_gate_and_deepseek_fallback_note` | PASSED | Yandex spike report records credential gate and historical DeepSeek fallback note. |

### Failed Test Detail

Failure:

```text
FAILED tests/test_demo_readiness.py::test_demo_readiness_reports_gates_without_dense_success
AssertionError: assert 'stale' in {'gated_skip', 'ready'}
```

Interpretation:

The old test accepted only `ready` or `gated_skip`. The current system reports `stale`, which is more accurate after the full-corpus recovery:

- prepared corpus has 36,321 chunks;
- main `embedding-index-manifest.json` still points to the old 11-card corpus hash;
- main Qdrant vector count is still `0`;
- full embedding build is still running.

This failure is not random. It exposes a real acceptance blocker: demo readiness artifacts are not current after the full-corpus rebuild.

## Current Demo Readiness

Command:

```bash
python3 -m app.demo.run_demo ... --json-output .planning/phases/01-data-architecture-research/demo-readiness.current.json
```

Result:

```json
{
  "overall_status": "blocked",
  "source_cards_status": "ready",
  "source_catalog_status": "ready",
  "embedding_corpus_status": "ready",
  "qdrant_status": "stale",
  "dense_retrieval_ready": false,
  "retrieval_eval_status": "gated",
  "extraction_eval_status": "gated",
  "data_relevance_eval_status": "gated",
  "blocked_components": ["qdrant"],
  "gated_components": ["data_relevance_eval", "extraction_eval", "retrieval_eval"]
}
```

Prepared counts:

```json
{
  "source_card_count": 36321,
  "catalog_source_cards_count": 36321,
  "embedding_chunk_count": 36321,
  "qdrant_vector_count": 0,
  "vector_store": "qdrant",
  "qdrant_collection": "phase1_source_cards"
}
```

Decision:

Demo readiness is not acceptable for MVP. It is acceptable as diagnostic evidence that the system refuses to claim readiness falsely.

## Current Retrieval Evaluation

Command:

```bash
python3 scripts/run_retrieval_spike.py \
  --goldens .planning/phases/01-data-architecture-research/golden-cases.yaml \
  --index-manifest .planning/phases/01-data-architecture-research/embedding-index-manifest.json \
  --output .planning/phases/01-data-architecture-research/retrieval-eval.current.csv \
  --comparison .planning/phases/01-data-architecture-research/retrieval-comparison.current.md \
  --limit 20
```

Result:

- Rows: 20 / 20 golden cases
- Dense status: `gated_skip` for all 20
- Source family match: 14 true, 6 false
- No top candidate: 6 cases

Per-case snapshot:

| Case | Top Source | Top Candidate | Source Family Match | Dense |
|---|---|---|---:|---|
| GC-001 | fedstat | `fedstat:62470:fedstatru/data/parquet/62470.parquet` | true | gated_skip |
| GC-002 | fedstat | `fedstat:40579:fedstatru/data/parquet/40579.parquet` | true | gated_skip |
| GC-003 | none | none | false | gated_skip |
| GC-004 | fedstat | `fedstat:58367:fedstatru/data/parquet/58367.parquet` | true | gated_skip |
| GC-005 | none | none | false | gated_skip |
| GC-006 | fedstat | `fedstat:40479:fedstatru/data/parquet/40479.parquet` | true | gated_skip |
| GC-007 | fedstat | `fedstat:57043:fedstatru/data/parquet/57043.parquet` | true | gated_skip |
| GC-008 | none | none | false | gated_skip |
| GC-009 | fedstat | `fedstat:62127:fedstatru/data/parquet/62127.parquet` | true | gated_skip |
| GC-010 | fedstat | `fedstat:61936:fedstatru/data/parquet/61936.parquet` | true | gated_skip |
| GC-011 | none | none | false | gated_skip |
| GC-012 | fedstat | `fedstat:62275:fedstatru/data/parquet/62275.parquet` | true | gated_skip |
| GC-013 | fedstat | `fedstat:57319:fedstatru/data/parquet/57319.parquet` | true | gated_skip |
| GC-014 | fedstat | `fedstat:58606:fedstatru/data/parquet/58606.parquet` | true | gated_skip |
| GC-015 | none | none | false | gated_skip |
| GC-016 | fedstat | `fedstat:37053:fedstatru/data/parquet/37053.parquet` | true | gated_skip |
| GC-017 | none | none | false | gated_skip |
| GC-018 | fedstat | `fedstat:34089:fedstatru/data/parquet/34089.parquet` | true | gated_skip |
| GC-019 | fedstat | `fedstat:54671:fedstatru/data/parquet/54671.parquet` | true | gated_skip |
| GC-020 | fedstat | `fedstat:34133:fedstatru/data/parquet/34133.parquet` | true | gated_skip |

Analysis:

- The retrieval system is not useless: it often finds a source family and source-card candidates.
- It is not reliable enough for MVP: 6/20 cases return no candidate, all dense retrieval is gated, and several top candidates are semantically weak.
- GC-001 is especially important: for "Какой ВВП России в 2024 году?" the top candidate is a GDP-related share indicator, not the direct GDP indicator. This is unacceptable as final source selection.

Decision:

Retrieval is acceptable as an experimental scaffold. It is not acceptable as an MVP source selector.

## Current Extraction Probes

Command:

```bash
python3 scripts/run_extraction_probes.py \
  --source-catalog-manifest .planning/phases/01-data-architecture-research/source-catalog-manifest.json \
  --report .planning/phases/01-data-architecture-research/extraction-probes.current.md \
  --json-output .planning/phases/01-data-architecture-research/extraction-probes.current.json
```

Result:

| Source | Coverage Status | Extraction Status | Meaning |
|---|---:|---:|---|
| FedStat | ok | skipped_with_reason | Normalizer and SQL-first contract recorded; full wide Parquet extraction is not implemented as an answer path. |
| World Bank | ok | skipped_with_reason | Canonical long-format adapter evidence recorded; full row extraction waits for source-specific filters. |
| CKAN | skipped_with_reason | skipped_with_reason | No promoted CKAN package id available. |

Decision:

Extraction probes are useful architecture evidence. They are not an MVP deterministic extraction path.

## Current Data Relevance Evaluation

Command:

```bash
python3 -m app.evals.run_eval \
  --goldens .planning/phases/01-data-architecture-research/golden-cases.yaml \
  --retrieval-eval .planning/phases/01-data-architecture-research/retrieval-eval.current.csv \
  --extraction-probes .planning/phases/01-data-architecture-research/extraction-probes.current.json \
  --index-manifest .planning/phases/01-data-architecture-research/embedding-index-manifest.json \
  --json-output .planning/phases/01-data-architecture-research/data-relevance-eval.current.json \
  --markdown-output .planning/phases/01-data-architecture-research/data-relevance-eval.current.md
```

Result:

```json
{
  "total_cases": 20,
  "passed": 0,
  "failed": 0,
  "gated": 20,
  "qdrant_status": "gated_skip",
  "dense_status": "gated_skip",
  "extraction_probe_status": "skipped_with_reason"
}
```

Decision:

This is the strongest acceptance signal: 0/20 golden cases pass. Phase 1 cannot be accepted as a functional agent MVP.

## Current Workflow Smoke

Command:

```bash
python3 -m app.workflow.run_graph \
  --goldens .planning/phases/01-data-architecture-research/golden-cases.yaml \
  --case-index 0 \
  --index-manifest .planning/phases/01-data-architecture-research/partial-embedding-index-manifest.json \
  --json-output .planning/phases/01-data-architecture-research/run-graph-smoke.current.json
```

Result:

```json
{
  "status": "ok",
  "route": "Ambiguous lookup",
  "qdrant_status": "partial_ready",
  "coverage_status": "gated",
  "extraction_status": "gated",
  "selected_count": 5,
  "trace_count": 6
}
```

Final answer:

```json
{
  "status": "ok",
  "summary": "Phase 1 graph emitted source-bound trace artifacts; numeric narration is withheld until deterministic extraction returns data.",
  "clarification_question": "Уточните недостающие параметры запроса.",
  "source_ids": ["fedstat:62470:fedstatru/data/parquet/62470.parquet"]
}
```

Analysis:

- Positive: the graph emits machine-readable trace and does not invent numeric values.
- Negative: `final_answer.status=ok` conflicts with `coverage_status=gated` and `extraction_status=gated`.
- Negative: top selected source for the GDP query is not reliable enough.
- Negative: this is still a narrow smoke graph, not the full architecture chain.

Decision:

Workflow smoke is acceptable as trace contract evidence. It is not acceptable as user-facing agent behavior.

## Embedding / Index State

Observed:

```text
embedding-cache.jsonl: 22,293
embedding-corpus.jsonl: 36,321
```

Background process:

```text
PID 77528 running scripts/build_embedding_index.py ... --batch-size 64 --workers 3
```

Interpretation:

The full embedding build is still in progress. The heartbeat monitor should remain active. Until the full index manifest is refreshed, main demo readiness remains blocked/stale.

## Acceptance Decision

Phase 1 is acceptable as a foundation for:

- source-card and embedding corpus contracts;
- full FedStat + World Bank prepared metadata corpus;
- source catalog materialization;
- Qdrant/Yandex embedding build path;
- retrieval/eval scaffolding;
- deterministic extraction probe scaffolding;
- trace/event/UI contracts;
- diagnostic Streamlit shell.

Phase 1 is not acceptable as:

- a functional MVP agent;
- a jury-demo UI;
- a reliable source selector;
- a deterministic data extraction workflow;
- an end-to-end answer generation system;
- a complete implementation of `ARCHITECTURE_STACK.md`.

## Can We Continue From This?

Yes, but only if we treat Phase 1 as infrastructure, not as product behavior.

Continue from it:

- keep the prepared corpus/catalog work;
- keep embedding/index builder;
- keep artifact schemas and trace contracts;
- keep Streamlit only as a codebase starting point, not as final UX;
- keep eval harness but make it stricter.

Do not continue from it unchanged:

- do not present current UI to jury;
- do not call the current graph a full agent;
- do not accept `final_answer.status=ok` when extraction is gated;
- do not trust current retrieval ranking for final source choice;
- do not claim MVP readiness until all 20 golden cases reach correct terminal outcomes; staged implementation order is allowed, but final acceptance is all cases.

## Required Next Phase For Jury MVP

Create a new phase focused on full MVP product behavior:

1. Build a real runtime workflow:
   `User query → Supervisor → Intent Analyst → Research Designer / Direct path → FedStat/WB/CKAN Scouts → Coverage & Schema → Extraction Planner → Deterministic Tools → Methodology Critic → Visualization → Narrator → answer + dataset + script + sources + trace`.

2. Make status semantics strict:
   final answer cannot be `ok` if coverage or extraction is gated.

3. Promote the full golden-case set to real acceptance:
   all 20 cases must end as `passed`, `needs_clarification`, or `not_found`; no golden case may end as `gated`, `stale`, `skipped_with_reason`, or `no_candidate`.

4. Fix source ranking:
   direct indicator intent must beat weak contextual matches.

5. Turn Streamlit into the actual jury UI:
   query input runs the workflow, shows state transitions, selected/rejected sources, coverage, generated SQL/script, dataset, chart, answer, and limitations.

6. Make acceptance binary:
   MVP is not accepted until selected demo cases return sourced numeric output and all gates are visible.
