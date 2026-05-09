# Phase 01: Data Architecture Research - Research

**Researched:** 2026-05-09
**Domain:** source-bound economic data assistant architecture research
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
### Architecture Stack Status
- **D-01:** Treat `.planning/ARCHITECTURE_STACK.md` as the target architecture for Phase 1 research and planning.
- **D-02:** Phase 1 should validate risks and implementation details inside that stack, not compare against a radically simpler architecture unless a blocker is discovered.

### Source Scope
- **D-03:** FedStat, World Bank, and CKAN are all in scope from the start.
- **D-04:** CKAN is a first-class source path for discovery and data access, not just a bonus freshness check.
- **D-05:** Local dumps remain important for speed and reproducibility, but Phase 1 must research how live CKAN package/resource discovery integrates into the same source-bound workflow.

### Retrieval and Catalog
- **D-06:** Implement/research retrieval fully according to `.planning/ARCHITECTURE_STACK.md`: lexical BM25/FTS plus dense embeddings and reranking where feasible.
- **D-07:** Metadata indexing should use compact source cards and evidence bundles rather than loading raw CKAN/API/table responses into LLM context.
- **D-08:** Retrieval must support exact code/title matches, Russian and English lexical search, semantic matches, proxy candidates, methodology matches, and rejection reasons.

### Deterministic Extraction
- **D-09:** Implement/research data extraction fully according to `.planning/ARCHITECTURE_STACK.md`: DuckDB SQL-first with PyArrow/source adapters for normalization and Polars where useful.
- **D-10:** FedStat requires a real normalizer strategy for wide Parquet tables, including first-row headers, dimensions, period columns, units, source URLs, and coverage preview.
- **D-11:** World Bank requires a real adapter strategy for indicator cards, countries/aggregates, coverage by country/period, and canonical long-format output.
- **D-12:** LLMs may choose plans and explain results, but numbers must come only from deterministic tools.

### Orchestration and Agents
- **D-13:** Implement/research the orchestration fully according to `.planning/ARCHITECTURE_STACK.md`: LangGraph hierarchical supervisor with typed artifacts.
- **D-14:** The minimum target graph for research/planning is Lead DataAgent/Supervisor, Intent/Triage, Research Designer, FedStat Scout, World Bank Scout, CKAN Scout, Coverage & Schema, Extraction Planner, deterministic tools, Methodology Critic, Narrator, and Visualization where relevant.
- **D-15:** Simple direct lookups should be able to skip unnecessary agents, but complex research queries should use parallel source scouts and critic loops.

### LLM Choice
- **D-16:** Use Qwen 3.6 via Yandex AI Studio as the target model per architecture stack.
- **D-17:** Do not spend Phase 1 primarily on broad model benchmarking. DeepSeek/YandexGPT comparisons can be tested later if needed.
- **D-18:** Yandex AI Studio integration should remain part of the target: OpenAI-compatible API, structured outputs/tool calling, and optional native File Search / Vector Store / MCP Hub where they accelerate the architecture.

### Test Cases and Evaluation
- **D-19:** Phase 1 should prepare the broader 15-20 test-case set from the task, not only a small 5-8 smoke set.
- **D-20:** Test coverage should include simple lookup, comparative query, research query, derived metric, ambiguous query, and no-data query.
- **D-21:** Evaluation must measure not just final answer text, but retrieval quality, coverage preview, source rejection, deterministic extraction, and trace completeness.

### Phase 1 Output Shape
- **D-22:** Phase 1 output should include research report(s), executable spikes, and trade-off tables.
- **D-23:** Spikes are evidence for planning and MVP selection; they are not automatically accepted as production implementation without explicit Phase 2 planning.

### Success Criterion Priority
- **D-24:** The main recommendation criterion for Phase 2 is maximum demonstration value from multi-agent trace and UI transparency.
- **D-25:** Reliability remains non-negotiable: every numeric value must be source-bound and reproducible, but among reliable options the preferred path is the one with the strongest visible agent workflow and trace.

### Claude's Discretion
- The planner may choose exact spike ordering, file/module boundaries, schemas, and test harness structure.
- The planner may decide whether to implement dense embeddings locally or through Yandex AI Studio first, as long as the full architecture target is respected.
- The planner may choose specific charting/eval libraries within the stack constraints.

