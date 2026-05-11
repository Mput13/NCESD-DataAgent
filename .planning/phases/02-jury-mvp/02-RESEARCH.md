# Phase 02: jury-mvp - Research

**Researched:** 2026-05-10  
**Domain:** source-bound economic data agent, LangGraph workflow, deterministic statistical extraction, Streamlit response surface  
**Confidence:** HIGH for repo/current-state findings; MEDIUM for external API/runtime recommendations

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Phase 2 implements the full `.planning/ARCHITECTURE_STACK.md` capability set as the minimum jury prototype.
- **D-02:** Do not simplify Phase 2 into a "representative" 2-3 case demo. The final acceptance set is all 20 golden cases in `.planning/phases/01-data-architecture-research/golden-cases.yaml`.
- **D-03:** The planner decides implementation waves autonomously. Preferred execution style is fast, parallelizable workstreams where independent parts can run at the same time.
- **D-03A:** Plans may stage implementation waves, but every wave must preserve the final full-functionality target and must not redefine success downward.
- **D-04:** Phase 1 infrastructure artifacts are reused and upgraded; they are not evidence that product behavior is complete.
- **D-05:** Current `gated`, `stale`, `skipped_with_reason`, `no_candidate`, or probe-only outputs are accepted only as diagnostic Phase 1 evidence, never as Phase 2 final outcomes.
- **D-06:** Valid final golden-case terminal outcomes are only `passed`, `needs_clarification`, and `not_found`.
- **D-07:** `passed` means the request traverses the complete pipeline and returns an answer: relevant source selection, coverage checked, deterministic extraction completed, source-bound answer produced, dataset/script/artifacts available, visualization when relevant, and trace visible.
- **D-08:** `needs_clarification` means the request is genuinely ambiguous and the system asks a specific useful question instead of pretending to answer.
- **D-09:** `not_found` means trusted/available sources were checked and rejected with explicit evidence.
- **D-10:** `final_answer.status=ok` while coverage or extraction is gated is a bug to fix, not an acceptable partial success.
- **D-11:** Implement the real workflow runtime that maps to the architecture stack roles: Supervisor, Intent Analyst, Research Designer, FedStat Scout, World Bank Scout, CKAN Scout, Coverage & Schema, Extraction Planner, Deterministic Tools, Methodology Critic, Visualization, and Narrator.
- **D-12:** The current `Phase1Graph` narrow smoke runner is a seed and trace-contract reference only. Phase 2 must replace or extend it into real product execution.
- **D-13:** Use one typed workflow state object through the graph. The remote workstream `AgentState` idea may be ported selectively if it preserves current Phase 1 artifacts and tests.
- **D-14:** Simple direct lookups may skip unnecessary agents, but the implementation must still have the full architecture available for comparative, research, ambiguous, derived-metric, and no-data queries.
- **D-15:** Human-in-the-loop clarification and repair routing are in scope for Phase 2 because they are required for valid `needs_clarification` behavior and user feedback/fix requests.
- **D-15A:** Implement the full contract from `.planning/ARCHITECTURE_STACK.md`, not a simplified local substitute. This includes the complete artifact/state/trace contract needed by downstream UI and evaluation surfaces.
- **D-16:** FedStat, World Bank, and CKAN are all first-class source paths in Phase 2.
- **D-17:** CKAN is a trusted NSED catalog API, not general web search. Use bounded `package_search` / `package_show`, compressed source cards, and promoted metadata only.
- **D-18:** Qdrant remains the vector-store abstraction. Do not replace it with an ad hoc local vector path.
- **D-19:** Run full embedding/Qdrant index refresh in parallel with workflow, extraction, eval, and response-contract work. Do not serialize the whole phase behind index completion if useful work can proceed independently.
- **D-19A:** Final readiness cannot remain stale or gated. The target path uses real embedding calls and a current Qdrant index/readiness artifact.
- **D-20:** Retrieval ranking must be good enough that direct indicator intents beat weak contextual matches. The known GC-001 GDP source-ranking issue is a Phase 2 blocker.
- **D-21:** Source scouts must return selected and rejected source cards with reasons, match modes, risks, units, coverage hints, and provenance links.
- **D-22:** Coverage Preview must check actual periods, geographies, units, frequency, missing values, source-specific schema risks, and alternatives before extraction.
- **D-23:** Deterministic extraction must work for FedStat wide Parquet, World Bank long Parquet, and promoted CKAN resources where golden cases require them.
- **D-24:** LLMs may classify, plan, select, critique, and narrate, but numeric values must come only from deterministic tools or trusted source adapters.
- **D-25:** Extraction Planner should select safe operations and SQL/Python templates; it must not become an unconstrained free-form code generator.
- **D-26:** Dataset exports must include dataset file, script, manifest, provenance, quality flags, and source links.
- **D-27:** Methodology Critic must block or repair bad outputs before narration. It must catch unit mismatches, missing coverage, wrong aggregations, unsupported sources, and no-data dishonesty.
- **D-28:** Visualization is part of the full jury workflow when relevant. It must be generated from `DatasetArtifact`, not from LLM text.
- **D-29:** Narrator must produce different answer shapes for direct lookup, comparison, research, clarification, and not-found cases, while preserving sources, methodology, limitations, and trace.
- **D-30:** Unsupported numeric claims are hard failures even if the prose looks plausible.
- **D-31:** Do not build a full custom frontend in Phase 2 planning unless a later explicit request changes this. Prepare a frontend-facing response format suitable for a chat-like LLM interface similar to Claude.
- **D-32:** The response contract must support message-style output plus structured blocks for answer, citations/sources, dataset artifacts, generated script, visualization spec, trace/state timeline, selected/rejected sources, coverage, extraction plan, limitations, clarification questions, not-found evidence, and feedback/fix requests.
- **D-33:** Streamlit remains a simple fast test surface. It should call the same workflow entrypoint used by tests/evals and render enough of the response contract for manual testing, but it is not the primary polished frontend deliverable.
- **D-34:** UI polish is useful only after product behavior is real. Do not spend Phase 2 effort on decorative design before source selection, coverage, extraction, eval, trace, and frontend response contract are working.
- **D-35:** Qwen via Yandex AI Studio remains the target LLM path for structured intent/planning/critic/narration.
- **D-36:** Preserve the verified Yandex chat endpoint/auth pattern from current code: `https://llm.api.cloud.yandex.net/v1` with `Authorization: Api-Key ...`.
- **D-37:** All LLM calls and embedding calls specified by the architecture stack must be real calls in the target path. "Live" means actual Yandex/Qwen and embedding API calls, not mocked responses, canned outputs, or silent deterministic substitutes.
- **D-38:** Deterministic fallback may be used only for local tests where explicitly marked, but it must not hide missing Qwen/Yandex integration in the jury path and must not be counted as final Phase 2 readiness.
- **D-38A:** Automatic tests and golden-case evals are required but not sufficient.
- **D-38B:** After implementation, run manual testing through the quick UI/workflow surface and incorporate user feedback from that testing before claiming Phase 2 complete.
- **D-38C:** Manual testing should verify not only final text, but the whole product behavior: pipeline traversal, trace readability, source selection/rejection, deterministic numeric provenance, dataset/script artifacts, frontend response format, clarification behavior, not-found honesty, and feedback/fix-request flow.
- **D-39:** Do not merge `origin/workstream-1/core-integration` wholesale.
- **D-40:** Selectively port only useful ideas, such as a single workflow state, LangGraph routing, clarification loops, and contract tests.
- **D-41:** Do not port stub scouts, stub extraction, old planning state, deletion of Phase 1 evidence, or the regressed Yandex endpoint/auth behavior.

