# Coding Conventions

**Analysis Date:** 2026-05-10

## Naming Patterns

**Files:**
- Use snake_case Python module names in `app/`, `scripts/`, and `tests/`: `app/artifacts/source_cards.py`, `app/workflow/run_graph.py`, `scripts/run_retrieval_spike.py`, `tests/test_eval_runner.py`.
- Group modules by product boundary: artifacts in `app/artifacts/`, retrieval in `app/retrieval/`, workflow in `app/workflow/`, deterministic data tools in `app/data/`, UI adapters in `app/ui/`, demo readiness in `app/demo/`.
- Use hyphenated lowercase artifact names under `.planning/phases/01-data-architecture-research/`: `golden-cases.yaml`, `retrieval-eval.current.csv`, `data-relevance-eval.current.json`, `phase1-test-acceptance.md`.
- Use explicit `*.current.*` suffixes for acceptance snapshots that should not overwrite the original Plan 1 artifacts: `.planning/phases/01-data-architecture-research/retrieval-eval.current.csv`, `.planning/phases/01-data-architecture-research/extraction-probes.current.json`.

**Functions:**
- Use snake_case verbs for behavior: `run_evaluation()` in `app/evals/run_eval.py`, `assess_demo_readiness()` in `app/demo/run_demo.py`, `build_embedding_corpus()` in `scripts/build_embedding_corpus.py`, `run_extraction_probes()` in `scripts/run_extraction_probes.py`.
- Prefix private helpers with `_`: `_score_case()` in `app/evals/run_eval.py`, `_qdrant_status()` in `app/demo/run_demo.py`, `_tokens()` in `app/retrieval/hybrid_retrieval.py`.
- Keep CLI entrypoints named `main()` and guard them with `if __name__ == "__main__": main()`: `app/evals/run_eval.py`, `app/workflow/run_graph.py`, `scripts/run_retrieval_spike.py`.

**Variables:**
- Use descriptive artifact variable names instead of short abbreviations: `goldens_path`, `retrieval_eval_path`, `extraction_probes_path`, `index_manifest_path` in `app/evals/run_eval.py`.
- Use status names as strings from the product vocabulary: `ready`, `blocked`, `gated`, `gated_skip`, `stale`, `skipped_with_reason`, `no_candidate`, `needs_clarification`, `not_found`.
- Use `Path` objects for filesystem inputs and outputs: `DemoInputs` in `app/demo/run_demo.py`, `run_golden_case()` in `app/workflow/run_graph.py`, `run_retrieval_evaluation()` in `scripts/run_retrieval_spike.py`.

**Types:**
- Use `PascalCase` for Pydantic models and dataclasses: `SourceCandidateCard` in `app/artifacts/source_cards.py`, `TraceEvent` in `app/artifacts/workflow_artifacts.py`, `GraphState` in `app/workflow/graph_contract.py`, `DemoInputs` in `app/demo/run_demo.py`.
- Use `Literal` type aliases for bounded state vocabularies: `WorkflowStatus` and `QueryCategory` in `app/artifacts/workflow_artifacts.py`, `RouteName` in `app/workflow/graph_contract.py`, `IndexState` in `app/ui/trace_models.py`.
- Use `Enum` only where the value is a stable artifact contract, such as `MatchMode` in `app/artifacts/source_cards.py`.

## Code Style

**Formatting:**
- No formatter config is detected. There is no `pyproject.toml`, `.prettierrc`, `ruff.toml`, or `.flake8`.
- Follow the existing Black-compatible Python style: 4-space indentation, double quotes for strings, line wrapping around 88-100 columns, one blank line between top-level functions/classes.
- Keep `from __future__ import annotations` at the top of Python modules. It appears throughout `app/`, `scripts/`, and `tests/`.
- Prefer explicit keyword-only parameters for public orchestration functions: `run_evaluation()` in `app/evals/run_eval.py`, `run_golden_case()` in `app/workflow/run_graph.py`, `run_retrieval_evaluation()` in `scripts/run_retrieval_spike.py`.

**Linting:**
- No linting config or lint command is detected.
- Enforce style through local consistency and pytest coverage until a linter is added.
- Avoid broad `except Exception` except at boundaries where the current code intentionally records optional dependency or live API skips: `export_csv_parquet_manifest()` in `app/data/deterministic_tools.py`, `_ckan_probe()` in `scripts/run_extraction_probes.py`.

## Import Organization