### Deferred Ideas (OUT OF SCOPE)
- Broad DeepSeek/YandexGPT/Qwen benchmarking is deferred; Phase 1 targets Qwen 3.6 per architecture stack and can test alternatives later if needed.
- Final production MVP implementation remains Phase 2, after Phase 1 research/spikes and explicit planning.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| NLU-01 | Система принимает запрос на естественном языке (русский) и классифицирует его тип | Typed `IntentFrame`, Qwen structured output, LangGraph triage node, 15-20 eval cases |
| NLU-02 | Система формализует запрос в определение исследования | Research Designer artifact, evidence bundle contract, clarification/no-data routing |
| NLU-03 | Для неоднозначных запросов система задаёт уточняющие вопросы | Clarification branch, checkpointer-backed thread state, UI artifact/feedback handling |
| NLU-04 | Система корректно определяет, когда запрашиваемых данных нет | Coverage preview, rejection reasons, critic policy, no-data test cases |
| SRCH-01 | RAG-индекс по метаданным Росстата | Source-card catalog, lexical + dense + rerank research, FedStat normalizer requirements |
| SRCH-02 | RAG-индекс по метаданным World Bank | Indicator-card catalog, country/period coverage fields, World Bank adapter design |
| SRCH-03 | Инструмент `find_data` | Scout-agent + retrieval interface + bounded CKAN/package/resource discovery |
| SRCH-04 | Результаты поиска включают метаданные | SourceCandidateCard/EvidenceBundle fields for source, period, geography, units, provenance |
</phase_requirements>

## Summary

Phase 1 should be planned as an evidence-building phase for a stack that is already chosen, not as architecture shopping. The main job is to de-risk and operationalize the locked design: LangGraph hierarchical orchestration, DuckDB SQL-first deterministic extraction, FedStat + World Bank + CKAN from day one, and a Streamlit trace-first demo surface. The planning target is not "build the MVP now", but "produce enough validated artifacts and executable spikes that Phase 2 can implement without reopening core stack choices."

The highest-risk planning areas are not generic LLM concerns. They are: FedStat normalization into a canonical long format, bounded CKAN discovery without dumping raw API payloads into model context, hybrid retrieval quality for Russian/English/statistical-code search, and a trace model that visibly exposes agent decisions while preserving source-bound determinism. Current official docs support the chosen stack: LangGraph v1.x is purpose-built for persistence and subgraphs, DuckDB directly queries Parquet with pushdown, Streamlit supports chat/status primitives, and Yandex AI Studio supports structured outputs, OpenAI-compatible APIs, tools, and MCP. The main local blocker is not docs maturity but environment readiness: Yandex env vars are currently unset, the repo has only a thin client wrapper, and the existing wrapper disagrees with the verified Yandex usage pattern.

**Primary recommendation:** Plan Phase 1 as four bounded research streams: catalog/retrieval, deterministic adapters, orchestration/trace contracts, and eval/test-case pack, with small executable spikes in each stream and one final recommendation brief that ranks Phase 2 options by visible trace quality under deterministic reliability constraints.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `langgraph` | `1.1.10` (PyPI, 2026-04-27) | Hierarchical supervisor, subgraphs, checkpoints | Official docs position it as low-level orchestration with durable execution, HITL, and stateful workflows |
| `duckdb` | `1.5.2` (PyPI, 2026-04-13) | SQL-first query engine over Parquet | Official docs confirm direct Parquet scans, metadata/schema inspection, filter/projection pushdown |
| `pyarrow` | `24.0.0` (PyPI, 2026-04-21) | File/schema access, source-specific normalization | Best fit for low-level parquet/schema handling before canonicalization |
| `pydantic` | `2.13.4` (PyPI, 2026-05-06) | Typed artifacts and validation | Strong schema contracts for agent outputs, source cards, coverage reports, extraction plans |
| `openai` | `2.36.0` (PyPI, 2026-05-07) | OpenAI-compatible client against Yandex AI Studio | Yandex docs explicitly support OpenAI-compatible APIs and model URIs for common-instance models |
| `streamlit` | `1.57.0` (PyPI, 2026-04-28) | Demo UI with chat + trace/status | Official docs expose `st.chat_input`, chat containers, and `st.status` for long-running steps |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `polars` | `1.40.1` (PyPI, 2026-04-22) | Supplemental lazy transforms | Use for awkward reshapes where DuckDB SQL is clumsy, but keep SQL-first contracts |
| `rapidfuzz` | `3.14.5` (PyPI, 2026-04-07) | Fuzzy title/code matching | Use in lexical candidate generation and code/title rescue paths |
| `rank-bm25` | `0.2.2` (PyPI, 2022-02-16) | Cheap lexical baseline | Use only as a spike/baseline if DuckDB FTS or SQLite FTS coverage is incomplete |
| `sentence-transformers` | `5.4.1` (PyPI, 2026-04-14) | Local dense embeddings/rerank fallback | Use when Yandex embedding credentials are unavailable or for offline/local bakeoffs |
| `langgraph-checkpoint-sqlite` | `3.0.3` (PyPI, 2026-01-19) | Local durable checkpoints | Use for local Phase 1/2 experiments before any Postgres move |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `DuckDB` | `pandas`-first pipelines | Simpler for ad hoc notebooks, weaker fit for deterministic SQL generation and big-file scans |
| `LangGraph` | custom loop | Lower upfront complexity, but you lose built-in checkpointing/HITL/subgraph structure the phase explicitly wants |
| `Streamlit` | Gradio/CLI | Faster for some demos, but Streamlit best matches the trace/workbench requirement already locked in project memory |
| `Yandex embeddings first` | local `sentence-transformers` first | Local path avoids cloud credentials; Yandex path better matches target stack and hackathon narrative |

