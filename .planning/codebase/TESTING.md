# Testing Patterns

**Analysis Date:** 2026-05-10

## Test Framework

**Runner:**
- `pytest` is used through `python3 -m pytest`.
- No `pytest.ini`, `pyproject.toml`, `setup.cfg`, or `tox.ini` is detected.
- Tests live in `tests/` and include both pytest function tests and `unittest.TestCase` classes.

**Assertion Library:**
- Native `assert` in pytest-style tests: `tests/test_eval_runner.py`, `tests/test_workflow_graph.py`, `tests/test_hybrid_retrieval.py`.
- `unittest.TestCase` assertions in older contract tests: `tests/test_source_cards_contract.py`, `tests/test_source_card_builders.py`, `tests/test_source_catalog_and_corpus.py`.

**Run Commands:**
```bash
python3 -m pytest -q              # Run all tests, current result: 26 passed / 1 failed
python3 -m pytest -vv             # Run all tests with full case names
python3 -m pytest tests/test_eval_runner.py -q
```

No watch-mode or coverage command is configured.

## Current Results

**Observed 2026-05-10:**
- Command: `python3 -m pytest -q`
- Result: 27 collected, 26 passed, 1 failed.
- Failing test: `tests/test_demo_readiness.py::test_demo_readiness_reports_gates_without_dense_success`.
- Failure reason: `assess_demo_readiness()` reports `qdrant_status="stale"` while the test expects `{"ready", "gated_skip"}`.
- Interpretation: the failure is a real readiness state. `.planning/phases/01-data-architecture-research/embedding-index-manifest.json` points to an old corpus hash while `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json` has 36,321 chunks.

**Current Gate Commands:**
```bash
python3 -m app.demo.run_demo \
  --source-cards-manifest .planning/phases/01-data-architecture-research/source-cards-manifest.json \
  --source-catalog-manifest .planning/phases/01-data-architecture-research/source-catalog-manifest.json \
  --embedding-corpus-manifest .planning/phases/01-data-architecture-research/embedding-corpus-manifest.json \
  --index-manifest .planning/phases/01-data-architecture-research/embedding-index-manifest.json \
  --retrieval-eval .planning/phases/01-data-architecture-research/retrieval-eval.csv \
  --extraction-probes .planning/phases/01-data-architecture-research/extraction-probes.json \
  --data-relevance-eval .planning/phases/01-data-architecture-research/data-relevance-eval.json \
  --json-output /tmp/matmod-demo-readiness.json
```

Observed result: `overall_status=blocked`, `qdrant_status=stale`, `dense_retrieval_ready=false`, `retrieval_eval_status=gated`, `extraction_eval_status=gated`, `data_relevance_eval_status=gated`.

```bash
python3 scripts/run_retrieval_spike.py \
  --goldens .planning/phases/01-data-architecture-research/golden-cases.yaml \
  --index-manifest .planning/phases/01-data-architecture-research/embedding-index-manifest.json \
  --output /tmp/matmod-retrieval-eval.csv \
  --comparison /tmp/matmod-retrieval-comparison.md \
  --limit 20
```

Observed result: 20 rows, all 20 dense rows `gated_skip`, 14 source-family matches, 6 no-candidate rows (`GC-003`, `GC-005`, `GC-008`, `GC-011`, `GC-015`, `GC-017`).

```bash
python3 scripts/run_extraction_probes.py \
  --source-catalog-manifest .planning/phases/01-data-architecture-research/source-catalog-manifest.json \
  --report /tmp/matmod-extraction-probes.md \
  --json-output /tmp/matmod-extraction-probes.json
```

Observed result: 3 probes. FedStat and World Bank coverage are `ok`; all extraction statuses are `skipped_with_reason`; CKAN coverage is `skipped_with_reason` because no promoted CKAN package id is available.

```bash
python3 -m app.evals.run_eval \
  --goldens .planning/phases/01-data-architecture-research/golden-cases.yaml \
  --retrieval-eval .planning/phases/01-data-architecture-research/retrieval-eval.current.csv \
  --extraction-probes .planning/phases/01-data-architecture-research/extraction-probes.current.json \
  --index-manifest .planning/phases/01-data-architecture-research/embedding-index-manifest.json \
  --json-output /tmp/matmod-data-relevance-eval.json \
  --markdown-output /tmp/matmod-data-relevance-eval.md
```