### Claude's Discretion

- The planner chooses the implementation wave order and should seek parallel work where file ownership and dependencies allow it. Fast implementation is preferred.
- The planner should run embedding/Qdrant readiness work in parallel with workflow/extraction/eval/frontend-response-contract work where possible. Final readiness still requires real LLM/embedding calls and no unresolved stale/gated critical path.
- The planner may refactor modules and schemas to support the full workflow, provided Phase 1 artifacts, source-bound invariants, and tests are preserved or deliberately migrated with evidence.
- The planner may add focused tests and eval artifacts beyond the existing suite where needed for golden-case acceptance.

### Deferred Ideas (OUT OF SCOPE)

None from this discussion. The user explicitly rejected deferring architecture-stack functionality out of Phase 2; downstream planning may stage work internally, but not move required Phase 2 capabilities into an unapproved later phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| NLU-01..04 | classify Russian natural-language queries, formalize research definitions, clarify ambiguity, honestly report no data | Use Qwen structured output into `IntentFrame` and final terminal mapping; ambiguous/no-data goldens must not enter extraction. |
| SRCH-01..04 | RAG/index search over FedStat and World Bank metadata plus `find_data` with source metadata | Use existing 36,321-card corpus, Qdrant collection, source catalog, and bounded CKAN package search; fix ranking and rejected-source reasons. |
| DATA-01..05 | deterministic Parquet read/filter/aggregate/derived metrics | Implement FedStat, World Bank, and CKAN adapters as structured operations compiled to DuckDB/PyArrow, never free-form LLM table reading. |
| ART-01..06 | research definition, design, dataset schema, script, dataset export, sourced numeric answer | Extend `workflow_artifacts.py` response contract; every `passed` case must emit dataset/script/manifest/provenance and source-bound answer blocks. |
| RBST-01..03 | fuzzy, invalid, and no-data handling | Use LangGraph interrupt/clarification routing and Methodology Critic terminal decisions; `not_found` requires attempted source evidence. |
| RBST-04 | LLM never extracts numbers from tables | Keep deterministic tools as the only numeric authority; test final answers for unsupported numeric claims. |
| UI-01..04 | simple non-programmer UI with trace and downloads | Keep Streamlit as test surface; route `st.chat_input` into the same workflow entrypoint used by evals and render the response contract. |
| ENG-01..04 | reproducibility, separation of LLM/code, extensible sources, architecture docs | Add `langgraph` to requirements, document run/eval commands, preserve source adapter boundaries and update README/architecture docs. |
</phase_requirements>