**Installation:**
```bash
pip install -U langgraph langgraph-checkpoint-sqlite duckdb pyarrow polars pydantic openai streamlit rapidfuzz rank-bm25 sentence-transformers
```

**Version verification:** Verified on 2026-05-09 via `pip index versions` and PyPI JSON API for `langgraph`, `duckdb`, `pyarrow`, `polars`, `streamlit`, `pydantic`, `sentence-transformers`, `rapidfuzz`, `rank-bm25`, `openai`, and `langgraph-checkpoint-sqlite`.

## Architecture Patterns

### Recommended Project Structure

```text
app/
├── artifacts/      # Pydantic schemas: intent, source cards, coverage, plans, trace events
├── data/           # FedStat/WorldBank/CKAN adapters, catalog builders, normalizers
├── retrieval/      # lexical search, dense search, rerank, evidence bundling
├── workflow/       # LangGraph nodes, subgraphs, routing, checkpoint config
├── ui/             # Streamlit app, state machine panels, artifact viewers, feedback
└── llm/            # hardened Yandex AI Studio client and model configuration
```

### Pattern 1: Typed Artifact Pipeline
**What:** Every agent/tool boundary exchanges typed Pydantic artifacts, not raw prose.
**When to use:** Always; especially between intent, scout, coverage, extraction, critic, narrator.
**Example:**
```python
# Source: https://docs.langchain.com/oss/python/langgraph/graph-api
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

class GraphState(TypedDict):
    intent: dict
    candidates: list[dict]
    coverage: dict

def triage(state: GraphState):
    return {"intent": {"kind": "simple_lookup"}}

builder = StateGraph(GraphState)
builder.add_node("triage", triage)
builder.add_edge(START, "triage")
builder.add_edge("triage", END)
graph = builder.compile()
```

### Pattern 2: Per-Invocation Subgraphs Under a Checkpointed Parent
**What:** Parent supervisor has a checkpointer; worker subgraphs stay per-invocation unless they truly need multi-turn memory.
**When to use:** Default for FedStat/World Bank/CKAN scouts.
**Why:** LangGraph docs explicitly recommend per-invocation subgraphs for most multi-agent tool-like calls and warn that per-thread subgraphs conflict with parallel calls.

### Pattern 3: Metadata-Only Retrieval, Then Coverage Preview, Then Extraction
**What:** Search over source cards first, inspect real coverage second, extract numbers third.
**When to use:** Always for SRCH and NLU no-data decisions.
**Why:** Prevents raw CKAN/API/table payloads from polluting model context and keeps no-data decisions source-bound.

### Pattern 4: Canonical Long Format at the Adapter Boundary
**What:** FedStat and World Bank adapters emit the same normalized long-format contract with provenance and units.
**When to use:** Before any downstream aggregation, join, metric derivation, or narration.
**Why:** Critic, narrator, coverage, and eval logic should not branch on source-specific table shapes.