**Order:**
1. `from __future__ import annotations`
2. Standard library imports: `argparse`, `csv`, `json`, `Path`, `Any`
3. Third-party imports: `yaml`, `pydantic`, `duckdb`, `requests`, `qdrant_client`
4. Local `app.*` imports

Example from `app/workflow/run_graph.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from app.artifacts.workflow_artifacts import CoverageReport, DatasetArtifact
```

**Path Aliases:**
- No package alias configuration is detected.
- Use absolute imports from the repository package: `from app.artifacts.workflow_artifacts import TraceEvent`.
- Scripts that are run as direct files add the repo root to `sys.path`: `scripts/run_retrieval_spike.py`, `scripts/run_extraction_probes.py`, `scripts/build_embedding_corpus.py`.
- Prefer module execution for `app/` entrypoints: `python3 -m app.demo.run_demo`, `python3 -m app.workflow.run_graph`, `python3 -m app.evals.run_eval`. Direct `python3 app/demo/run_demo.py` is documented as failing with `ModuleNotFoundError` in `.planning/phases/01-data-architecture-research/phase1-actual-state-verification.md`.

## Error Handling

**Patterns:**
- Raise `ValueError` for invalid local inputs and unsafe operations: `run_duckdb_query()` in `app/data/deterministic_tools.py` rejects non-`SELECT`/`WITH` SQL; `cosine_distance()` in `app/retrieval/embedding_index.py` rejects vectors with unequal lengths.
- Raise `RuntimeError` for missing required runtime configuration or malformed external responses: `YandexAIStudioConfig.from_env()` and `YandexAIStudioClient.structured_chat()` in `app/llm/yandex_ai_studio.py`.
- Use explicit gate data instead of pretending success when credentials or artifacts are unavailable: `GatedSkipStatus` in `app/retrieval/embedding_index.py`, `qwen_credential_gate()` in `app/llm/yandex_ai_studio.py`, `assess_demo_readiness()` in `app/demo/run_demo.py`.
- Record `gated`, `gated_skip`, `stale`, and `skipped_with_reason` as structured artifact fields. Do not collapse these into `ok`.
- For Phase 2, final answer semantics must be stricter than the current Phase 1 graph: `FinalAnswer.status` must not be `ok` when `CoverageReport.status` or `ExtractionPlan.status` is `gated`. The current violation is documented in `.planning/phases/01-data-architecture-research/phase1-test-acceptance.md` and occurs in `app/workflow/run_graph.py`.

## Logging

**Framework:** `print` and machine-readable artifacts.

**Patterns:**
- CLI commands print compact JSON or one-line summaries: `app/demo/run_demo.py` prints `overall_status`, `qdrant_status`, `dense_retrieval_ready`, and output path; `app/evals/run_eval.py` prints `total_cases` and `qdrant_status`.
- Durable evidence is written to JSON, CSV, and Markdown files rather than logs: `data-relevance-eval.json`, `retrieval-eval.csv`, `extraction-probes.json`, `embedding-index-build.md`.
- For new Phase 2 workflow code, emit `TraceEvent` records from `app/artifacts/workflow_artifacts.py` and include artifact ids in the trace instead of relying on console logs.

## Comments

**When to Comment:**
- Use docstrings for artifact contracts and public behavior. Most Pydantic models in `app/artifacts/source_cards.py` and `app/artifacts/workflow_artifacts.py` have concise docstrings.
- Use short comments only for non-obvious policy decisions, such as the source-bound quality gate note in `app/evals/run_eval.py`.
- Avoid comments that restate simple assignments.

**JSDoc/TSDoc:**
- Not applicable. The codebase is Python-only.

## Function Design

**Size:**
- Keep public functions focused on one workflow boundary. Current examples: `run_evaluation()` scores existing artifacts in `app/evals/run_eval.py`; `assess_demo_readiness()` reads manifests and synthesizes readiness in `app/demo/run_demo.py`; `run_golden_case()` runs a single golden case in `app/workflow/run_graph.py`.
- Split scoring, rendering, and IO into helpers. `app/evals/run_eval.py` separates `_load_goldens()`, `_score_case()`, `_render_markdown()`, and `main()`.
- Large modules exist and should be treated carefully: `app/demo/run_demo.py` has 372 lines, `app/artifacts/source_cards.py` has 336 lines, `app/retrieval/hybrid_retrieval.py` has 313 lines, and `app/workflow/run_graph.py` has 296 lines.