## Summary

Phase 2 should plan around the fact that Phase 1 infrastructure is now more usable than the stale acceptance notes imply: the embedding cache contains all 36,321 chunks, the Qdrant manifest is `ready`, `python3 -m pytest -q` passes 27/27, Yandex/Qwen and embedding environment configuration is present, and bounded CKAN responds. The remaining MVP gap is product behavior: retrieval ranking quality, source-specific deterministic extraction, strict terminal outcomes, a real workflow runtime, and a frontend-facing response contract consumed by both evals and Streamlit.

The implementation should not start by rebuilding the corpus unless a manifest check fails. Start by freezing the current ready index/readiness evidence, then build a single Phase 2 workflow service entrypoint that takes user text and returns a typed `WorkflowResponse`. Evals, CLI smoke tests, and Streamlit must all call that same entrypoint. The response must make component statuses visible, but final golden-case terminal states must be only `passed`, `needs_clarification`, or `not_found`.

**Primary recommendation:** implement Phase 2 as a LangGraph-backed, Pydantic-state workflow over existing source cards/Qdrant/catalog, with deterministic source adapters promoted ahead of narration and a strict all-20-golden eval gate.

## Project Constraints (from AGENTS.md)

- Use GSD for non-trivial planning/execution and durable `.planning/` memory.
- Treat Phase 1 as accepted infrastructure and Phase 2 as the full jury MVP; do not invent additional numbered follow-up phases.
- Execute single-track through canonical plans; do not recreate owner-specific Core/Data/UI workstreams.
- Phase 2 acceptance is all 20 golden cases with correct `passed` / `needs_clarification` / `not_found` outcomes and no stale/gated/skipped final states.
- Numbers must come from deterministic code or trusted source adapters, never LLM memory.
- CKAN is trusted NSED catalog API access, not general web search.
- Keep secrets in `.env`; never commit API keys or secret values.
- Prefer traceable artifacts: notes, source candidates, rejection reasons, generated SQL/code, extraction logs, verification results.
- Streamlit is the first demo UI target and must expose state machine, trace, artifacts, feedback, and fix requests.
- No `CLAUDE.md` or project-local skill directories were found.

## Current State Findings

| Area | Finding | Confidence |
|------|---------|------------|
| Tests | `python3 -m pytest -q` now passes `27 passed in 7.52s`. Earlier 26/27 reports are stale. | HIGH |
| Qdrant | Full cache/corpus line counts are 36,321 / 36,321; demo readiness reports `qdrant_status=ready`, `qdrant_vector_count=36321`, `dense_retrieval_ready=true`. | HIGH |
| Demo readiness | Overall status remains `gated` because retrieval eval, extraction eval, and data relevance eval artifacts are still not Phase 2-ready. | HIGH |
| Fresh retrieval smoke | A fresh 20-case retrieval run over the ready index records `dense_status=ready`; only GC-008 remains `no_candidate`, but several top candidates are still semantically weak. | HIGH |
| Extraction | Existing extraction probes remain `skipped_with_reason`; no answer-grade FedStat/WB/CKAN extraction path exists. | HIGH |
| UI | `app/ui/streamlit_app.py` accepts chat input but does not execute a user-query workflow; it renders readiness artifacts. | HIGH |
| Workflow | `Phase1Graph` has an `invoke()` compatibility shape but only appends a checkpoint trace. It must be replaced/extended. | HIGH |
| External access | Yandex/Qwen config resolves using fallback env vars; CKAN package search for `57319` returned HTTP 200 and success. | HIGH |

## Standard Stack

### Core

| Library | Verified Installed | Latest Verified | Purpose | Why Standard |
|---------|--------------------|-----------------|---------|--------------|
| Python | 3.11.9 | local runtime | application/runtime | Existing repo and Yandex docs support Python 3.10+; keep current runtime. |
| LangGraph | 1.1.10 | 1.1.10, uploaded 2026-04-27 | workflow graph, state, routing, clarification/repair loops | Official docs position it for long-running stateful agents, durable execution, streaming, and human-in-the-loop. It is installed but missing from `requirements.txt`; add it. |
| Pydantic | 2.12.5 | 2.13.4, uploaded 2026-05-06 | typed artifacts and response contracts | Existing code already uses `BaseModel`, `ConfigDict(extra="forbid")`, and model dumps everywhere. |
| Yandex AI Studio/Qwen client | local `requests` client | current official AI Studio docs checked | live structured LLM calls | Locked decision requires verified `https://llm.api.cloud.yandex.net/v1` and `Api-Key` auth; do not port remote branch auth changes. |
| Yandex text embeddings | local `requests` client | official `textEmbedding` endpoint checked | document/query embeddings | Current code correctly separates `text-search-doc` and `text-search-query` model URIs. |
| Qdrant client | 1.17.1 | 1.17.1, uploaded 2026-03-13 | vector store abstraction | Existing manifest/collection are ready; preserve Qdrant instead of introducing a local vector path. |
| DuckDB | 1.5.2 | 1.5.2, uploaded 2026-04-13 | deterministic SQL extraction | Official Python docs support direct Parquet query; repo already restricts SQL to read-only `SELECT`/`WITH`. |
| PyArrow | 23.0.1 | 24.0.0, uploaded 2026-04-21 | Parquet schema/exports | Required for FedStat/WB Parquet and dataset exports. |
| Streamlit | 1.55.0 | 1.57.0, uploaded 2026-04-28 | quick jury/test UI | Existing UI target; official chat input/session APIs fit the needed chat-like surface. |