### Anti-Patterns to Avoid
- **Raw API dump to LLM:** Never pass CKAN `package_show`/resource payloads or large table samples straight into model context; compress to source cards/evidence bundles first.
- **LLM-decides-the-number:** LLM may choose a plan or explain, but extracted numeric values must come from DuckDB/PyArrow-backed code paths only.
- **FedStat-only special casing at the UI layer:** Normalize in adapters, not in Streamlit rendering or narrator prompts.
- **Per-thread scout subgraphs by default:** LangGraph docs warn these do not support parallel tool calls cleanly.
- **Planning Phase 1 as one giant prototype:** The phase should generate isolated proofs and contracts, not a half-merged system with unclear acceptance criteria.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Workflow persistence | homemade JSON checkpoint files | `langgraph` + `langgraph-checkpoint-sqlite` | Official support for threads, checkpoints, interrupts, replay |
| Parquet scanning over large dumps | pandas eager full-file reads | `duckdb` + `pyarrow` | Pushdown, schema inspection, direct SQL over Parquet |
| Chat/trace UI shell | custom frontend for Phase 1 | `streamlit` | The project already requires trace visibility fast; Streamlit has native chat/status containers |
| OpenAI-compatible HTTP client | bespoke raw `requests` client long-term | `openai` client against Yandex `base_url` | Better fit for structured outputs, tools, model URI handling |
| Hybrid retrieval baseline | custom BM25 implementation | DuckDB/SQLite FTS + optional `rank-bm25` spike + dense provider abstraction | Lower risk and easier eval than inventing ranking primitives |

**Key insight:** The deceptive complexity in this phase is not "calling an LLM"; it is repeatable retrieval, coverage validation, and checkpointed agent state. The fastest route is to lean on battle-tested primitives and spend engineering effort on source adapters and artifact contracts.

## Common Pitfalls

### Pitfall 1: Treating CKAN as General Web Search
**What goes wrong:** The system floods the model with noisy package/resource payloads and irrelevant search hits.
**Why it happens:** CKAN `package_search` is powerful but broad; raw responses are not model-ready.
**How to avoid:** Bound search calls, compress to source cards, keep rejection reasons, and inspect specific resources only after shortlist selection.
**Warning signs:** Huge candidate sets, trace steps with no narrowing rationale, or prompts carrying raw API JSON.

### Pitfall 2: Skipping Coverage Preview
**What goes wrong:** The model confidently selects a dataset whose real period/country/unit coverage does not satisfy the question.
**Why it happens:** Metadata often overstates availability, especially for wide statistical tables.
**How to avoid:** Make coverage preview a mandatory pre-extraction tool step and a first-class eval dimension.
**Warning signs:** Queries fail only after extraction, or no-data reasoning lacks evidence from actual rows.

### Pitfall 3: Using the Existing Yandex Client as-Is
**What goes wrong:** Auth or endpoint behavior diverges from the verified path.
**Why it happens:** `app/llm/yandex_ai_studio.py` currently uses `Authorization: Bearer ...` and `https://ai.api.cloud.yandex.net/v1`, while project research and Yandex examples for OpenAI-compatible flows use API-key auth and `https://llm.api.cloud.yandex.net/v1`.
**How to avoid:** Make a Phase 1 hardening spike for the Yandex wrapper before building graph logic on top of it.
**Warning signs:** 401/permission errors, missing structured output support, or incompatible tool-calling semantics.

### Pitfall 4: Overcommitting to One Dense Provider Too Early
**What goes wrong:** Retrieval planning blocks on cloud credentials or model infra instead of progressing on catalog quality.
**Why it happens:** Dense search feels like the "real" RAG work, but cards, filters, and evaluation matter more first.
**How to avoid:** Keep a provider abstraction; plan dense retrieval as required, but allow local `sentence-transformers` fallback if Yandex creds are unavailable.
**Warning signs:** No dense spike can run because env vars are unset, and the whole retrieval stream stalls.

### Pitfall 5: Parallel Scouts Without State Discipline
**What goes wrong:** Multi-agent trace becomes noisy or stateful collisions appear.
**Why it happens:** Shared mutable state and per-thread subgraphs are used for workers that should be isolated.
**How to avoid:** Parent graph owns shared state; scouts return append-only typed artifacts; default to per-invocation subgraphs.
**Warning signs:** Non-deterministic candidate ordering, checkpoint conflicts, or hard-to-replay traces.

## Code Examples

Verified patterns from official sources:

### Direct Parquet Query With DuckDB
```sql
-- Source: https://duckdb.org/docs/current/data/parquet/overview.html
SELECT country_id, indicator_id, date, value
FROM read_parquet('/path/to/wb/*.parquet')
WHERE indicator_id = 'NY.GDP.MKTP.CD'
  AND country_id IN ('RUS', 'KAZ')
  AND date BETWEEN 2015 AND 2024;
```

### LangGraph With Local Checkpointing
```python
# Source: https://docs.langchain.com/oss/python/langgraph/persistence
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from typing_extensions import TypedDict

class State(TypedDict):
    route: str

def choose_route(state: State):
    return {"route": "world_bank"}

builder = StateGraph(State)
builder.add_node("choose_route", choose_route)
builder.add_edge(START, "choose_route")
builder.add_edge("choose_route", END)

graph = builder.compile(checkpointer=InMemorySaver())
graph.invoke({"route": ""}, {"configurable": {"thread_id": "phase1-demo"}})
```

### Streamlit Status + Chat Input For Visible Trace
```python
# Source: https://docs.streamlit.io/develop/api-reference/chat/st.chat_input
# Source: https://docs.streamlit.io/develop/api-reference/status/st.status
import streamlit as st

with st.status("Running retrieval...", expanded=True) as status:
    prompt = st.chat_input("Спросите про показатель или исследование")
    if prompt:
        st.write("Intent parsed")
        st.write("Scouts dispatched")
        status.update(label="Trace complete", state="complete")
```