**Parameters:**
- Use keyword-only parameters for orchestration and script-callable functions.
- Use `Path` parameters for artifacts and `dict[str, Any]` for loaded JSON payloads.
- For live APIs, expose bounded limits and injectable endpoints: `ckan_package_search(query, rows=5, endpoint=None)` and `ckan_package_show(package_id, endpoint_root=None)` in `app/data/deterministic_tools.py`.

**Return Values:**
- Return typed Pydantic models for durable artifacts: `DatasetArtifact` and `VisualizationSpec` in `app/data/deterministic_tools.py`.
- Return plain JSON-serializable dictionaries from CLI/workflow aggregators: `run_evaluation()` in `app/evals/run_eval.py`, `assess_demo_readiness()` in `app/demo/run_demo.py`, `run_golden_case()` in `app/workflow/run_graph.py`.
- Use `model_dump(mode="json")` or `model_dump()` before writing Pydantic artifacts to disk.

## Module Design

**Exports:**
- There are no barrel exports in `__init__.py`; the `app/*/__init__.py` files are empty. Import concrete modules directly.
- Keep canonical artifact ownership stable:
  - `TraceEvent` belongs in `app/artifacts/workflow_artifacts.py`.
  - `SourceCandidateCard`, `EvidenceBundle`, and embedding corpus contracts belong in `app/artifacts/source_cards.py`.
  - UI view models belong in `app/ui/trace_models.py` and must import `TraceEvent` rather than redefining it.

**Barrel Files:**
- Not used. Do not add broad `app.artifacts import *` style exports unless the codebase adopts that pattern explicitly.

## Artifact Conventions

**Artifact Schemas:**
- Define schemas with Pydantic `BaseModel` and `ConfigDict(extra="forbid")`: `SourceCandidateCard`, `EmbeddingDocument`, `CoverageReport`, `ExtractionPlan`, `DatasetArtifact`, `FinalAnswer`, `TraceEvent`.
- Use `Field(default_factory=list)` and `Field(default_factory=dict)` for mutable defaults.
- Preserve source-bound separation: source cards, retrieval evidence, coverage reports, extraction plans, datasets, visualization specs, critique, final answer, feedback, and trace are separate artifacts.

**Artifact Paths:**
- Phase evidence lives under `.planning/phases/01-data-architecture-research/`.
- Local/generated heavy data lives under `.local/dataagent/phase1/` and is ignored by `.gitignore`.
- SQL probe artifacts live under `.planning/phases/01-data-architecture-research/extraction-probe-artifacts/`.
- Tests should write temporary artifacts to `tmp_path` instead of mutating committed `.planning/` artifacts unless a phase plan explicitly requires refreshing evidence.

**Source-Bound Rules:**
- Numbers must come only from deterministic tools or trusted source adapters. `run_duckdb_query()` in `app/data/deterministic_tools.py` is the core current deterministic SQL tool.
- LLM code in `app/llm/yandex_ai_studio.py` may classify, plan, select, and narrate, but must not read table values or invent numeric facts.
- Embedding input is source-card metadata only. `SourceCandidateCard.to_embedding_text()` in `app/artifacts/source_cards.py` excludes raw numeric observations and generated answers through `_NON_EMBEDDABLE_METADATA_KEYS` and `EmbeddingIndexContract.excluded_content`.
- CKAN access must stay bounded and trusted. Use `ckan_package_search()` and `ckan_package_show()` from `app/data/deterministic_tools.py`; do not treat CKAN as general web search.

## Phase 2 Implementation Guidance

**Golden Case Target:**
- Phase 2 jury MVP must target all 20 cases in `.planning/phases/01-data-architecture-research/golden-cases.yaml`.
- Valid final outcomes are `passed`, `needs_clarification`, and `not_found`.
- Invalid final outcomes are `gated`, `stale`, `skipped_with_reason`, `no_candidate`, unsupported numeric claims, and `final_answer.status=ok` while coverage or extraction is gated.

**Patterns To Preserve:**
- Keep full prepared source-card/catalog/corpus artifacts and manifests from Phase 1.
- Continue using Qdrant as the vector-store abstraction through `app/retrieval/embedding_index.py`.
- Preserve the verified Yandex AI Studio chat-completions behavior in `app/llm/yandex_ai_studio.py`: base URL `https://llm.api.cloud.yandex.net/v1` and `Authorization: Api-Key ...`.
- Preserve document/query embedding split from `app/retrieval/embedding_index.py`: `text-search-doc` for source-card chunks and `text-search-query` for natural-language queries.
- Reuse `TraceEvent` and artifact models instead of adding duplicate UI-local schemas.

---

*Convention analysis: 2026-05-10*