### Supporting

| Library | Verified Installed | Latest Verified | Purpose | When to Use |
|---------|--------------------|-----------------|---------|-------------|
| Altair | 6.0.0 | 6.1.0, uploaded 2026-04-21 | deterministic chart specs | Use from `DatasetArtifact` only. |
| Plotly | 6.6.0 | local installed | fallback table/chart renderer | Use only as fallback when Altair rendering fails. |
| PyYAML | 6.0.3 | 6.0.3, uploaded 2025-09-25 | golden cases | Keep for `golden-cases.yaml`. |
| requests | 2.32.5 | 2.33.1, uploaded 2026-03-30 | Yandex/CKAN HTTP | Keep current simple clients; mock in unit tests. |
| python-dotenv | 1.2.2 | 1.2.2, uploaded 2026-03-01 | local `.env` loading | Use for secret presence only; never print values. |
| pytest | 9.0.3 | local installed | test runner | Existing suite convention. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| LangGraph | hand-written graph runner | Current `Phase1Graph` shows the risk: easy to emit trace without real routing, interrupts, or durable state. Use LangGraph for Phase 2 routing. |
| raw `requests` Yandex client | OpenAI Python SDK | Yandex quickstart supports OpenAI SDK, but current verified tests and locked decision use raw requests with `llm.api.cloud.yandex.net` and `Api-Key`. Do not migrate during Phase 2 unless needed. |
| Qdrant embedded local mode | Qdrant Docker/server | Local mode works and is ready, but the Python client warns above 20,000 points. For jury performance, prefer Docker/server if daemon can be started; otherwise keep local with explicit warning. |
| DuckDB + PyArrow | Polars | `polars` is listed in `requirements.txt` but not installed and not used. Do not plan Phase 2 around Polars. |
| Full custom frontend | Streamlit now, chat contract for future | User explicitly rejected polished frontend now. Build the response contract and simple Streamlit test surface. |

**Installation:**

```bash
python3 -m pip install -r requirements.txt
python3 -m pip install "langgraph>=1.1.10"
```

Recommended requirements fix:

```text
langgraph>=1.1.10
```

Do not rely on `openai` or `polars` until `python3 -m pip install -r requirements.txt` has been rerun and imports are verified; both were absent in the current environment despite being listed or architecturally optional.

## Architecture Patterns

### Recommended Project Structure

```text
app/
  workflow/
    service.py          # one user-query entrypoint used by evals, CLI, and Streamlit
    state.py            # Phase 2 typed workflow state, evolved from GraphState
    graph.py            # LangGraph StateGraph construction and conditional routing
    nodes/
      supervisor.py
      intent.py
      research_design.py
      scouts.py
      coverage.py
      extraction_planner.py
      deterministic_tools.py
      critic.py
      visualization.py
      narrator.py
  data/
    fedstat_adapter.py
    world_bank_adapter.py
    ckan_adapter.py
  evals/
    run_eval.py         # extend to execute workflow outputs, not probe artifacts only
  ui/
    streamlit_app.py    # render WorkflowResponse from service.py
```

### Pattern 1: Single Typed State Through LangGraph

**What:** Replace the checkpoint-only `Phase1Graph` with a compiled LangGraph `StateGraph` using one shared Phase 2 state object. Nodes should return partial state updates and append canonical `TraceEvent` records.

**When to use:** Every product execution path, including direct lookups and clarification/no-data routes.

**Example:**

```python
# Source: LangGraph Graph API docs and local GraphState pattern.
from typing import TypedDict, NotRequired
from langgraph.graph import StateGraph, START, END

class AgentState(TypedDict):
    run_id: str
    query: str
    intent: NotRequired[dict]
    evidence: NotRequired[dict]
    coverage_reports: NotRequired[list[dict]]
    dataset_artifacts: NotRequired[list[dict]]
    final_outcome: NotRequired[str]
    trace_events: list[dict]

builder = StateGraph(AgentState)
builder.add_node("intent", intent_node)
builder.add_node("scouts", source_scouts_node)
builder.add_node("coverage", coverage_node)
builder.add_node("extract", extraction_node)
builder.add_node("critic", critic_node)
builder.add_node("narrator", narrator_node)
builder.add_edge(START, "intent")
builder.add_conditional_edges("intent", route_after_intent)
builder.add_edge("scouts", "coverage")
builder.add_edge("coverage", "extract")
builder.add_edge("extract", "critic")
builder.add_conditional_edges("critic", route_after_critic)
builder.add_edge("narrator", END)
graph = builder.compile(checkpointer=checkpointer)
```