### Yandex Embeddings Via OpenAI-Compatible Client
```python
# Source: https://aistudio.yandex.ru/docs/en/ai-studio/operations/embeddings/search-openai.html
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["YANDEX_API_KEY"],
    base_url="https://llm.api.cloud.yandex.net/v1",
)

doc = client.embeddings.create(
    model=f"emb://{os.environ['YANDEX_FOLDER_ID']}/text-search-doc/latest",
    input="Индекс потребительских цен России",
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single-agent "RAG chatbot" | Hierarchical supervisor + typed tool/artifact graph | 2025-2026 ecosystem standardization around LangGraph/Yandex agent docs | Better traceability, bounded tool scopes, resumable workflows |
| Raw document/file RAG for tabular facts | Metadata cards + deterministic extraction after coverage check | 2025-2026 best practice for fact-grounded data agents | Lower hallucination risk; clearer no-data decisions |
| Pandas-first data handling | DuckDB SQL-first with Arrow/Polars support | Mature DuckDB Parquet + FTS ecosystem through 2025-2026 | Better big-file performance and easier generated SQL |
| Hidden pipeline internals | User-visible trace/status/artifact panels | Streamlit/Yandex/LangGraph tooling now supports this directly | Aligns with Phase 2 demo-value criterion |

**Deprecated/outdated:**
- "RAG alone guarantees correctness": outdated for this project; retrieval must be paired with deterministic extraction and citation/provenance checks.
- "CKAN is just a freshness add-on": rejected by locked decisions; it is a first-class discovery/data path.
- "DeepSeek is the default target model": outdated for this phase; Qwen via Yandex AI Studio is the locked target.

## Open Questions

1. **Dense retrieval provider for the first executable spike**
   - What we know: Locked architecture requires dense retrieval; planner may choose local or Yandex-first.
   - What's unclear: Whether the first runnable spike should depend on Yandex credentials that are currently unset.
   - Recommendation: Plan a provider-agnostic interface and execute lexical baseline first, then either local `sentence-transformers` or Yandex embeddings depending on environment setup at execution time.

2. **Exact artifact schema boundaries**
   - What we know: The architecture requires typed artifacts such as intent, source cards, coverage, extraction plans, and trace events.
   - What's unclear: Whether one unified artifact package or per-domain modules will be easier to evolve during Phase 2.
   - Recommendation: Define a small shared core (`IntentFrame`, `SourceCandidateCard`, `CoverageReport`, `ExtractionPlan`, `TraceEvent`) and keep source-specific details nested, not top-level.

3. **How far the Streamlit spike should go in Phase 1**
   - What we know: UI transparency is a priority criterion, but Phase 1 is still research/spikes.
   - What's unclear: Whether the phase should stop at a trace mock/workbench or include a thin end-to-end demo path.
   - Recommendation: Plan a minimal but real trace workbench: prompt input, visible node timeline, candidate/rejection panels, artifact JSON, and a no-data display. Do not overbuild final UX.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | all executable spikes | ✓ | 3.11.9 | — |
| `pip` | install research/spike deps | ✓ | 24.0 | — |
| Node/npm | GSD helpers only | ✓ | Node 24.12.0 / npm 11.6.2 | — |
| local dumps root `/Users/a/Downloads/dumps` | source research/spikes | ✓ | filesystem | — |
| FedStat local dump | FedStat adapter research | ✓ | `fedstatru.zip` present | use archive/bounded probes |
| World Bank local dump | World Bank adapter research | ✓ | `wb/` present | — |
| live NSED CKAN API | CKAN discovery research | ✓ | `package_search?rows=0` returned count `53799` on 2026-05-09 | local promoted metadata cache |
| World Bank API | validation/fallback research | ✓ | reachable on 2026-05-09 | local WB dump |
| Yandex AI Studio env vars | model/embedding/tool spikes | ✗ | — | use local retrieval spikes first; keep Yandex integration spike gated |
| DuckDB CLI | shell-based manual probing | ✗ | — | use Python `duckdb` package |

**Missing dependencies with no fallback:**
- None for planning/research itself.

**Missing dependencies with fallback:**
- Yandex runtime credentials are unset in this shell; Phase 1 can still progress on local retrieval/adapters, but any Qwen/embedding/tool-call spike must be explicitly gated on env setup.
- DuckDB CLI is absent; this does not block implementation because the Python package is the standard runtime path.

## Sources

### Primary (HIGH confidence)
- Official project memory:
  - `.planning/phases/01-data-architecture-research/01-CONTEXT.md`
  - `.planning/PROJECT.md`
  - `.planning/REQUIREMENTS.md`
  - `.planning/ROADMAP.md`
  - `.planning/STATE.md`
  - `.planning/DATA_REPORT.md`
  - `.planning/ARCHITECTURE_STACK.md`
  - `.planning/ARCHITECTURE_RESEARCH.md`
  - `.planning/YANDEX_AI_STUDIO_RESEARCH.md`
  - `AGENTS.md`
- LangGraph docs:
  - https://docs.langchain.com/oss/python/langgraph
  - https://docs.langchain.com/oss/python/langgraph/persistence
  - https://docs.langchain.com/oss/python/langgraph/use-subgraphs
- DuckDB docs:
  - https://duckdb.org/docs/current/data/parquet/overview.html
  - https://duckdb.org/docs/current/core_extensions/full_text_search
- Streamlit docs:
  - https://docs.streamlit.io/develop/api-reference/chat/st.chat_input
  - https://docs.streamlit.io/develop/api-reference/status/st.status
- Yandex AI Studio docs:
  - https://aistudio.yandex.ru/docs/en/ai-studio/concepts/agents/
  - https://aistudio.yandex.ru/docs/en/ai-studio/concepts/generation/models.html
  - https://aistudio.yandex.ru/docs/en/ai-studio/concepts/generation/structured-output.html
  - https://aistudio.yandex.ru/docs/en/ai-studio/operations/embeddings/search-openai.html
  - https://aistudio.yandex.ru/docs/en/ai-studio/concepts/mcp-hub/
- CKAN docs:
  - https://docs.ckan.org/en/latest/api/index.html?highlight=package_search
- World Bank docs:
  - https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation
- Verified current package versions/publish dates:
  - PyPI JSON API for `langgraph`, `duckdb`, `pyarrow`, `polars`, `streamlit`, `pydantic`, `sentence-transformers`, `rapidfuzz`, `rank-bm25`, `openai`, `langgraph-checkpoint-sqlite`

### Secondary (MEDIUM confidence)
- Current live endpoint probes performed on 2026-05-09:
  - `https://repository.nsedc.ru/api/3/action/package_search?rows=0`
  - `https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL?format=json&per_page=1`

### Tertiary (LOW confidence)
- None required for the main recommendations.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - locked by `01-CONTEXT.md` and verified against official docs/current package registries.
- Architecture: HIGH - project architecture is already chosen; official LangGraph/Streamlit/Yandex/DuckDB docs support the implementation path.
- Pitfalls: HIGH - grounded in locked project decisions, current repo state, and official framework behavior.

**Research date:** 2026-05-09
**Valid until:** 2026-05-16
