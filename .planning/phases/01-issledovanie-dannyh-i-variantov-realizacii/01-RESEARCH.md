# Phase 1: Исследование данных и вариантов реализации - Research

**Researched:** 2026-05-09  
**Domain:** source-bound economic data assistant discovery, metadata retrieval, deterministic data extraction spikes  
**Confidence:** HIGH for local data/API facts; MEDIUM for final MVP stack recommendations because Phase 1 intentionally defers decisions to team discussion

## User Constraints

### From Project Planning

- Core value: numbers must come from deterministic code or trusted source adapters, never from LLM memory.
- Every numeric result must carry source/provenance; a number without a source is an error.
- If requested data is unavailable, the system must honestly report that and show what was checked.
- CKAN is a trusted NSED catalog API, not general web search. Use bounded `package_search`, `package_show`, and resource inspection; cache only promoted metadata.
- Local secrets stay in `.env`; never commit API keys.
- Prefer traceable artifacts: research notes, source candidates, rejection reasons, generated SQL/code, extraction logs, verification results.
- UI is not Phase 1 implementation scope, but project direction says Streamlit is the first demo UI target and must expose state machine, trace, artifacts, and feedback/fix requests.
- Phase 1 may run small spikes, but implementation choices remain recommendations until team discussion.

### Project Constraints (from AGENTS.md)

- Use the GSD loop for non-trivial work: discuss phase, plan phase, execute phase, verify work.
- Treat `.planning/PROJECT.md`, `.planning/ROADMAP.md`, `.planning/REQUIREMENTS.md`, and `.planning/STATE.md` as durable project memory.
- The assistant is source-bound: numbers must come from deterministic code or trusted source adapters, never from LLM memory.
- CKAN is a trusted NSED catalog API, not general web search; use bounded package/resource search and cache only promoted metadata.
- Keep local secrets in `.env`; never commit API keys.
- Prefer traceable artifacts: research notes, source candidates, rejection reasons, generated SQL/code, extraction logs, and verification results.
- Streamlit is the first demo UI target; the UI must expose the state machine, trace, artifacts, and user feedback/fix requests.

## Summary

Phase 1 should plan discovery work, not a full prototype. The critical unknowns are: which MVP query types can be supported by the actual local dumps, how well lexical/hybrid search performs on metadata cards, how much FedStat normalization is needed for selected indicators, and which LLM/API path reliably produces structured NLU artifacts without inventing data.

The current evidence strongly supports a source-bound architecture: build a metadata catalog first, search source cards rather than numeric tables, verify coverage before extraction, and let deterministic Python/DuckDB/PyArrow code produce any numeric values. World Bank is the fastest reliable source for cross-country MVP cases. FedStat is essential for Russian official statistics but needs a wide-to-long normalizer. NSED CKAN should be treated as live discovery/provenance/freshness, not as a raw context dump for the LLM.

**Primary recommendation:** Plan Phase 1 as four bounded spikes: data map verification, metadata search benchmark, NLU structured-output benchmark, and MVP test-case selection with explicit no-data/ambiguity cases.

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| NLU-01 | Classify Russian NL queries into simple, comparative, research, derived metric, ambiguous, no-data | Use structured `IntentFrame` output plus 5-8 golden prompts; do not hardcode classification as the only decision path. |
| NLU-02 | Formalize query into geography, period, disciplinary angle, concrete questions | Use Pydantic artifacts with known fields and open assumptions; validate slots against source catalogs. |
| NLU-03 | Ask clarifying questions for ambiguous queries and use answers | Plan a clarification policy: ask only when missing fields block retrieval/extraction; otherwise continue with explicit assumptions. |
| NLU-04 | Identify when requested data is absent and report honestly | Requires source candidate log, coverage preview, and no-data explanation artifact before any final answer. |
| SRCH-01 | RAG index over FedStat metadata | Build FedStat catalog from `metdata.csv`, `metadata/*.json`, and actual Parquet/clean JSONL availability; do not rely on incomplete `metadata.jsonl`. |
| SRCH-02 | RAG index over World Bank metadata | Build WB catalog from `indicators.json`, `metadata.json/jsonl`, `sources.json`, `countries.json`, and actual Parquet files. |
| SRCH-03 | `find_data` by keywords, topic, country, period | Start with DuckDB/SQLite FTS + RapidFuzz + rules; benchmark against optional embeddings/File Search. |
| SRCH-04 | Search results include source, period, geography, units | SourceCandidateCard must include unit, time coverage, geo coverage, source URL, availability flags, and quality flags. |