### Pattern 2: One Service Entrypoint for UI and Evals

**What:** Create a workflow service function such as `run_user_query(query: str, *, run_config: WorkflowRunConfig) -> WorkflowResponse`.

**When to use:** Streamlit, CLI smoke tests, all-20 golden evals, and manual jury testing.

**Example:**

```python
response = run_user_query(
    query="Сравни население России и Казахстана по данным World Bank.",
    run_config=WorkflowRunConfig(index_manifest=PHASE1_INDEX, artifact_dir=PHASE2_ARTIFACTS),
)
assert response.final_outcome in {"passed", "needs_clarification", "not_found"}
```

### Pattern 3: Component Statuses Are Internal, Terminal Outcomes Are Product-Level

**What:** Keep `coverage.status`, `extraction.status`, and `retrieval.status` for trace/debugging, but map final outcomes separately.

**When to use:** Every final answer and eval row.

**Required mapping:**

| Internal Evidence | Final Outcome |
|-------------------|---------------|
| valid source + coverage + dataset + critic pass | `passed` |
| missing critical user choice | `needs_clarification` |
| bounded trusted search found no usable source/coverage | `not_found` |
| stale/gated/skipped/no_candidate | implementation failure, not final outcome |

### Pattern 4: Source-Specific Deterministic Adapters

**What:** Implement adapters behind a common operation interface, then compile safe operations to DuckDB/PyArrow.

**When to use:** FedStat wide Parquet, World Bank long Parquet, and promoted CKAN resources.

**Example operation contract:**

```python
class ExtractionOperation(BaseModel):
    source_family: Literal["fedstat", "world_bank", "ckan"]
    operation: Literal["coverage_preview", "filter_rows", "join_indicators", "normalize_index"]
    source_id: str
    filters: dict[str, str | int | list[str]]
    output_columns: list[str]
    model_config = ConfigDict(extra="forbid")
```

### Pattern 5: Chat-Like Response Contract, Not Polished Frontend

**What:** Return message-style output plus structured blocks for artifacts, not-found evidence, trace, sources, and feedback actions.

**When to use:** Both Streamlit now and future Claude-like frontend.

```python
class WorkflowResponse(BaseModel):
    run_id: str
    final_outcome: Literal["passed", "needs_clarification", "not_found"]
    message: str
    answer_blocks: list[dict]
    citations: list[dict]
    selected_sources: list[dict]
    rejected_sources: list[dict]
    coverage: list[dict]
    extraction_plan: dict | None
    dataset_artifacts: list[dict]
    script_artifacts: list[dict]
    visualization: dict | None
    trace_events: list[TraceEvent]
    limitations: list[str]
    feedback_actions: list[dict]
    model_config = ConfigDict(extra="forbid")
```

### Anti-Patterns to Avoid

- **UI-only workflow path:** Streamlit must not contain product logic or bypass evals.
- **Final `ok` with gated internals:** This is already a known bug; make it impossible.
- **Free-form SQL from LLM:** LLM chooses safe operations; adapters compile SQL/scripts.
- **Raw CKAN payloads in context:** compress into source cards; call `package_show` only for promoted top candidates.
- **Partial index as readiness:** partial manifests are debugging-only.
- **Remote branch wholesale merge:** it deletes Phase 1 evidence and regresses Yandex auth.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Graph routing, loops, clarification pauses | custom if/else graph runner | LangGraph `StateGraph`, checkpointer, interrupts | Needed for stateful repair/clarification; current smoke runner is too easy to fake. |
| Artifact validation | ad hoc dict validation | Pydantic v2 models with `extra="forbid"` | Stable response/eval/UI contracts and schema errors. |
| Vector search | local cosine JSONL search | Qdrant through existing manifest | Locked decision and ready collection exist. |
| SQL/data extraction | LLM-written arbitrary SQL | typed safe operations compiled by adapters to DuckDB/PyArrow | Prevents unsafe local file reads and unsupported numeric claims. |
| CKAN discovery | general web search | bounded CKAN Action API `package_search` / `package_show` | CKAN is trusted NSED catalog, not open web search. |
| Chat UI framework | custom frontend | Streamlit plus `WorkflowResponse` | User asked not to polish frontend; Streamlit already exists. |
| Eval format | manual spreadsheet checking | pytest + machine-readable all-20 golden eval JSON | Acceptance is strict and must be reproducible. |

**Key insight:** Phase 2 is not blocked by lack of libraries; it is blocked by letting diagnostic gates masquerade as product behavior. Plan tasks that make evidence hard to bypass.