Observed result: 20 total, 0 passed, 0 failed, 20 gated, `qdrant_status=gated_skip`, `dense_status=gated_skip`, `extraction_probe_status=skipped_with_reason`.

## Test File Organization

**Location:**
- Tests are centralized in `tests/`.
- There are no co-located `*_test.py` files under `app/`.

**Naming:**
- Test files use `test_*.py`: `tests/test_embedding_index.py`, `tests/test_yandex_ai_studio.py`, `tests/test_demo_readiness.py`.
- Test functions use `test_<behavior>()`.
- `unittest.TestCase` classes use descriptive names ending in `Test`: `SourceCardsContractTest`, `SourceCatalogAndCorpusTest`, `SourceCardBuildersTest`.

**Structure:**
```text
tests/
├── test_source_cards_contract.py       # Pydantic artifact contracts
├── test_source_card_builders.py        # FedStat, World Bank, CKAN source-card builders
├── test_source_catalog_and_corpus.py   # SQLite catalog and embedding corpus
├── test_embedding_index.py             # Yandex embedding config and Qdrant manifest gates
├── test_hybrid_retrieval.py            # BM25, dense status, rerank status CSV
├── test_workflow_graph.py              # workflow artifacts, graph contracts, run_graph smoke
├── test_deterministic_tools_and_trace.py
├── test_eval_runner.py
├── test_demo_readiness.py
└── test_yandex_ai_studio.py
```

## Test Structure

**Suite Organization:**
```python
def test_eval_runner_records_gated_components_without_silent_success(tmp_path: Path) -> None:
    from app.evals.run_eval import run_evaluation

    result = run_evaluation(
        goldens_path=Path(".planning/phases/01-data-architecture-research/golden-cases.yaml"),
        retrieval_eval_path=Path(".planning/phases/01-data-architecture-research/retrieval-eval.csv"),
        extraction_probes_path=Path(".planning/phases/01-data-architecture-research/extraction-probes.json"),
        index_manifest_path=Path(".planning/phases/01-data-architecture-research/embedding-index-manifest.json"),
        json_output=tmp_path / "data-relevance-eval.json",
        markdown_output=tmp_path / "data-relevance-eval.md",
    )

    assert result["gated"] > 0
    assert not any(item["status"] == "passed" and item["gated_reasons"] for item in result["cases"])
```

**Patterns:**
- Import the unit under test inside the test function. This keeps import failures close to the behavior being tested and helps tests that monkeypatch modules like `requests`.
- Use `tmp_path` or `tempfile.TemporaryDirectory()` for generated artifacts. Examples: `tests/test_eval_runner.py`, `tests/test_embedding_index.py`, `tests/test_source_catalog_and_corpus.py`.
- Use committed `.planning/` artifacts for integration-style gates. Examples: `tests/test_demo_readiness.py`, `tests/test_eval_runner.py`, `tests/test_deterministic_tools_and_trace.py`.
- Assert both machine-readable output and written artifact contents: `tests/test_eval_runner.py` reads the written JSON/Markdown; `tests/test_hybrid_retrieval.py` reads the written CSV and comparison Markdown.
- For Phase 2, add tests that run all 20 golden cases, not only bounded subsets.

## Mocking

**Framework:** pytest `monkeypatch` and local fake classes.

**Patterns:**
```python
def fake_post(url: str, **kwargs: Any) -> _Response:
    captured["url"] = url
    captured.update(kwargs)
    return _Response()

monkeypatch.setattr("requests.post", fake_post)
```

Used in `tests/test_yandex_ai_studio.py` to validate the Yandex AI Studio endpoint, `Api-Key` auth header, and structured-output payload without making a live request.

```python
monkeypatch.setenv("YANDEX_AI_STUDIO_API_KEY", "")
monkeypatch.setenv("QDRANT_MODE", "local")
monkeypatch.setenv("QDRANT_COLLECTION", "phase1_source_cards_test")
```

Used in `tests/test_embedding_index.py` to force credential-gated behavior and Qdrant config fields.