</phase_requirements>

## Standard Stack

### Core

| Library | Verified Version | Purpose | Why Standard |
|---------|------------------|---------|--------------|
| Python | 3.11.9 local | Phase spike scripts and adapters | Already available locally; compatible with current project. |
| requests | 2.33.1, published 2026-03-30 | CKAN/Yandex/World Bank HTTP calls | Already in requirements; enough for bounded API clients. |
| python-dotenv | 1.2.2, published 2026-03-01 | Local `.env` loading | Already in requirements; required for API key hygiene. |
| Pydantic | 2.13.4, published 2026-05-06 | Typed artifacts: IntentFrame, SourceCandidateCard, CoverageReport | Official v2 validation model fits structured LLM output and tool boundaries. |
| DuckDB | 1.5.2, published 2026-04-13 | SQL over Parquet, catalog tables, FTS spike | Official docs support Parquet scans, schema/metadata inspection, filter/projection pushdown, and FTS extension. |
| PyArrow | 24.0.0, published 2026-04-21 | Parquet metadata/schema inspection and selective reads | Official dataset API supports column and filter reads; useful before loading large FedStat files. |
| pandas | 3.0.2, published 2026-03-31 | Small tabular inspection and exported demo scripts | Readable for generated scripts; use only after coverage narrows data size. |
| RapidFuzz | 3.14.5, published 2026-04-07 | Fuzzy matching for countries, indicators, aliases | Lightweight way to handle Russian/English aliases before dense retrieval. |
| openai | 2.36.0, published 2026-05-07 | OpenAI-compatible Yandex AI Studio client | Yandex docs show OpenAI-compatible examples for chat completions, embeddings, and structured output. |

### Supporting

| Library | Verified Version | Purpose | When to Use |
|---------|------------------|---------|-------------|
| Streamlit | 1.57.0, published 2026-04-28 | Demo UI later; Phase 1 can sketch trace requirements | Use in Phase 3, but Phase 1 should keep artifacts UI-ready. |
| pytest | 9.0.3, published 2026-04-07 | Golden eval harness for spikes | Use if Phase 1 creates reusable scripts or query cases. |
| Polars | 1.40.1, published 2026-04-07 | Lazy large-table transforms | Optional fallback when DuckDB SQL or pandas is awkward. |
| Yandex AI Studio structured output | docs checked 2026-05-09 | JSON schema response formatting | Use for NLU benchmark; keep deterministic validation after model output. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| DuckDB FTS baseline | FAISS / Yandex File Search | Dense search may help synonyms, but lexical search is more explainable and catches exact codes/terms. Benchmark before adopting embeddings. |
| pandas extraction first | DuckDB SQL first | pandas is readable, but risks full-file loads; DuckDB gives safer filter/projection pushdown and reproducible SQL artifacts. |
| One unified index only | Per-source search adapters + merge | Per-source adapters preserve FedStat/WB/CKAN semantics and make rejection logs clearer. |
| Full LangGraph implementation now | Simple spike scripts + typed artifacts | Phase 1 should answer planning unknowns; defer workflow build to Phase 2 after team decisions. |

**Installation for Phase 1 spikes:**

```bash
python3 -m pip install -U requests python-dotenv pydantic duckdb pyarrow pandas rapidfuzz openai pytest
```

**Version verification performed:** `python3 -m pip index versions ...` and PyPI JSON upload timestamps on 2026-05-09.

## Architecture Patterns

### Recommended Project Structure for Phase 1 Outputs