## Common Pitfalls

### Pitfall 1: Treating Ready Qdrant As Ready MVP

**What goes wrong:** Dense retrieval is ready, but extraction/eval/answer remain gated.  
**Why it happens:** The Phase 1 artifacts have separate readiness dimensions.  
**How to avoid:** Make demo readiness require workflow eval and extraction artifacts, not just vector count.  
**Warning signs:** `overall_status=gated` with `qdrant_status=ready`.

### Pitfall 2: Direct Indicator Requests Still Rank Weak Contextual Sources

**What goes wrong:** GC-001 still ranks `fedstat:62470` above direct GDP indicators even with dense ready.  
**Why it happens:** fallback reranker rewards keyword overlap and source family, not exact indicator intent.  
**How to avoid:** Add domain-aware ranking: exact code/title/indicator-class bonuses, direct-vs-context penalty, source preference enforcement, and coverage preview vetoes.  
**Warning signs:** "ВВП" returns GDP-share/funding indicators rather than direct GDP.

### Pitfall 3: LangGraph Interrupts Re-run Node Prefix Code

**What goes wrong:** clarification/repair nodes duplicate side effects after resume.  
**Why it happens:** Official docs say resumed interrupted nodes restart from the beginning; code before `interrupt()` runs again.  
**How to avoid:** Keep interrupt nodes side-effect-free before the interrupt; persist artifacts before/after with idempotent IDs.

### Pitfall 4: Streamlit Reruns Break Chat State

**What goes wrong:** chat history, selected run, or artifacts disappear or rerun expensive workflow calls.  
**Why it happens:** Streamlit reruns top-to-bottom on interactions; widget keys/session state matter.  
**How to avoid:** Store `run_id`, messages, latest `WorkflowResponse`, and feedback in `st.session_state`; cache only read-only manifests, not mutable workflow outputs.

### Pitfall 5: Local Qdrant Performance/Locking

**What goes wrong:** embedded Qdrant warns at 36,321 vectors and can conflict with concurrent local clients.  
**Why it happens:** Qdrant Python local mode warns above 20,000 points and Docker daemon is currently not running.  
**How to avoid:** Prefer one promoted local/server mode for jury; if using Docker, plan a daemon-start prerequisite. Keep local mode acceptable for tests if performance is sufficient.

### Pitfall 6: LLM Numeric Leakage

**What goes wrong:** Narrator includes plausible numbers not present in `DatasetArtifact`.  
**Why it happens:** free-form narration prompt has access to user query and source titles but no enforced numeric ledger.  
**How to avoid:** Narrator may only cite values from dataset rows/provenance; add regex/source cross-check tests for final answer numbers.

### Pitfall 7: CKAN Context Explosion

**What goes wrong:** raw API response floods Qwen context and causes wrong source selection.  
**Why it happens:** CKAN packages/resources are heterogeneous and verbose.  
**How to avoid:** `package_search(rows<=5)` -> compressed cards -> local rerank -> `package_show(top<=3)` -> promoted metadata only.

### Pitfall 8: Requirements Drift

**What goes wrong:** a planner assumes `requirements.txt` matches the active environment.  
**Why it happens:** `openai` and `polars` are absent now despite requirement/architecture mentions; `langgraph` is installed but not declared.  
**How to avoid:** Wave 0 should run import/version checks and update `requirements.txt` before implementation tasks depend on packages.

## Code Examples

### Strict Final Status Guard

```python
def derive_final_outcome(state: AgentState) -> str:
    if state["intent"].get("needs_clarification"):
        return "needs_clarification"
    if state.get("not_found_evidence"):
        return "not_found"
    if not state.get("dataset_artifacts"):
        raise RuntimeError("passed outcome requires deterministic dataset artifacts")
    if any(report["status"] != "ok" for report in state.get("coverage_reports", [])):
        raise RuntimeError("passed outcome requires ok coverage")
    if state["critique"]["verdict"] not in {"pass", "pass_with_warnings"}:
        raise RuntimeError("passed outcome requires critic approval")
    return "passed"
```

### Streamlit Uses Workflow Service

```python
if prompt := st.chat_input("Введите экономический запрос", key="phase2_query"):
    with st.status("DataAgent runs source-bound workflow", expanded=True):
        response = run_user_query(prompt, run_config=ui_run_config())
        st.session_state["latest_response"] = response

response = st.session_state.get("latest_response")
if response:
    st.chat_message("assistant").markdown(response.message)
    st.download_button("Dataset CSV", data=read_artifact(response.dataset_artifacts[0]))
    render_trace(response.trace_events)
```

### Adapter-Compiled SQL Only