**What to Mock:**
- HTTP calls to Yandex AI Studio and embedding endpoints: `requests.post` in `app/llm/yandex_ai_studio.py` and `app/retrieval/embedding_index.py`.
- Environment variables for Yandex, Qdrant, reranker, and dimensions.
- Temporary corpus and manifest files for retrieval/index tests.

**What NOT to Mock:**
- Artifact serialization and deserialization. Tests should read actual JSON/CSV/Markdown outputs.
- Pydantic validation for artifact contracts.
- Deterministic tool results once source-specific extraction is implemented for Phase 2. Numeric outputs must be exercised through code/tool artifacts, not mocked final answers.
- Phase 2 golden-case acceptance. The final gate must evaluate all 20 cases in `.planning/phases/01-data-architecture-research/golden-cases.yaml`.

## Fixtures and Factories

**Test Data:**
```python
corpus_artifact.write_text(
    "\n".join(json.dumps(doc, ensure_ascii=False) for doc in docs) + "\n",
    encoding="utf-8",
)
```

Used in `tests/test_hybrid_retrieval.py` to create a tiny source-card corpus and manifest.

```python
card = SourceCandidateCard(
    source="ckan",
    builder_source="ckan_package_search",
    dataset_id="emiss_57319",
    resource_id="57319.parquet",
    title="Gross domestic product in market prices",
    match_mode=MatchMode.CKAN_DISCOVERY,
    provenance_url="https://fedstat.ru/indicator/57319",
    why_matched="CKAN discovery by indicator code.",
)
```

Used in `tests/test_source_cards_contract.py` to validate source-card and embedding chunk contracts.

**Location:**
- No shared `conftest.py` or fixture module exists.
- Fixtures are inline per test file.
- Phase 2 should introduce shared factories only when multiple tests need the same `IntentFrame`, `SourceCandidateCard`, `CoverageReport`, `DatasetArtifact`, or golden-case result shape.

## Coverage

**Requirements:** No coverage threshold is enforced.

**View Coverage:**
```bash
# Not configured
```

**Observed Coverage Shape:**
- Good contract coverage for source cards, embedding manifests, Yandex client headers, retrieval CSV fields, eval runner gates, demo readiness, deterministic tool exports, and workflow trace contracts.
- Limited product behavior coverage for full user-query execution, source-specific extraction, final answer semantics, Streamlit workflow execution, and all 20 golden cases as a strict pass/clarify/not-found acceptance set.

## Test Types

**Unit Tests:**
- Pydantic artifact contract tests: `tests/test_source_cards_contract.py`, `tests/test_workflow_graph.py`, `tests/test_deterministic_tools_and_trace.py`.
- Pure helper/config tests: `tests/test_embedding_index.py`, `tests/test_hybrid_retrieval.py`.
- Builder tests for FedStat, World Bank, and CKAN source cards: `tests/test_source_card_builders.py`.

**Integration Tests:**
- Manifest and local artifact integration: `tests/test_source_catalog_and_corpus.py`, `tests/test_demo_readiness.py`.
- Eval harness integration over committed Phase 1 artifacts: `tests/test_eval_runner.py`.
- Extraction probe integration over the source catalog manifest: `tests/test_deterministic_tools_and_trace.py`.
- Workflow smoke integration through `run_golden_case()` in `tests/test_workflow_graph.py`.

**E2E Tests:**
- Not used.
- Streamlit is import-tested in `tests/test_demo_readiness.py`, but there is no browser or Streamlit runtime E2E test.
- Phase 2 needs an E2E-style CLI gate that runs the real workflow over all 20 golden cases and validates terminal statuses and artifact presence.

## Eval Harness

**Golden Cases:**
- The canonical set is `.planning/phases/01-data-architecture-research/golden-cases.yaml`.
- It contains all 20 Phase 2 acceptance cases: `GC-001` through `GC-020`.
- Categories include `simple`, `comparative`, `research`, `derived_metric`, `ambiguous`, and `no_data`.
- Phase 2 final acceptance must cover all 20 cases. Staged implementation order is allowed, but final acceptance cannot be a subset.