```text
app/
  schemas/
    artifacts.py          # IntentFrame, SourceCandidateCard, CoverageReport
  retrieval/
    catalog_builders.py   # FedStat/WB/CKAN catalog builders
    lexical_search.py     # DuckDB/SQLite FTS and fuzzy matching spike
  data/
    fedstat_probe.py      # schema/coverage probes for selected codes
    wb_probe.py           # WB coverage and extraction probe
  evals/
    golden_cases.yaml     # 5-8 Phase 1 test prompts
    run_retrieval_eval.py # compare candidate ranking modes
  llm/
    yandex_ai_studio.py   # existing client, needs auth/header verification
```

### Pattern 1: Source Cards Before Numeric Data

**What:** Convert FedStat, World Bank, and CKAN results into compact `SourceCandidateCard` records. Include title, source, indicator/package id, unit, time coverage, geo coverage, URLs, availability flags, and rejection risks.

**When to use:** All search/RAG work in Phase 1.

**Example:**

```python
from pydantic import BaseModel

class SourceCandidateCard(BaseModel):
    source: str
    dataset_id: str
    title: str
    unit: str | None = None
    time_coverage: str | None = None
    geo_coverage: list[str] = []
    source_url: str | None = None
    availability_flags: list[str] = []
    quality_flags: list[str] = []
    why_matched: str
    match_mode: str
```

### Pattern 2: Coverage Preview Before Extraction

**What:** Search only identifies candidates. A separate deterministic preview checks actual schema, periods, geographies, null values, units, and file availability before any number is exposed.

**When to use:** Required for NLU-04 and SRCH-04; especially important for WB 2025 null rows and FedStat wide Parquet.

**Example:**

```sql
-- Source: DuckDB Parquet docs
DESCRIBE SELECT * FROM read_parquet('wb/parquet/NY.GDP.MKTP.CD.parquet');

SELECT countryiso3code, min(date) AS min_year, max(date) AS max_year, count(value) AS non_null_values
FROM read_parquet('wb/parquet/NY.GDP.MKTP.CD.parquet')
WHERE value IS NOT NULL
GROUP BY countryiso3code;
```

### Pattern 3: Per-Source Search Adapters With Common Output

**What:** Implement `FedStatSearch`, `WorldBankSearch`, and `CkanSearch` separately, then merge/rerank their common `SourceCandidateCard` outputs.

**When to use:** Phase 1 search benchmark and later `find_data`.

**Why:** FedStat metadata, WB indicator metadata, and CKAN packages have different semantics. Per-source adapters keep source-specific filters and make rejection reasons auditable.

### Pattern 4: Structured NLU With Validation

**What:** Ask Yandex AI Studio for JSON schema output, validate with Pydantic, then verify slots against catalogs. LLM output is a hypothesis, not a fact source.

**When to use:** NLU-01..NLU-03 spike.

**Example:**

```python
# Source: Yandex AI Studio structured output docs
response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "intent_frame",
        "schema": {
            "type": "object",
            "properties": {
                "query_type": {"type": "string"},
                "geography": {"type": "array", "items": {"type": "string"}},
                "period": {"type": "string"},
                "needs_clarification": {"type": "boolean"},
                "missing_fields": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["query_type", "geography", "period", "needs_clarification", "missing_fields"],
        },
    },
}
```

### Anti-Patterns to Avoid

- **Embedding numeric tables directly:** It invites hallucinated numeric answers and hides provenance. Index metadata cards only.
- **Treating `metadata.jsonl` as FedStat truth:** Existing data research found it effectively incomplete; build from `metdata.csv`, `metadata/*.json`, and actual file presence.
- **Letting CKAN responses enter the LLM raw:** `package_search` can return thousands of noisy matches. Compress into candidate cards and call `package_show` only for top candidates.
- **Classifying "no data" from search misses only:** A no-data claim needs attempted sources, query variants/proxies, and coverage checks.
- **Committing to a model/retrieval engine in Phase 1:** Spikes should produce evidence and recommendations; team discussion chooses Phase 2 scope.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON schema validation | Custom dict checks | Pydantic v2 | Better error reporting, typed artifacts, reusable tests. |
| Parquet SQL/filtering | Manual row scanning | DuckDB `read_parquet` and PyArrow dataset reads | Official support for schema inspection and filter/projection pushdown. |
| Full-text baseline | Ad hoc substring-only scoring | DuckDB FTS or SQLite FTS5 plus RapidFuzz | BM25/ranked search and Russian stemming support are available. |
| CKAN client semantics | Freeform web search | CKAN Action API: `package_search`, `package_show`, `resource_search` | CKAN API is the trusted catalog boundary. |
| Arbitrary generated extraction code | LLM-written unrestricted scripts | Fixed operation templates: inspect, filter, melt, aggregate, export | Preserves deterministic numbers and reproducibility. |
| Source/no-data trace | Freeform prose only | Structured candidate and rejection logs | Required for honest no-data behavior and later UI trace. |