```python
def execute_plan(plan: ExtractionPlan) -> DatasetArtifact:
    operations = [ExtractionOperation.model_validate(item) for item in plan.operations]
    sql, params, provenance = compile_operations_to_duckdb(operations)
    rows = run_duckdb_query(sql, parameters=params)
    return build_dataset_artifact(
        rows=rows,
        artifact_id=plan.artifact_id.replace("plan", "dataset"),
        source_id=plan.source_id,
        provenance=provenance,
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed/Verified | Impact |
|--------------|------------------|------------------------|--------|
| checkpoint-compatible custom graph | LangGraph `StateGraph` with shared state, conditional routing, interrupts, checkpointer | LangGraph 1.1.10 current on PyPI, docs checked 2026-05-10 | Use real graph runtime instead of expanding `Phase1Graph`. |
| generic one-mode embeddings | Yandex doc/query split: `text-search-doc` for source chunks, `text-search-query` for natural-language query | Existing tests/env and Yandex docs checked 2026-05-10 | Preserve split and test it in GC-019/GC-020. |
| stale/gated dense evidence | ready 36,321-vector Qdrant collection | local verification 2026-05-10 | Planner should refresh eval artifacts, not default to rebuilding index. |
| diagnostic Streamlit shell | chat UI calls workflow service and renders typed response | Phase 2 target | No UI-only path. |
| probe-level extraction | source-specific deterministic adapters with dataset/script/manifest | Phase 2 required | DATA/ART acceptance depends on this. |

**Deprecated/outdated:**

- Earlier Phase 1 notes saying full embedding build is still running are now stale; cache/corpus are complete.
- Earlier 26/27 pytest result is stale; current suite is 27/27.
- Remote branch Yandex `Bearer` / `ai.api.cloud.yandex.net` client is rejected for this repo. Keep current verified `llm.api.cloud.yandex.net` with `Api-Key`.

## Open Questions

1. **Should Qdrant local mode be promoted to Docker/server before jury?**
   - What we know: local mode is ready but warns at 36,321 points; Docker CLI exists but daemon is not running.
   - What's unclear: whether local UI/eval latency is acceptable during manual jury testing.
   - Recommendation: keep local mode for implementation; add a late readiness task to benchmark and optionally promote to Docker/server.

2. **Which CKAN packages/resources must be promoted for passed outcomes?**
   - What we know: CKAN API responds and GC-013 can discover by code; current full corpus includes at least a promoted CKAN card in retrieval output.
   - What's unclear: which CKAN resources are extractable enough for GC-006/007/012/014/018.
   - Recommendation: plan a CKAN promotion matrix per golden case with explicit `passed` vs `not_found` evidence.

3. **How strict should all-20 acceptance be for ambiguous cases?**
   - What we know: GC-001, GC-006, GC-009, and GC-010 expect clarification before extraction.
   - What's unclear: whether a candidate preview is required for every clarification.
   - Recommendation: treat clarification as valid only when the question is specific and trace shows why extraction was blocked.

## Environment Availability

| Dependency | Required By | Available | Version/State | Fallback |
|------------|-------------|-----------|---------------|----------|
| Python | all code | yes | 3.11.9 | none needed |
| pip | dependency install | yes | 24.0 | upgrade optional |
| pytest | automated verification | yes | 9.0.3 | none |
| Streamlit | test UI | yes | 1.55.0 installed | CLI/workflow eval if UI unavailable |
| LangGraph | Phase 2 graph | yes installed | 1.1.10; not in `requirements.txt` | add to requirements |
| Pydantic | artifacts | yes | 2.12.5 installed | none |
| Qdrant local collection | dense retrieval | yes | 36,321 vectors, `ready` | Docker/server if local mode too slow |
| Qdrant CLI | direct CLI admin | no | command missing | use Python client |
| Docker daemon | optional Qdrant server/sandbox | no | CLI 29.1.3 present; daemon not running | embedded local Qdrant |
| Yandex/Qwen config | live LLM calls | yes | config resolves; model set; no secret values printed | tests may mock only |
| Yandex embeddings config | dense index/query | yes | no missing embedding env vars | none for target path |
| CKAN/NSED API | trusted catalog | yes | HTTP 200, success for `57319` probe | cached promoted metadata |
| bge reranker endpoint | optional rerank | no | `BGE_RERANKER_URL` unset | deterministic fallback, but ranking must improve |
| OpenAI package | optional SDK | no | not installed | keep raw requests client |
| Polars package | optional data engine | no | not installed | DuckDB/PyArrow |

**Missing dependencies with no fallback:**

- None for the current target path, assuming Yandex credentials remain available in local `.env`.

**Missing dependencies with fallback:**

- Docker daemon: fallback is embedded Qdrant, but performance warning must be tracked.
- Qdrant CLI: fallback is Python client.
- bge reranker endpoint: fallback is deterministic rerank, but direct-indicator ranking must be fixed.
- `openai` and `polars`: not required for the chosen Phase 2 path.

## Practical Verification Gates

Nyquist validation is disabled in `.planning/config.json`, so this is not a formal `## Validation Architecture` section. The planner should still use these gates:

| Gate | Command / Evidence | Required Result |
|------|--------------------|-----------------|
| Unit/contract suite | `python3 -m pytest -q` | all tests pass |
| Requirements/import sanity | `python3 -c "import langgraph, streamlit, qdrant_client, duckdb, pyarrow, pydantic"` | imports succeed |
| Ready index | `python3 -m app.demo.run_demo ... --json-output <tmp>` | `qdrant_status=ready`, vector count equals corpus count |
| Fresh retrieval eval | `python3 scripts/run_retrieval_spike.py ... --limit 20` | dense status ready; no unacceptable no-candidate except cases deliberately terminal `not_found` |
| Workflow all-20 eval | Phase 2 extended `python3 -m app.evals.run_eval ...` | every case is `passed`, `needs_clarification`, or `not_found` |
| UI manual smoke | `PYTHONPATH=. python3 -m streamlit run app/ui/streamlit_app.py --server.port 8501` | user query executes workflow service and renders response blocks |
| Manual UAT | user runs representative prompts and feedback/fix request | feedback incorporated or documented before readiness |

## Planning Recommendations

1. **Wave 0: freeze readiness and dependency baseline.** Add `langgraph` to `requirements.txt`, verify imports, record current ready Qdrant/index evidence, and refresh retrieval/data-relevance artifacts so planners do not chase stale Phase 1 states.
2. **Wave 1: define Phase 2 contracts.** Extend `workflow_artifacts.py` with final outcome, response contract, attempted-source/no-data artifacts, script artifact, and stricter dataset provenance.
3. **Wave 2: build workflow service + LangGraph routing.** Replace/extend `run_graph.py` with product execution that supports direct, comparative, research, derived, ambiguous, and no-data routes.
4. **Wave 3: extraction adapters.** Implement FedStat wide, World Bank long, and promoted CKAN deterministic adapters; start with goldens most likely to pass and expand to all required `passed` cases.
5. **Wave 4: retrieval ranking and scout quality.** Use ready dense index, but add direct-indicator ranking, source preference, rejection logs, and coverage-veto logic.
6. **Wave 5: critic/narrator/visualization.** Critic owns final blocking/repair; narrator can only reference dataset values; visualization comes from dataset artifact.
7. **Wave 6: Streamlit response renderer + manual UAT.** Wire `st.chat_input` to the same service and expose trace/artifacts/feedback.
8. **Wave 7: docs and final gates.** README, architecture docs, all-20 eval, demo readiness, manual feedback summary.

## Sources

### Primary (HIGH confidence)

- Local repo files: `.planning/phases/02-jury-mvp/02-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `.planning/ROADMAP.md`, `.planning/ARCHITECTURE_STACK.md`, Phase 1 acceptance/current-state reports, and codebase maps.
- Local code: `app/artifacts/workflow_artifacts.py`, `app/workflow/graph_contract.py`, `app/workflow/run_graph.py`, `app/data/deterministic_tools.py`, `app/retrieval/*`, `app/evals/run_eval.py`, `app/ui/streamlit_app.py`.
- LangGraph docs: https://docs.langchain.com/oss/python/langgraph/overview and https://docs.langchain.com/oss/python/langgraph/graph-api
- LangGraph interrupts docs: https://docs.langchain.com/oss/python/langgraph/interrupts
- Yandex AI Studio quickstart: https://aistudio.yandex.ru/docs/en/ai-studio/quickstart/
- Yandex text embedding API: https://aistudio.yandex.ru/docs/en/ai-studio/embeddings/api-ref/Embeddings/textEmbedding.html
- Streamlit `st.chat_input`: https://docs.streamlit.io/develop/api-reference/chat/st.chat_input
- CKAN Action API: https://docs.ckan.org/en/latest/api/
- Qdrant Python client docs: https://python-client.qdrant.tech/
- Pydantic v2 models docs: https://pydantic.dev/docs/validation/2.0/usage/models/

### Secondary (MEDIUM confidence)

- PyPI JSON API version/publish checks for `langgraph`, `pydantic`, `streamlit`, `qdrant-client`, `duckdb`, `pyarrow`, `altair`, `polars`, `requests`, `python-dotenv`, `PyYAML`, `openai`.
- DuckDB Python docs/search result for direct Parquet querying: https://duckdb.org/docs/stable/clients/python/overview
- Qdrant local mode source docs indicating the 20,000-point local warning threshold: https://python-client.qdrant.tech/_modules/qdrant_client/local/qdrant_local

### Tertiary (LOW confidence)

- None used for authoritative recommendations.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH - verified against local imports, PyPI current versions, and official docs.
- Architecture: HIGH - constrained by repo code and locked `.planning/ARCHITECTURE_STACK.md`.
- Pitfalls: HIGH for repo-specific pitfalls; MEDIUM for Qdrant local performance because benchmark not measured.
- Environment availability: HIGH - probed local commands/env presence without printing secrets.

**Research date:** 2026-05-10  
**Valid until:** 2026-05-17 for fast-moving API/package details; 2026-06-09 for repo-specific architectural findings unless Phase 2 implementation changes the codebase.