**Rubric:**
- `.planning/phases/01-data-architecture-research/eval-rubric.md` defines hard fail rules and a 16-point scoring model.
- Hard fail examples include unsupported numeric claims, fabricated source metadata, no-data requests answered confidently, LLM table reading, missing trace decisions, and raw numeric data in embeddings.
- Passing evidence requires structured intent, source cards, coverage preview, deterministic extraction, rejection/no-data honesty, and trace completeness.

**Current Runner:**
- `app/evals/run_eval.py` consumes `golden-cases.yaml`, `retrieval-eval.csv`, `extraction-probes.json`, `embedding-index-manifest.json`, and representative `run-graph-*.json` files.
- It writes JSON and Markdown with aggregate counts and per-case statuses.
- Current scoring is an infrastructure gate, not the final Phase 2 rubric implementation. It records `passed`, `failed`, and `gated`, with all current cases gated when dense retrieval or extraction is unavailable.

**Phase 2 Gate Requirements:**
- Add or extend an eval command that produces one row/result for each of `GC-001` through `GC-020`.
- Each final case status must be exactly one of `passed`, `needs_clarification`, or `not_found`.
- `gated`, `stale`, `skipped_with_reason`, and `no_candidate` are not valid final outcomes.
- A case with `FinalAnswer.status="ok"` and gated coverage/extraction must fail.
- Every `passed` case must include source provenance, coverage evidence, deterministic extraction evidence, dataset/script artifacts where relevant, and trace events.

## Common Patterns

**Async Testing:**
```python
# Not used. Current code and tests are synchronous.
```

**Error Testing:**
```python
rows = run_duckdb_query("SELECT 1 AS value, 'source-bound' AS label")
assert rows == [{"value": 1, "label": "source-bound"}]
```

Use direct function calls for deterministic tools. Add explicit negative tests for unsafe SQL in `run_duckdb_query()` when expanding deterministic extraction in Phase 2.

```python
result = run_golden_case(
    goldens_path=goldens,
    case_index=0,
    index_manifest_path=manifest,
)
assert result["status"] == "gated"
assert "unsupported_numeric_claim" not in json.dumps(result)
```

Use workflow smoke tests to verify trace and no unsupported numeric claims. For Phase 2, this should become a full matrix over all 20 golden cases.

## Acceptance Gaps

**Pytest Gap:**
- `tests/test_demo_readiness.py` does not accept `stale` as a valid readiness state even though `app/demo/run_demo.py` intentionally reports it. Update the test or refresh the manifest only when the embedding index is actually current.

**Workflow Gap:**
- `app/workflow/run_graph.py` is a narrow Phase 1 graph slice. It does not implement the full Phase 2 workflow:
  `User query -> Supervisor -> Intent Analyst -> Research Designer / Direct path -> FedStat/WB/CKAN Scouts -> Coverage & Schema -> Extraction Planner -> Deterministic Tools -> Methodology Critic -> Visualization -> Narrator`.

**Status Semantics Gap:**
- The current workflow smoke can produce `final_answer.status="ok"` while coverage and extraction are `gated`. Phase 2 tests must forbid this.

**Retrieval Gap:**
- Current retrieval eval over all 20 golden cases returns all dense rows as `gated_skip`, 14 source-family matches, and 6 no-candidate cases.
- `GC-001` has a known ranking risk: GDP-related contextual candidates can outrank the direct GDP indicator. Add tests for direct indicator intent beating weak contextual matches.

**Extraction Gap:**
- `scripts/run_extraction_probes.py` records coverage/probe evidence, but extraction remains `skipped_with_reason` for FedStat, World Bank, and CKAN.
- Phase 2 needs deterministic source-specific extraction tests for selected golden cases and eventually all `passed` cases.

**UI Gap:**
- `app/ui/streamlit_app.py` is a diagnostic shell. It imports readiness and shows trace artifacts, but it does not submit a user query into the evaluated workflow.
- Phase 2 UI tests should verify that Streamlit calls the same workflow/eval path used by tests.

**CKAN Gap:**
- CKAN has bounded tool functions in `app/data/deterministic_tools.py` and source-card builder coverage in `tests/test_source_card_builders.py`, but current probes report no promoted CKAN package id.
- Phase 2 needs tests for bounded package/resource search, cached promoted metadata, rejection reasons, and not-found handling.

---

*Testing analysis: 2026-05-10*