**Key insight:** The hard part is not writing a chatbot. It is proving that candidate sources actually contain the requested facts, units, geography, and period before the LLM narrates anything.

## Common Pitfalls

### Pitfall 1: Search Looks Good But Data Is Missing

**What goes wrong:** Metadata title matches the query, but the requested period/geography is null or absent.  
**Why it happens:** Catalog metadata describes a dataset broadly; actual table coverage varies by dimension and period.  
**How to avoid:** Add coverage preview as a required step between search and extraction.  
**Warning signs:** Candidate cards with no `has_non_null_values` or no inspected period/geography coverage.

### Pitfall 2: FedStat Wide Tables Are Treated Like WB Long Tables

**What goes wrong:** Code expects `year`/`value` columns but FedStat Parquet has `column00`, `column01`, etc. with the actual header in row 0.  
**Why it happens:** Parquet extension alone does not normalize statistical layout.  
**How to avoid:** Plan a FedStat normalizer spike for selected codes only; compare output row counts to metadata.  
**Warning signs:** Extraction code filters nonexistent `year` or `value` fields on FedStat files.

### Pitfall 3: Units Are Missing Or Inferred Too Late

**What goes wrong:** Answers compare current US dollars, constant dollars, percentages, rubles, and indexes as if they are equivalent.  
**Why it happens:** WB `unit` field is mostly empty; units are often embedded in indicator names/notes. FedStat units are source-specific strings.  
**How to avoid:** Store `unit_raw`, `unit_normalized`, and `unit_source` in candidate cards and coverage reports.  
**Warning signs:** SourceCandidateCard has no unit but extraction is allowed to proceed.

### Pitfall 4: Ambiguity Policy Becomes Annoying

**What goes wrong:** The system asks too many questions instead of doing useful discovery.  
**Why it happens:** Missing slot detection is confused with blocking ambiguity.  
**How to avoid:** Ask only when a missing field prevents source selection or would materially change the result; otherwise continue with assumptions shown in trace.  
**Warning signs:** "дай инфляцию" asks five questions before showing candidate interpretations.

### Pitfall 5: Yandex Endpoint/Auth Drift

**What goes wrong:** One client uses `Bearer` against `https://ai.api...`, while the smoke-tested path used `Api-Key` against `https://llm.api...`.  
**Why it happens:** Yandex docs and project notes show multiple compatible endpoints and auth styles depending on API.  
**How to avoid:** Phase 1 should include an explicit LLM client smoke test for the exact endpoint, header, model URI, folder id, and structured output path.  
**Warning signs:** `permission_error`, empty response content, or structured output silently returned as plain text.

## Code Examples

### CKAN Bounded Search

```python
import requests

def package_search(query: str, rows: int = 10) -> dict:
    response = requests.get(
        "https://repository.nsedc.ru/api/3/action/package_search",
        params={"q": query, "rows": rows},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError(payload)
    return payload["result"]
```

### DuckDB FTS Candidate Search

```sql
-- Source: DuckDB FTS docs
INSTALL fts;
LOAD fts;

PRAGMA create_fts_index(
  'source_cards',
  'source_id',
  'title',
  'description',
  'topics',
  stemmer = 'russian',
  stopwords = 'none',
  overwrite = 1
);

SELECT source_id, title, score
FROM (
  SELECT *,
         fts_main_source_cards.match_bm25(source_id, 'валовой внутренний продукт') AS score
  FROM source_cards
) s
WHERE score IS NOT NULL
ORDER BY score DESC
LIMIT 10;
```

### PyArrow Selective Read

```python
import pyarrow.dataset as ds

dataset = ds.dataset("wb/parquet/NY.GDP.MKTP.CD.parquet", format="parquet")
table = dataset.to_table(
    columns=["indicator_id", "countryiso3code", "date", "value"],
    filter=(ds.field("countryiso3code").isin(["RUS", "KAZ"])) & (ds.field("date") >= 2015),
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| "RAG means vector DB" | Hybrid/source-card retrieval plus coverage preview | Reinforced by current project data research and DuckDB/Yandex docs | Planning should compare lexical, hybrid, and embeddings instead of assuming vectors. |
| LLM reads tables and answers | LLM creates structured plans; tools extract values | Project constraint from TЗ and AGENTS | All numeric tasks require deterministic adapters and manifests. |
| One monolithic agent | Typed artifacts and bounded tools; LangGraph later if selected | Current architecture research | Phase 1 can evaluate artifacts before building full orchestration. |
| Live API as direct context | CKAN adapter with bounded search and compressed candidate cards | CKAN result count and noisy broad queries verified | Prevents context noise and preserves trace. |

**Deprecated/outdated for this project:**

- Pure dense retrieval as the first search implementation: useful as a benchmark candidate, not a baseline.
- Full FedStat normalization in Phase 1: too large for discovery; normalize selected indicators and document complexity.
- Fine-tuning: not justified before retrieval, coverage, and NLU structured-output baselines are measured.

## Open Questions

1. **Which 5-8 MVP prompts should drive evaluation?**
   - What we know: Phase scope needs simple, comparative, research, derived metric, ambiguous, and no-data cases.
   - What's unclear: Final prompts are not selected.
   - Recommendation: Choose prompts that exercise WB easy path, FedStat hard path, CKAN discovery, ambiguity, and no-data.

2. **Does DuckDB FTS beat simple keyword + aliases on Russian economic metadata?**
   - What we know: DuckDB FTS supports BM25 and Russian stemmer; CKAN/FedStat search can be noisy.
   - What's unclear: Quality on the actual 5-8 prompts.
   - Recommendation: Benchmark top-k hit quality against substring/RapidFuzz and optional embeddings.

3. **Which Yandex model should handle structured NLU?**
   - What we know: DeepSeek 3.2 smoke test passed; architecture notes mention Qwen/YandexGPT candidates.
   - What's unclear: Availability and quality for JSON schema output on Russian economic prompts.
   - Recommendation: Phase 1 should run the same IntentFrame eval across accessible models and record parse success, slot accuracy, and clarification quality.

4. **How much FedStat normalization is required for the MVP?**
   - What we know: FedStat wide Parquet is heterogeneous; `clean_jsonl` covers only a small subset.
   - What's unclear: Whether selected MVP indicators can use clean JSONL or need wide-to-long support.
   - Recommendation: Probe selected codes first (`57319`, `40578`, `33568`/`61028`, `30973`) before committing to broader normalization.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python | All Phase 1 scripts | yes | 3.11.9 | none needed |
| pip | Package install/version audit | yes | 24.0 | none needed |
| requests | CKAN/Yandex HTTP | yes | 2.32.5 installed; latest 2.33.1 | use stdlib `urllib` for small probes |
| python-dotenv import | Local `.env` loading | no in current shell import check | declared in requirements | run `python3 -m pip install -r requirements.txt` |
| PyArrow | Parquet inspection | yes | 23.0.1 installed; latest 24.0.0 | DuckDB after install |
| pandas | Small table work | yes | 2.3.3 installed; latest 3.0.2 | PyArrow tables |
| DuckDB Python | SQL/FTS/parquet spike | no | latest 1.5.2 | SQLite FTS + PyArrow, but weaker for Parquet SQL |
| DuckDB CLI | Manual SQL probes | no | unavailable | Python package after install |
| sqlite3 CLI | Catalog/FTS fallback | yes | 3.51.0 | DuckDB after install |
| RapidFuzz | Fuzzy aliases | yes | 3.14.3 installed; latest 3.14.5 | substring/regex baseline |
| Pydantic | Typed artifacts | yes | 2.12.5 installed; latest 2.13.4 | dataclasses + manual validation, not recommended |
| Streamlit | Later UI/trace demo | yes | 1.55.0 installed; latest 1.57.0 | CLI reports for Phase 1 |
| openai Python package | Yandex OpenAI-compatible API | no | latest 2.36.0 | existing `requests` client |
| pytest | Eval harness | no | latest 9.0.3 | script assertions, but install pytest for repeatable evals |
| NSED CKAN API | SRCH discovery | yes | API returned `success=true`, count `53799` on 2026-05-09 | cached local metadata if network fails |
| Local FedStat dump | Data map/FedStat probes | yes | `/Users/a/Downloads/dumps/fedstatru/fedstatru.zip` | CKAN resources |
| Local WB dump | Data map/WB probes | yes | `/Users/a/Downloads/dumps/wb/data.zip` | World Bank API or CKAN resources |

**Missing dependencies with no fallback:**

- None blocking for research. DuckDB and pytest should be installed before serious spikes, but Phase 1 can begin with PyArrow/requests.

**Missing dependencies with fallback:**

- DuckDB Python: fallback is PyArrow + SQLite FTS, but planning should include DuckDB install.
- openai package: fallback is existing requests-based Yandex client, but structured output is easier to benchmark with OpenAI-compatible SDK.
- pytest: fallback is manual script assertions; install for durable evals.

## Validation Architecture

Skipped. `.planning/config.json` explicitly sets `workflow.nyquist_validation` to `false`.

## Sources

### Primary (HIGH confidence)

- Local planning files: `.planning/PROJECT.md`, `.planning/ROADMAP.md`, `.planning/REQUIREMENTS.md`, `.planning/DATA_REPORT.md`, `.planning/ARCHITECTURE_STACK.md`, `.planning/ARCHITECTURE_RESEARCH.md`, `.planning/YANDEX_AI_STUDIO_RESEARCH.md`.
- Local AGENTS.md project instructions.
- Local environment probes on 2026-05-09: Python/package import checks, PyPI version checks, CKAN API call, local dump paths.
- DuckDB Parquet docs: https://duckdb.org/docs/current/data/parquet/overview.html
- DuckDB FTS docs: https://duckdb.org/docs/lts/core_extensions/full_text_search.html
- CKAN Action API docs: https://docs.ckan.org/en/latest/api/index.html
- PyArrow Dataset docs: https://arrow.apache.org/docs/python/dataset.html
- Yandex AI Studio structured output docs: https://aistudio.yandex.ru/docs/en/ai-studio/operations/generation/completions-structured
- LangGraph persistence/HITL docs: https://docs.langchain.com/oss/python/langgraph/persistence
- Streamlit chat input docs: https://docs.streamlit.io/develop/api-reference/chat/st.chat_input

### Secondary (MEDIUM confidence)

- Existing architecture recommendation files for LangGraph, Streamlit, hybrid retrieval, and multi-agent layering. These are project baselines, but Phase 1 must still benchmark before treating them as accepted decisions.

### Tertiary (LOW confidence)

- None used as authoritative input. Web search results were only accepted when they led to official docs or current package registries.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH for Python/DuckDB/PyArrow/Pydantic/requests versions and capabilities; MEDIUM for optional AI Studio/LangGraph choices because model availability and team decision are pending.
- Architecture: HIGH for source-bound/data-tool separation; MEDIUM for hierarchical agent implementation because Phase 1 should not lock orchestration yet.
- Pitfalls: HIGH for data-shape and provenance pitfalls from local data report; MEDIUM for model/API pitfalls because exact Yandex endpoint/header should be re-smoke-tested in the implementation environment.

**Research date:** 2026-05-09  
**Valid until:** 2026-05-16 for AI Studio/model/API details; 2026-06-08 for local data and Python stack recommendations.
