# Phase 2 Workflow Fix Diagnosis

**Created:** 2026-05-11  
**Updated:** 2026-05-11 after graph-aware RAG code review  
**Purpose:** зафиксировать ошибки текущего Phase 2 workflow перед переработкой кода.  
**Scope:** запрос пользователя -> агенты/узлы -> артефакты -> eval/UI.  

## Executive Summary

Phase 2 сейчас выглядит не как самостоятельный source-bound агент, а как смесь:

- реального workflow service;
- golden-case acceptance harness;
- подсказочной `golden-coverage-matrix`;
- live LLM требований без стабильного bounded режима;
- слишком слабого eval, который пропускает пустые ответы как "acceptable".

Главная проблема не в самом русском языке. Файлы реально сохранены в UTF-8, русские строки в `golden-cases.yaml` и Python-коде читаются корректно. Видимые `Рљ...` в PowerShell - это проблема отображения консоли. Но русская семантика всё равно обрабатывается хрупко: через небольшие alias/synonym словари, regex и LLM-промпты без отдельного слоя нормализации запроса.

Самая опасная архитектурная ошибка: acceptance fixtures начали протекать в runtime. `case_id` из acceptance runner попадает в `Phase2State`, после чего `Research Designer` читает `golden-coverage-matrix.json` и передает `matrix_hint` в LLM. Это превращает golden cases из независимого измерителя качества в подсказку для агента. В обычном пользовательском запросе такой подсказки нет, поэтому eval начинает проверять не продукт, а продукт плюс шпаргалку.

После добавления graph-aware RAG часть retrieval-артефактов изменилась. Теперь актуальная картина не "dense + lexical + reranker seam", а:

```text
query
-> LexicalBM25Retriever
-> DenseQdrantRetriever
-> KnowledgeGraphStore.graph_first_card_ids(query)
-> GraphExpander.expand(dense seed card_ids)
-> Qdrant payload fetch for graph neighbours
-> RRF fusion
-> HybridRetrievalResult(candidates, rejected_candidates, SubgraphContext)
```

Это улучшает retrieval-контекст, но не исправляет само по себе workflow-ошибки: graph candidates всё равно должны пройти coverage, extraction planner, deterministic tools, critic и acceptance scoring. Graph RAG не должен получать `golden-coverage-matrix` как answer key.

## Current Runtime Data Flow

Фактическая цепочка сейчас:

```text
scripts/run_phase2_acceptance.py
  -> loads golden-cases.yaml
  -> loads golden-coverage-matrix.json
  -> for each case builds WorkflowRunConfig(case_id=GC-...)
  -> app.workflow.service.run_user_query(query, run_config)
  -> run_user_query_to_pending_finalization()
  -> initial Phase2State includes:
       run_id
       query
       intent=None
       evidence=None
       coverage_reports=[]
       extraction_plan=None
       dataset_artifacts=[]
       script_artifacts=[]
       _case_id=GC-...
       _live_llm_required=True
       _live_embeddings_required=True
  -> app.workflow.graph.build_phase2_graph().invoke(state)
  -> supervisor
  -> intent_analyst
  -> research_designer
       reads golden-coverage-matrix.json when _case_id exists
       passes matrix_hint to design_research()
  -> source_scouts
       run_source_scouts()
       -> HybridRetriever.search()
       -> BM25 + dense Qdrant + graph_first + graph expansion + RRF
       -> EvidenceBundleArtifact(selected_sources, rejected_sources)
  -> coverage_schema
  -> extraction_planner
  -> deterministic_tools
  -> finalization_pending
  -> service._finalize_state()
  -> critic
  -> visualization
  -> narrator
  -> WorkflowResponse
  -> acceptance scorer
```

This means the product path and eval path are not cleanly separated.

### First-stage request processing bug notes

Current first-stage processing is:

```text
UI / HTTP / CLI / acceptance
  -> run_user_query(query, WorkflowRunConfig)
  -> run_user_query_to_pending_finalization()
  -> Phase2State(query, run_id, runtime flags)
  -> supervisor
  -> intent_analyst
```

Problems observed at this first boundary:

- Agent 1 is currently missing as a real component. The workflow does not correctly parse and preserve the input string before agent routing; it only stores raw `query: str` in `Phase2State`.
- There is no explicit `RequestEnvelope`; the raw `query: str` is mixed with runtime flags, artifact paths, and acceptance-only `case_id`.
- `WorkflowRunConfig.live_llm_required` is still a product-facing boolean, so callers can construct non-live behavior instead of choosing a strict runtime mode.
- `DataAgentWebHandler._run_config()` accepts `local_mode` from request payload and turns it into `live_llm_required=False`; this makes offline/no-response behavior reachable from the HTTP product path.
- `Supervisor` catches LLM errors and silently defaults to `research` via `triage_llm_failed_using_research_default`; this is another no-response fallback and must become an explicit `llm_error`/gated state.
- `service.run_user_query_to_pending_finalization()` catches any graph exception and returns `finalization_pending` with `graph_error:*`; this should be an explicit error artifact/readiness failure, not a normal pending state that downstream finalization can accidentally narrate.
- The first two agents do not receive the same clean input contract. `Supervisor` receives raw `query` plus implicit `_live_llm_required`; `Intent Analyst` receives raw `query`; later nodes receive richer artifacts. This makes it easy for later code to infer around missing structure.

Target first-stage processing should be:

```text
RequestEnvelope
  query_text: str
  normalized_query_text: str
  language: ru
  locale: "ru-RU" | ...
  runtime_mode: LIVE_JURY | UNIT_TEST
  artifact_root: Path
  request_id/run_id
  acceptance_metadata: absent in product path
  no expected source_id/outcome

Agent 1 - Request Intake / Query Normalizer
  input:
    raw_query_text
    caller: ui | api | cli | acceptance
  output:
    RequestEnvelope
    QueryNormalizationReport:
      original_text
      stripped_text
      normalized_text
      detected_language
      parse_warnings
      user_visible_input_errors
  responsibilities:
    validate non-empty query
    preserve original text
    normalize whitespace and punctuation
    detect language/locale
    keep the query as user input, not as an answer hint
    never attach golden expected source/outcome

SupervisorInput
  request_id
  query_text
  normalized_query_text
  locale
  runtime_mode

SupervisorOutput
  route: direct | research | no_data_candidate | needs_clarification_candidate
  budget: bounded tool/LLM call budget
  llm_status: ok | llm_timeout | llm_error | llm_unavailable
  reasoning_summary

IntentAnalystInput
  query_text
  locale
  supervisor_route

IntentFrame
  category
  known_fields
  missing_fields
  source_preferences_from_user_only
  ambiguity_reasons
  confidence
```

If `Supervisor` or `Intent Analyst` cannot call the live LLM in product mode, the workflow must stop with explicit `llm_*` status. It must not choose `research` or fabricate an intent through rules.

### Clarification must continue the same request, not become a fresh query

Clarification is the first important branch after `Intent Analyst`, not a separate workflow start. If the LLM says the request lacks required context, the system should return `needs_clarification` with a durable pending state and wait for the user's answer.

Correct clarification flow:

```text
Agent 1 - Request Intake
  -> RequestEnvelope(run_id=phase2-abc, query_text=original question)
Agent 2 - Supervisor
  -> SupervisorDecision(route=needs_clarification_candidate or direct/research)
Agent 3 - Intent Analyst
  -> IntentFrame(
       known_fields={...},
       missing_fields=["period", "geography"],
       needs_clarification=true
     )
Agent 4 - Clarification Manager
  -> ClarificationRequestArtifact(
       run_id=phase2-abc,
       original_query_text,
       current_intent,
       missing_fields,
       questions,
       resume_from="intent_analyst" | "source_scouts" | "coverage_schema"
     )
User answer
  -> ClarificationTurn(
       run_id=phase2-abc,
       answer_text,
       refers_to_missing_fields=[...]
     )
Agent 3 - Intent Analyst re-analysis
  -> Updated IntentFrame for the same run_id
  -> continue workflow from the correct node
```

Current code violates this in `service.continue_user_query()`:

- If `pending-clarification.json` is missing, it calls `run_user_query(clarification_answer, ...)`, turning the clarification into a fresh standalone request.
- If the pending file cannot be parsed, it also starts a fresh request.
- When no extracted data exists, it calls `run_user_query(f"{old_query} | Уточнение: {answer}")`, which changes the data shape from structured continuation into a concatenated query string.
- If LLM re-analysis fails, it manually injects `clarification_answer` into `known_fields`, which is another no-response fallback.

Required fix:

- Introduce Agent 4 `Clarification Manager` as a real workflow component.
- Persist pending clarification as a typed artifact, not an incidental JSON side file only.
- `continue_user_query(run_id, answer)` must require a valid pending state; if missing/corrupt, return explicit `clarification_state_missing` or `clarification_state_corrupt`, not a fresh answer.
- The user's clarification answer must be attached to the existing `run_id` as a turn/event, then re-parsed by `Intent Analyst` against the previous `IntentFrame`.
- The system must preserve the original query and store the clarification separately; concatenated query strings may be used only as LLM prompt context, never as the canonical request.

### Request-to-source-discovery flow: how "found" currently happens

Current request-to-found flow:

```text
0. User
  sends raw query text

1. Request Intake / Query Normalizer
  currently missing; raw query is stored directly in Phase2State.query

2. Supervisor
  reads Phase2State.query
  writes _supervisor_route

3. Intent Analyst
  reads Phase2State.query
  writes IntentFrame

4. Clarification Manager
  currently implicit in service/narrator, not a real graph node
  should stop here when IntentFrame.needs_clarification=true

5. Research Designer
  only for non-direct routes
  writes ResearchDesignArtifact

6. Source Scouts
  input:
    query: raw Phase2State.query
    expected_sources: IntentFrame.source_preferences
    index_manifest_path
  calls:
    HybridRetriever.search(query, expected_sources, limit=5)
  output:
    EvidenceBundleArtifact(selected_sources, rejected_sources)
```

`HybridRetriever.search()` currently decides source candidates this way:

```text
query
  -> LexicalBM25Retriever.search(query)
       token match over source-card embedding_text
       small RU/EN synonym map
  -> DenseQdrantRetriever.search(query)
       live Yandex query embedding
       Qdrant ANN over phase1_source_cards
  -> KnowledgeGraphStore.graph_first_card_ids(query)
       deterministic parse_query_intent(query)
       hardcoded concepts/geographies/years/source aliases
       concept -> SourceCard graph edges
  -> GraphExpander.expand(dense seed card_ids)
       dense top cards -> graph entity_link
       2-hop SQLite graph traversal
       Qdrant payload fetch by neighbour card_id
  -> RRF fusion
       lexical weight 0.55
       dense weight 4.0
       graph_first weight 2.5
       graph_neighbour weight 1.5
  -> rejection split
       reject source_preference_mismatch
       reject no_evidence
       reject share/percent title when query did not ask for share
  -> top 5 accepted candidates
```

This means "found" at Source Scouts means only: "candidate source cards were retrieved". It does not yet mean:

- the source has the requested geography;
- the source has the requested period;
- the source has extractable local data;
- the selected card is the best source-bound answer;
- the candidate passed coverage or methodology checks.

Observed bugs at this boundary:

- Source Scouts pass the raw query string into retrieval instead of using the normalized query plus structured `IntentFrame` fields.
- `IntentFrame.known_fields` are used later by Coverage, but not as first-class retrieval constraints.
- `ResearchDesignArtifact` is not materially used to shape Source Scouts queries; complex/research intent can collapse back to the same raw-query search.
- `HybridRetrievalResult.subgraph_context` is dropped when converting to `EvidenceBundleArtifact`; downstream agents cannot inspect the graph path that caused a source to appear.
- `why_matched` is generic (`lexical/dense retrieval score=...`) even when the candidate came from graph-first, graph-neighbour, or fusion. The real `fusion_modes`, ranks, raw scores, and graph path are not promoted to the handoff artifact.
- CKAN scout catches all exceptions and returns an empty list, hiding catalog/network/tool failure as "no CKAN candidate".
- Dense retrieval can be gated while the system still returns lexical/graph candidates as `retrieval_status="ok"`. The artifact should distinguish `complete`, `partial_dense_gated`, `partial_ckan_error`, etc.
- Graph-first query understanding is hardcoded alias/regex parsing. It improves recall for known concepts but can miss Russian morphology/synonyms outside the small map.

These are two different classes of Agent 3 problems:

**Agent 3 core/search logic is weak** because:

- It searches from raw `query` rather than from `RequestEnvelope + IntentFrame + ResearchDesignArtifact`.
- It does not generate multiple scout queries from LLM research expansion.
- It treats `IntentFrame.source_preferences` as the main structured constraint, while indicator/geography/period fields are not strongly applied during retrieval.
- It does not use Research Designer output to decide which source families/scout branches should run.
- It has narrow deterministic graph query understanding, so Russian morphology and non-golden synonyms are fragile.
- CKAN trigger logic is mostly regex/source-preference based, not derived from the structured intent/research plan.
- It does not explicitly separate complete retrieval from partial retrieval when dense/Qdrant/CKAN/graph paths are degraded.

**Agent 3 handoff/data passing is weak** because:

- It compresses rich `RetrievalCandidate` objects into loose dicts.
- It drops `HybridRetrievalResult.subgraph_context`.
- It does not preserve full per-channel retrieval provenance (`fusion_modes`, ranks, raw scores, graph path).
- It names candidates `selected_sources`, which sounds verified rather than "selected for coverage".
- It does not provide typed `SourceCandidate` / `RejectedSourceCandidate` contracts.
- It does not tell Agent 4 which intent fields each candidate matched or failed to match.

So the fix must address both:

```text
Agent 3 internal search behavior:
  better inputs
  better query expansion
  better routing across retrieval channels
  better partial/gated status handling

Agent 3 output contract:
  typed candidates
  richer provenance
  selected_for_coverage naming
  preserved graph context
```

Detailed implementation direction for Agent 3:

#### 1. Add typed scout contracts

Create or extend artifacts in `app/artifacts/workflow_artifacts.py`:

```python
class RetrievalChannelStatus(BaseModel):
    channel: Literal[
        "lexical_bm25",
        "dense_qdrant",
        "graph_first",
        "graph_expansion",
        "ckan_discovery",
    ]
    status: Literal["ok", "partial", "gated", "error", "skipped", "not_run"]
    detail: str | None = None
    candidate_count: int = 0


class SourceCandidate(BaseModel):
    candidate_id: str
    source_family: str
    card_id: str | None = None
    dataset_id: str | None = None
    resource_id: str | None = None
    title: str
    provenance_url: str | None = None

    retrieval_paths: list[str]
    fusion_score: float | None = None
    path_scores: dict[str, float] = Field(default_factory=dict)
    path_ranks: dict[str, int] = Field(default_factory=dict)

    evidence_terms: list[str] = Field(default_factory=list)
    matched_intent_fields: dict[str, Any] = Field(default_factory=dict)
    unmatched_intent_fields: list[str] = Field(default_factory=list)
    graph_context_ref: str | None = None
    graph_neighbour_card_ids: list[str] = Field(default_factory=list)

    why_selected_for_coverage: str
    retrieval_warnings: list[str] = Field(default_factory=list)


class RejectedSourceCandidate(SourceCandidate):
    rejection_reasons: list[str]
    rejection_stage: Literal["retrieval", "fusion", "pre_coverage"]
```

Then change `EvidenceBundleArtifact` from loose dicts to typed fields while keeping backwards aliases during migration:

```python
class EvidenceBundleArtifact(BaseModel):
    selected_for_coverage: list[SourceCandidate] = Field(default_factory=list)
    rejected_candidates: list[RejectedSourceCandidate] = Field(default_factory=list)
    retrieval_status: Literal["complete", "partial", "gated", "error", "no_candidate"]
    channel_statuses: list[RetrievalChannelStatus] = Field(default_factory=list)
    subgraph_context: dict[str, Any] | None = None

    # temporary compatibility only
    selected_sources: list[dict[str, Any]] = Field(default_factory=list)
    rejected_sources: list[dict[str, Any]] = Field(default_factory=list)
```

Migration rule: product code should read `selected_for_coverage`; old `selected_sources` exists only until UI/tests are migrated.

#### 2. Change Agent 3 input shape

Current:

```python
run_source_scouts(query: str, *, expected_sources: list[str], index_manifest_path: Path)
```

Replace with:

```python
class SourceScoutInput(BaseModel):
    run_id: str
    original_query_text: str
    normalized_query_text: str
    intent: IntentFrame
    research_design: ResearchDesignArtifact | None = None
    retrieval_policy: RetrievalPolicy
    index_manifest_path: Path


class RetrievalPolicy(BaseModel):
    max_candidates: int = 5
    allowed_source_families: list[str] = ["fedstat", "world_bank", "ckan"]
    required_source_families: list[str] = []
    use_lexical: bool = True
    use_dense: bool = True
    use_graph: bool = True
    use_ckan_discovery: bool = True
    timeout_seconds: int = 30
```

New function:

```python
def run_source_scouts(scout_input: SourceScoutInput) -> EvidenceBundleArtifact:
    ...
```

`_node_source_scouts()` should build this from state:

```text
RequestEnvelope / Phase2State query fields
IntentFrame
ResearchDesignArtifact
runtime retrieval policy
```

It should not pass only raw `state["query"]`.

#### 3. Generate scout queries from Agent 1 + Agent 2 artifacts

Add a helper in `app/workflow/nodes/scouts.py`:

```python
def build_scout_queries(input: SourceScoutInput) -> list[ScoutQuery]:
    ...
```

Expected output:

```python
class ScoutQuery(BaseModel):
    text: str
    purpose: Literal["primary", "indicator_code", "source_family", "comparison", "graph_concept"]
    source_family_hint: str | None = None
    intent_fields_used: list[str] = Field(default_factory=list)
```

Construction rules:

- Always include `normalized_query_text` as primary.
- Add indicator-oriented queries from `IntentFrame.known_fields["indicator"]`.
- Add geography/period terms from `IntentFrame.known_fields`.
- Add `ResearchDesignArtifact.indicators` / future `indicators_to_search`.
- Add `ResearchDesignArtifact.search_queries_for_scouts` when present.
- Add source-specific queries only when the user or research design suggests them, e.g. World Bank for cross-country annual macro indicators.
- Deduplicate queries and cap them by retrieval budget.

Example:

```text
Original query:
  "Сравни динамику ВВП России и Казахстана за 2015-2024"

ScoutQuery[0]:
  text="сравни динамику ввп россии и казахстана за 2015-2024"
  purpose="primary"

ScoutQuery[1]:
  text="GDP Russia Kazakhstan 2015 2024 World Bank NY.GDP.MKTP.CD"
  purpose="indicator_code"
  source_family_hint="world_bank"

ScoutQuery[2]:
  text="ВВП Россия Казахстан 2015 2024 Росстат"
  purpose="source_family"
  source_family_hint="fedstat"
```

#### 4. Run hybrid retrieval per scout query, then merge

Instead of one call:

```python
HybridRetriever.search(query, expected_sources=expected_sources, limit=5)
```

do:

```python
all_results = []
for scout_query in scout_queries:
    result = retriever.search(
        scout_query.text,
        expected_sources=scout_query.source_family_hint or policy.required_source_families,
        limit=policy.max_candidates,
    )
    all_results.append((scout_query, result))
```

Then merge candidates by stable identity:

```text
identity priority:
  source_family + dataset_id + resource_id
  source_family + card_id
  source_family + title normalized
```

For each merged candidate, accumulate:

```text
retrieval_paths
path_scores
path_ranks
evidence_terms
matched scout query purposes
matched intent fields
retrieval warnings
```

Then run a final ranking over merged candidates:

```text
rank score =
  fusion_score
  + intent_field_match_bonus
  + source_family_hypothesis_bonus
  + exact_indicator_code_bonus
  - unmatched_required_field_penalty
  - known_risk_penalty
```

Do not let this ranking assert coverage. It only chooses candidates for Agent 4 to verify.

#### 5. Preserve graph context

Current `HybridRetrievalResult.subgraph_context` is lost when Agent 3 converts candidates to dicts.

Fix:

- Serialize subgraph context into the `EvidenceBundleArtifact`.
- Give it a `graph_context_ref`, e.g. `subgraph-context-{run_id}.json`, if it is too large.
- For each `SourceCandidate`, attach:
  - `graph_context_ref`
  - `graph_neighbour_card_ids`
  - graph path evidence when available

Agent 4 does not need to use graph context for deterministic coverage, but Critic/Narrator/eval need it to explain why a source appeared and whether retrieval overfit occurred.

#### 6. Make channel statuses explicit

Agent 3 should never collapse partial retrieval into plain `ok`.

Status rules:

```text
retrieval_status="complete"
  lexical ok + dense ok + graph ok + ckan not_needed/ok

retrieval_status="partial"
  at least one channel ok, but dense/graph/ckan failed or gated

retrieval_status="gated"
  required index/credentials unavailable and no reliable fallback channel should be used

retrieval_status="error"
  unexpected scout failure

retrieval_status="no_candidate"
  channels ran, but no candidate survived rejection
```

Channel details should look like:

```json
[
  {"channel": "lexical_bm25", "status": "ok", "candidate_count": 12},
  {"channel": "dense_qdrant", "status": "gated", "detail": "query_embedding_gated", "candidate_count": 0},
  {"channel": "graph_first", "status": "ok", "candidate_count": 4},
  {"channel": "graph_expansion", "status": "skipped", "detail": "no_dense_seeds", "candidate_count": 0},
  {"channel": "ckan_discovery", "status": "not_run", "detail": "not indicated by intent", "candidate_count": 0}
]
```

#### 7. CKAN must report failure, not disappear

Current `_run_ckan_scout()` catches all exceptions and returns `[]`.

Replace with:

```python
class CkanScoutResult(BaseModel):
    status: Literal["ok", "not_run", "gated", "error"]
    candidates: list[SourceCandidate]
    error: str | None = None
```

If CKAN was required by intent or research design and fails, `retrieval_status` should be `partial` or `error`, not `ok/no_candidate`.

#### 8. Update Agent 4 to consume new handoff

`run_coverage_preview()` should change from:

```python
run_coverage_preview(evidence: EvidenceBundleArtifact, *, intent_fields: dict[str, Any])
```

to:

```python
run_coverage_preview(
    evidence: EvidenceBundleArtifact,
    *,
    intent: IntentFrame,
    research_design: ResearchDesignArtifact | None,
    live_llm_required: bool,
) -> list[CoverageReport]
```

Agent 4 should iterate:

```python
for candidate in evidence.selected_for_coverage:
    source_card = hydrate_source_card(candidate.card_id or candidate.dataset_id)
    ...
```

Coverage reports should include candidate provenance:

```python
CoverageReport.evidence["source_candidate_id"] = candidate.candidate_id
CoverageReport.evidence["retrieval_paths"] = candidate.retrieval_paths
CoverageReport.evidence["matched_intent_fields"] = candidate.matched_intent_fields
```

#### 9. Tests required

Add/replace tests:

```text
test_source_scouts_build_queries_from_intent_and_research_design
  proves ResearchDesignArtifact.search_queries_for_scouts affects retrieval calls

test_source_scouts_preserves_retrieval_paths_and_graph_context
  proves graph_first/graph_expansion evidence survives into EvidenceBundleArtifact

test_source_scouts_partial_status_when_dense_gated
  dense unavailable + lexical ok => retrieval_status partial, not plain ok

test_ckan_required_error_is_reported
  CKAN required by intent, adapter raises => channel_status error

test_coverage_consumes_selected_for_coverage_not_selected_sources
  Agent 4 reads typed SourceCandidate objects

test_coverage_reports_candidate_provenance
  CoverageReport.evidence includes source_candidate_id and retrieval_paths
```

Acceptance/eval should reject:

- `selected_sources` without `selected_for_coverage`;
- missing channel statuses;
- candidates with no retrieval provenance;
- retrieval_status `ok` when dense/ckan/graph required path failed;
- coverage status `ok` when all candidate reports are gated/skipped/no rows.

Target Source Scouts handoff:

```text
SourceScoutInput:
  run_id
  original_query_text
  normalized_query_text
  intent:
    concepts
    geographies
    periods
    source_preferences_from_user_only
  research_design:
    indicators
    dimensions
    hypotheses
  retrieval_policy:
    max_candidates
    required_families
    allow_ckan_discovery

SourceCandidate:
  candidate_id
  source_family
  card_id/dataset_id/resource_id
  title
  retrieval_paths:
    - lexical_bm25
    - dense_qdrant
    - graph_first
    - graph_neighbour
  fusion_score
  path_scores
  evidence_terms
  matched_intent_fields
  subgraph_context_ref
  retrieval_warnings
  is_selected_for_coverage: bool

EvidenceBundleArtifact:
  selected_for_coverage: list[SourceCandidate]
  rejected_candidates: list[SourceCandidate + rejection_reason]
  retrieval_status:
    complete | partial | gated | error | no_candidate
  component_statuses:
    lexical
    dense_qdrant
    graph_first
    graph_expansion
    ckan
```

After this handoff, only Agent 7 `Coverage & Schema` may say whether the candidate actually covers the requested slice. Source Scouts must not be treated as final proof that data exists.

### Agent 3 -> Agent 4 handoff: candidates, not data tables

Agent 4 `Coverage & Schema` should receive a list of candidate source cards from Agent 3, not a single source and not raw statistical tables.

Correct handoff shape:

```text
Agent 3 - Source Scouts
  output:
    EvidenceBundleArtifact:
      selected_for_coverage:
        - SourceCandidate
        - SourceCandidate
        - SourceCandidate
      rejected_candidates:
        - RejectedSourceCandidate
      retrieval_status
      retrieval_channel_statuses

Agent 4 - Coverage & Schema
  input:
    EvidenceBundleArtifact.selected_for_coverage[]
    IntentFrame.known_fields
  does:
    for each SourceCandidate:
      hydrate full source card metadata if needed
      route by source_family
      inspect actual coverage/schema via deterministic adapter
      optionally ask LLM to compare coverage maps/risks
  output:
    list[CoverageReport]
```

So yes: Agent 4 should receive "a bunch" of source candidates. But they are candidate metadata records selected for coverage, not verified datasets and not extracted rows. Agent 4 is the first stage that checks whether those candidates actually cover the requested slice.

Current implementation:

- Agent 3 returns `EvidenceBundleArtifact.selected_sources: list[dict]`.
- Agent 4 loops through `evidence.selected_sources`.
- Each dict is hydrated through `hydrate_source_card()` from `.local/dataagent/phase1/source-catalog.sqlite` when possible.
- Then Coverage routes by `source_family`:
  - `fedstat` -> `preview_fedstat_coverage`
  - `world_bank` -> `preview_world_bank_coverage`
  - `ckan` -> `preview_ckan_coverage`
- Agent 4 emits `list[CoverageReport]`.

Problems in the current handoff:

- `EvidenceBundleArtifact.selected_sources` is an untyped `list[dict[str, Any]]`; there is no strict `SourceCandidate` model.
- The field name `selected_sources` overstates confidence. It should be `selected_for_coverage`.
- Retrieval metadata is compressed too aggressively. Agent 4 does not receive full `retrieval_paths`, `fusion_ranks`, `raw_scores`, or `subgraph_context`.
- Agent 4 receives only `intent.known_fields`, not the full `IntentFrame` or `ResearchDesignArtifact`, so coverage cannot reason over ambiguity, derived metrics, comparison dimensions, or research hypotheses.
- `run_coverage_preview()` always sets graph-level `coverage_schema` status to `ok` if no exception occurs, even if every `CoverageReport` is `gated` or `skipped_with_reason`.
- FedStat and World Bank preview functions currently return `CoverageReport(status="ok")` after metadata/row inspection even when the requested filtered slice may have zero usable rows. They report `row_count` in evidence, but do not map empty coverage to `no_data`/`skipped_with_reason`.
- CKAN coverage only inspects promoted metadata and supported formats; it does not validate requested period/geography coverage at this stage. That is acceptable only if reported as limited metadata coverage, not full data coverage.
- The LLM coverage assessment has a no-response fallback: if credentials are missing or the LLM call fails, it returns deterministic reports as-is.

Required fix:

- Introduce typed `SourceCandidate` and `RejectedSourceCandidate`.
- Rename or alias `selected_sources` to `selected_for_coverage`.
- Carry retrieval provenance into coverage: channels, ranks, graph path, and why matched.
- Pass full `IntentFrame` plus relevant `ResearchDesignArtifact` into Agent 4.
- Agent 4 aggregate status must reflect report statuses:
  - all ok -> `ok`
  - some ok, some skipped/gated -> `partial`
  - none ok but candidates checked -> `no_covered_slice`
  - adapter/LLM unavailable -> explicit gated/error status
- Preview adapters must return non-ok status when the requested period/geography/indicator slice has zero rows.
- Coverage LLM failure must become explicit `llm_*` evidence/status in product mode, not silent deterministic continuation.

Detailed implementation direction for Agent 4:

#### 1. Define Agent 4 responsibility precisely

Agent 4 `Coverage & Schema` is not a retriever and not an extractor. It is a validator of candidate source cards.

It receives candidates from Agent 3 and answers these questions for each candidate:

```text
Does this source card map to a real adapter/source family?
Can the full source metadata be hydrated?
Is there a local/promoted resource or trusted adapter path?
Does the source contain the requested indicator/concept?
Does it contain the requested geography/countries?
Does it contain the requested period/range?
What unit/frequency/schema does it expose?
Are there missing values or unsupported formats?
Can extraction proceed, or should the user be asked for clarification?
```

It must not:

```text
create final user answers
invent data values
call extraction tools that export datasets
turn a retrieval candidate into passed outcome
hide adapter/LLM failure as ok
```

#### 2. Replace current function signature

Current:

```python
def run_coverage_preview(
    evidence: EvidenceBundleArtifact,
    *,
    intent_fields: dict[str, Any],
    live_llm_required: bool = True,
) -> list[CoverageReport]:
```

Problem: `intent_fields` is too small and the function reads `evidence.selected_sources` loose dicts.

Target:

```python
class CoverageInput(BaseModel):
    run_id: str
    evidence: EvidenceBundleArtifact
    intent: IntentFrame
    research_design: ResearchDesignArtifact | None = None
    coverage_policy: CoveragePolicy


class CoveragePolicy(BaseModel):
    require_indicator_match: bool = True
    require_geography_match: bool = True
    require_period_overlap: bool = True
    allow_partial_period_overlap: bool = False
    max_candidates_to_preview: int = 5
    live_llm_required: bool = True
    timeout_seconds: int = 30


def run_coverage_preview(input: CoverageInput) -> CoverageBundleArtifact:
    ...
```

`CoverageBundleArtifact` should group reports and aggregate status:

```python
class CoverageBundleArtifact(BaseModel):
    artifact_id: str
    reports: list[CoverageReport]
    aggregate_status: Literal[
        "ok",
        "partial",
        "needs_clarification",
        "no_covered_slice",
        "gated",
        "error",
    ]
    selected_report_ids_for_extraction: list[str] = Field(default_factory=list)
    rejected_report_ids: list[str] = Field(default_factory=list)
    coverage_summary: str | None = None
```

Migration option: if adding `CoverageBundleArtifact` is too large, keep `list[CoverageReport]` temporarily but add a helper:

```python
def summarize_coverage_reports(reports: list[CoverageReport]) -> CoverageSummary:
    ...
```

#### 3. Extend CoverageReport schema

Current `CoverageReport` is too generic:

```python
source_id
status
checks
available_periods
available_geographies
unit
frequency
evidence
gated_reason
```

Target additions:

```python
class CoverageReport(BaseModel):
    report_id: str
    source_candidate_id: str
    source_family: str
    source_id: str
    status: Literal[
        "ok",
        "partial",
        "needs_clarification",
        "no_matching_rows",
        "gated",
        "skipped_with_reason",
        "error",
    ]

    requested_indicator: str | None = None
    requested_geographies: list[str] = Field(default_factory=list)
    requested_periods: list[str] = Field(default_factory=list)

    indicator_match: Literal["exact", "alias", "semantic", "missing", "unknown"]
    geography_match: Literal["exact", "partial", "missing", "not_applicable", "unknown"]
    period_match: Literal["exact", "overlap", "missing", "not_applicable", "unknown"]

    available_periods: list[str] = Field(default_factory=list)
    available_geographies: list[str] = Field(default_factory=list)
    unit: str | None = None
    frequency: str | None = None
    row_count_after_filters: int | None = None
    missing_values_count: int | None = None

    extraction_ready: bool = False
    extraction_blockers: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)

    retrieval_provenance: dict[str, Any] = Field(default_factory=dict)
    adapter_evidence: dict[str, Any] = Field(default_factory=dict)
    llm_assessment: dict[str, Any] | None = None
```

Key rule: `status="ok"` requires enough evidence for extraction:

```text
source adapter supported
metadata/resource available
requested indicator matched or source is an acceptable indicator source
requested geography matched or not applicable
requested period matched/overlapped according to policy
row_count_after_filters > 0 when local data preview is available
no extraction blockers
```

If a local preview reads metadata but finds no rows for the requested slice, status must be:

```text
no_matching_rows
```

not `ok`.

#### 4. Hydration must be explicit and traceable

Current:

```python
source_card = hydrate_source_card(source_card)
```

This silently returns the lightweight card when lookup fails.

Target:

```python
class HydratedSourceCard(BaseModel):
    source_candidate_id: str
    source_card: dict[str, Any]
    hydration_status: Literal["full", "lightweight_only", "missing"]
    hydration_key: str | None
    catalog_path: str | None
    warnings: list[str] = Field(default_factory=list)
```

Agent 4 should record hydration status in every `CoverageReport`:

```python
adapter_evidence["hydration_status"] = hydration.hydration_status
adapter_evidence["hydration_warnings"] = hydration.warnings
```

If full metadata is required for an adapter and hydration fails, report:

```text
status="gated"
extraction_blockers=["source_card_hydration_failed"]
```

#### 5. Adapter-specific coverage rules

FedStat:

```text
input:
  SourceCandidate + full FedStat source card + IntentFrame

must check:
  local parquet path exists
  indicator filter matches actual indicator/name/code
  geography filter matches actual geography rows when requested
  period columns overlap requested periods
  row_count_after_filters > 0

status:
  ok -> requested slice has rows
  no_matching_rows -> parquet exists but filter returns zero rows
  gated -> required parquet/source file missing
  error -> unexpected adapter failure
```

World Bank:

```text
input:
  SourceCandidate + World Bank source card + countries/periods/indicator_id

must check:
  local parquet path exists
  indicator_id resolved from candidate or intent
  country aliases normalize to ISO/country ids
  period overlap exists
  aggregate rows excluded
  row_count_after_filters > 0

status:
  ok -> rows exist for requested countries/periods
  partial -> some requested countries/periods exist, some missing
  no_matching_rows -> source exists but requested slice empty
  gated/error as above
```

CKAN:

```text
input:
  SourceCandidate with package/resource metadata

must check:
  package metadata was promoted or can be promoted
  supported deterministic resource format exists (csv/csv.gz/parquet)
  resource count and selected resource ids are preserved
  period/geography coverage is unknown unless metadata/schema proves it

status:
  ok -> supported promoted resource exists and metadata sufficient for extraction
  partial -> supported resource exists but period/geography coverage unknown
  skipped_with_reason -> no supported deterministic resource
  gated/error -> package show/download metadata unavailable when required
```

CKAN should not pretend to know period/geography coverage from package title alone.

#### 6. LLM assessment is advisory and must not hide failures

Current `_llm_assess_coverage()`:

```python
if qwen_credential_gate() == gated_skip:
    return reports
except Exception:
    return reports
```

Target product behavior:

```text
If live_llm_required=True:
  LLM unavailable -> add llm_unavailable status/evidence and mark coverage bundle gated/partial.
  LLM timeout -> add llm_timeout.
  LLM error -> add llm_error.

If live_llm_required=False:
  allowed only in unit tests with mocked boundary, not product readiness.
```

LLM may enrich:

```text
best_slice
alternative_slices
quality_risks
ask_user flag
ask_user_reason
```

LLM must not override deterministic facts:

```text
cannot turn no_matching_rows into ok
cannot invent available periods/geographies
cannot remove adapter blockers
```

#### 7. Aggregate status for graph node

Current `_node_coverage_schema()` sets:

```python
status = "ok"
```

whenever `run_coverage_preview()` returns without exception.

Target aggregation:

```python
def aggregate_coverage_status(reports: list[CoverageReport]) -> str:
    if not reports:
        return "no_candidate"
    if any(r.status == "ok" for r in reports):
        if all(r.status == "ok" for r in reports):
            return "ok"
        return "partial"
    if any(r.status == "needs_clarification" for r in reports):
        return "needs_clarification"
    if all(r.status in ("gated", "error") for r in reports):
        return "gated"
    if all(r.status in ("no_matching_rows", "skipped_with_reason") for r in reports):
        return "no_covered_slice"
    return "partial"
```

Then state should carry:

```text
component_statuses["coverage_schema"] = aggregate_status
trace payload:
  report_count
  ok_count
  partial_count
  no_matching_rows_count
  gated_count
  selected_report_ids_for_extraction
```

#### 8. Agent 4 -> Agent 5 handoff

Agent 5 `Extraction Planner` should not receive all reports as a flat list and pick any `status == "ok"` without provenance.

Target handoff:

```text
CoverageBundleArtifact
  reports
  selected_report_ids_for_extraction
  aggregate_status

Agent 5 input:
  IntentFrame
  ResearchDesignArtifact
  CoverageBundleArtifact
```

Extraction Planner must only plan from reports where:

```text
status in ("ok", "partial" if policy allows)
extraction_ready == true
source_candidate_id exists
row_count_after_filters is None or > 0
```

If no extraction-ready report exists:

```text
ExtractionPlan.status = "skipped_with_reason" or "needs_clarification"
skip_reason = "no_extraction_ready_coverage"
```

#### 9. Tests required for Agent 4

Add/replace tests:

```text
test_coverage_consumes_typed_source_candidates
  Agent 4 reads selected_for_coverage and records source_candidate_id

test_fedstat_empty_filtered_slice_is_no_matching_rows
  local parquet exists but requested period/geography/indicator yields zero rows

test_world_bank_partial_country_period_coverage
  one requested country/year exists, another missing -> status partial

test_ckan_metadata_only_reports_unknown_period_geography
  CKAN supported format but no schema evidence -> partial, not full ok

test_coverage_aggregate_status_no_covered_slice
  all reports no_matching_rows/skipped -> component status no_covered_slice

test_coverage_llm_unavailable_is_explicit
  live_llm_required=True and Qwen gated -> llm_unavailable evidence/status, not silent pass

test_coverage_report_preserves_retrieval_provenance
  report.evidence includes source_candidate_id, retrieval_paths, fusion_score

test_extraction_planner_receives_only_extraction_ready_reports
  gated/no_matching_rows reports cannot produce status ok plan
```

Acceptance should reject:

- `coverage_schema` component status `ok` with zero ok reports.
- any `CoverageReport(status="ok")` with known `row_count_after_filters == 0`.
- missing `source_candidate_id` in coverage evidence.
- missing retrieval provenance in coverage reports.
- product-mode LLM coverage assessment failure without explicit `llm_*` status.

### Agent 5 necessity: planner vs redundant pass-through

Agent 5 `Extraction Planner` is only justified if it performs a different job from Agent 4.

Agent 4 answers:

```text
"Which candidate sources actually cover the user's requested slice?"
```

Agent 5 should answer:

```text
"Given the verified coverage reports, what deterministic extraction program should run?"
```

If Agent 4 already emits a fully extraction-ready report with adapter, resource, filters, and extraction policy, Agent 5 can be reduced to a deterministic compiler or removed as a separate LLM agent.

#### When Agent 5 is useful

Keep Agent 5 as a real planning agent only for cases where coverage validation is not enough to define a safe extraction:

```text
comparative query:
  choose two or more coverage reports
  align periods/geographies
  decide join keys
  choose output shape

derived metric:
  choose base indicators
  define formula policy
  decide normalization/index operation

multi-source research query:
  choose primary vs supporting sources
  decide whether to extract one table or multiple tables
  preserve source-bound limitations

CKAN resource package:
  choose resource_id among supported resources
  choose CSV/parquet parsing policy
  decide schema mapping into canonical columns
```

For simple direct lookup, Agent 5 should not be an LLM reasoning step. It can be a deterministic plan compiler:

```text
CoverageReport(extraction_ready=true)
  -> compile ExtractionPlan
  -> Deterministic Tools
```

#### When Agent 5 is redundant

Agent 5 is redundant if its output only copies:

```text
source_id from CoverageReport
filters from IntentFrame
operations = ["coverage_preview", "filter_rows", "export_dataset"]
```

That is the current risk. In the current implementation:

- `build_extraction_plan()` takes `IntentFrame + list[CoverageReport]`.
- It filters `ok_reports`.
- It picks a primary report.
- It returns one `ExtractionPlan`.
- It does not carry `source_candidate_id`, `coverage_report_id`, `source_family`, `adapter_name`, or full resource metadata.
- It may call LLM to choose operations, but on LLM failure it silently falls back to rule-based operations.
- Agent 6 then guesses source family from `source_id` string, which means Agent 5 did not pass enough operational data.

So right now Agent 5 is partially redundant and partially under-specified.

#### Target design option A: keep Agent 5 as a deterministic compiler for direct cases

For direct/simple cases:

```text
Agent 4 Coverage & Schema
  -> CoverageBundleArtifact(
       selected_report_ids_for_extraction=["coverage-1"],
       reports=[CoverageReport(... extraction_ready=true ...)]
     )

Agent 5 Extraction Plan Compiler
  -> ExtractionPlan(
       plan_id,
       source_candidate_id,
       coverage_report_id,
       source_family,
       adapter_name,
       dataset_id,
       resource_id,
       filters,
       operations=["filter_rows", "export_dataset"],
       output_columns,
       extraction_readiness_checked=true
     )
```

No LLM is needed in this path. The compiler should be deterministic and should fail closed if required fields are missing.

#### Target design option B: keep Agent 5 as LLM planner only for complex cases

For comparative/research/derived cases, Agent 5 may use LLM, but only to choose among already verified coverage reports and allowlisted operations.

```text
Agent 5 LLM input:
  IntentFrame
  ResearchDesignArtifact
  CoverageBundleArtifact:
    only extraction_ready reports
    deterministic coverage facts
  AllowedOperations:
    filter_rows
    join_indicators
    normalize_index
    export_dataset

Agent 5 LLM output:
  selected_report_ids
  operations from allowlist only
  join_keys from approved schema only
  formula_policy from approved operations only
  limitations
```

Then deterministic validation must compile the final `ExtractionPlan`. The LLM must not write SQL, invent columns, or select reports that Agent 4 did not mark extraction-ready.

#### Target ExtractionPlan schema

Current `ExtractionPlan` is too thin:

```python
class ExtractionPlan(BaseModel):
    artifact_id: str
    source_id: str | None
    status: WorkflowStatus
    operations: list[str]
    duckdb_sql: str | None
    filters: dict[str, Any]
    output_columns: list[str]
    skip_reason: str | None
```

Replace/extend with:

```python
class ExtractionStep(BaseModel):
    step_id: str
    operation: Literal[
        "filter_rows",
        "join_indicators",
        "normalize_index",
        "export_dataset",
    ]
    input_report_ids: list[str]
    parameters: dict[str, Any] = Field(default_factory=dict)


class ExtractionPlan(BaseModel):
    artifact_id: str
    status: Literal[
        "ok",
        "needs_clarification",
        "skipped_with_reason",
        "gated",
        "error",
    ]

    source_candidate_ids: list[str] = Field(default_factory=list)
    coverage_report_ids: list[str] = Field(default_factory=list)
    source_family: str | None = None
    adapter_name: str | None = None
    dataset_id: str | None = None
    resource_id: str | None = None

    steps: list[ExtractionStep] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    output_columns: list[str] = Field(default_factory=list)

    compile_mode: Literal["deterministic_direct", "llm_complex_then_validated"]
    validation_errors: list[str] = Field(default_factory=list)
    skip_reason: str | None = None
```

#### Agent 5 routing rule

```python
if intent.category == "simple" and len(extraction_ready_reports) == 1:
    plan = compile_direct_extraction_plan(...)
elif intent.category in ("comparative", "research", "derived_metric"):
    plan = build_complex_extraction_plan_with_llm_then_validate(...)
else:
    plan = compile_best_available_plan_or_needs_clarification(...)
```

#### Remove bad fallback behavior

Current `_llm_select_plan()` falls back silently:

```python
except Exception:
    return _select_operations(intent, ok_reports), _safe_filters_from_intent(intent)
```

Target:

- direct/simple deterministic compile does not need LLM and can proceed without LLM.
- complex LLM planner failure must produce explicit `llm_error` / `llm_timeout` / `llm_unavailable`.
- product mode must not silently downgrade complex planning to a rule-based substitute.

#### Agent 5 -> Agent 6 handoff

Agent 6 must not infer source family from `source_id`.

Current risk:

```python
_resolve_source_family(extraction_plan)
  guesses fedstat/world_bank/ckan from source_id string
```

Target:

```text
ExtractionPlan.source_family = "world_bank"
ExtractionPlan.adapter_name = "extract_world_bank_dataset"
ExtractionPlan.coverage_report_ids = [...]
ExtractionPlan.source_candidate_ids = [...]
ExtractionPlan.dataset_id/resource_id = explicit
```

Agent 6 should dispatch from explicit `adapter_name`, not regex guessing.

#### Tests required for Agent 5

```text
test_direct_case_compiles_plan_without_llm
  one extraction-ready CoverageReport -> deterministic ExtractionPlan

test_complex_case_uses_llm_but_only_allowlisted_operations
  comparative/derived query -> LLM plan validated against allowed operations

test_complex_llm_failure_is_explicit
  product mode LLM error -> ExtractionPlan(status="gated" or "error", skip_reason includes llm_error)

test_extraction_plan_carries_report_and_candidate_ids
  plan includes coverage_report_ids and source_candidate_ids

test_extraction_plan_carries_source_family_and_adapter
  Agent 6 can dispatch without source_id string guessing

test_no_ok_plan_from_non_extraction_ready_report
  no_matching_rows/gated/skipped reports cannot produce status ok
```

Decision recommendation:

```text
Do not keep Agent 5 as a vague LLM agent for every query.
Make it:
  deterministic compiler for simple/direct cases;
  bounded LLM planner only for complex/multi-source/derived cases;
  always validated before Agent 6.
```

### Re-check findings: Agent 4 -> Agent 5 data transfer

After re-reading the current code, the Agent 4 -> Agent 5 boundary has several additional concrete defects.

#### Current runtime boundary

```text
Agent 4 - Coverage & Schema
  app/workflow/graph.py::_node_coverage_schema
  calls run_coverage_preview(...)
  appends list[CoverageReport] to state["coverage_reports"]

Agent 5 - Extraction Planner
  app/workflow/graph.py::_node_extraction_planner
  reads state["coverage_reports"]
  calls build_extraction_plan(intent, coverage_reports, live_llm_required)
```

The actual handoff is only:

```python
intent: IntentFrame
coverage_reports: list[CoverageReport]
```

But the operational decision needs:

```text
source candidate identity
source family
adapter name
dataset/resource ids
hydrated source card reference
coverage report id
extraction readiness
row-count policy
retrieval provenance
selected report ids
```

Those fields are missing or hidden in loose `evidence` dicts.

#### Existing richer source-card model is bypassed

The repository already has richer candidate models in `app/artifacts/source_cards.py`:

```python
class SourceCandidateCard(BaseModel):
    source
    builder_source
    dataset_id
    resource_id
    title
    match_mode
    units
    geography
    period_coverage
    provenance_url
    local_paths
    api_endpoint
    availability
    quality
    dimensions
    frequency
    why_matched
    metadata

class EvidenceBundle(BaseModel):
    coverage_intent
    selected_candidates: list[SourceCandidateCard]
    rejected_candidates: list[RejectedCandidate]
```

But Phase 2 workflow currently uses a separate weaker `EvidenceBundleArtifact`:

```python
selected_sources: list[dict[str, Any]]
rejected_sources: list[dict[str, Any]]
```

and a weaker `CoverageReport`:

```python
source_id
status
available_periods
available_geographies
unit
frequency
evidence
```

Fix direction:

- Either reuse `SourceCandidateCard` directly in Phase 2 `EvidenceBundleArtifact`, or create a `WorkflowSourceCandidate` that explicitly wraps/links it.
- Do not invent a third unrelated candidate representation.
- Agent 3 output, Agent 4 input, CoverageReport provenance, and Agent 5 plan input must share one stable candidate id.

Recommended compatibility model:

```python
class WorkflowSourceCandidate(BaseModel):
    candidate_id: str
    source_card: SourceCandidateCard | None = None
    source_card_ref: str | None = None
    source_family: str
    dataset_id: str | None = None
    resource_id: str | None = None
    card_id: str | None = None
    retrieval_provenance: RetrievalProvenance
```

This lets the workflow preserve existing Phase 1 source-card structure while adding retrieval provenance from hybrid/graph RAG.

#### CoverageReport cannot currently prove extraction readiness

Current Agent 5 only checks:

```python
ok_reports = [r for r in coverage_reports if r.status == "ok"]
```

This is not enough. A report can be `ok` while still missing operational fields needed by Agent 6:

```text
no adapter_name
no source_family
no hydrated source card ref
no source_candidate_id
no resource_id for CKAN
no row_count_after_filters
no extraction_ready boolean
```

Fix direction:

```python
def is_extraction_ready(report: CoverageReport) -> bool:
    return (
        report.status in ("ok", "partial_allowed")
        and report.extraction_ready is True
        and report.source_candidate_id
        and report.source_family in ("fedstat", "world_bank", "ckan")
        and report.adapter_name
        and not report.extraction_blockers
        and (report.row_count_after_filters is None or report.row_count_after_filters > 0)
    )
```

Agent 5 must filter by `is_extraction_ready(report)`, not by `status == "ok"` alone.

#### Agent 5 primary report selection is too weak

Current `_select_primary_report()`:

```python
period_score = 1 if not requested_periods or requested_periods <= available_periods else 0
return (period_score, row_count)
```

Problems:

- It ignores geography match.
- It ignores indicator match.
- It ignores source family preference/research design.
- It ignores extraction blockers.
- It ignores candidate retrieval provenance.
- It can choose a report with larger `row_count` but wrong geography/indicator.
- It has no tie-breaker based on coverage quality or source trust.

Target scorer:

```python
def score_extraction_ready_report(report, intent, research_design) -> ExtractionReadinessScore:
    return ExtractionReadinessScore(
        indicator_score=...,
        geography_score=...,
        period_score=...,
        row_count_score=...,
        source_preference_score=...,
        retrieval_confidence_score=...,
        quality_penalty=...,
        blockers_penalty=...,
    )
```

It should produce an auditable score object, not just a tuple.

#### Agent 5 LLM prompt receives lossy coverage summaries

Current `_llm_select_plan()` sends only:

```python
source_id
status
available_periods[:5]
available_geographies[:5]
unit
llm_best_slice
llm_quality_risks
```

This loses:

```text
coverage report id
source candidate id
source family
adapter name
row_count_after_filters
indicator/geography/period match status
extraction blockers
resource ids
retrieval provenance
full requested fields
research design dimensions/hypotheses
```

Fix direction:

```python
coverage_summary = [
  {
    "coverage_report_id": report.report_id,
    "source_candidate_id": report.source_candidate_id,
    "source_family": report.source_family,
    "adapter_name": report.adapter_name,
    "status": report.status,
    "extraction_ready": report.extraction_ready,
    "indicator_match": report.indicator_match,
    "geography_match": report.geography_match,
    "period_match": report.period_match,
    "row_count_after_filters": report.row_count_after_filters,
    "extraction_blockers": report.extraction_blockers,
    "retrieval_paths": report.retrieval_provenance.get("retrieval_paths", []),
  }
]
```

For direct/simple cases, skip this LLM prompt entirely and compile deterministically.

#### Agent 5 merges filters incorrectly with Agent 6

Agent 5 returns filters, then Agent 6 does:

```python
filters = dict(extraction_plan.filters or {})
filters.update(intent.known_fields)
```

This can overwrite validated planner filters with raw/less-normalized intent fields after Agent 5 has already compiled the plan.

Fix direction:

- Agent 5 must produce final adapter-ready filters.
- Agent 6 must not merge `intent.known_fields` into filters.
- If Agent 6 needs original intent, pass it separately for trace only.
- Validate filter schema per adapter before dispatch.

Adapter filter schemas:

```python
class FedStatExtractionFilters(BaseModel):
    indicator: str | None
    geography: str | None
    periods: list[str]

class WorldBankExtractionFilters(BaseModel):
    indicator_id: str
    countries: list[str]
    periods: list[str]

class CkanExtractionFilters(BaseModel):
    resource_id: str
    columns: list[str] = []
    where: dict[str, Any] = {}
```

#### Agent 5 -> Agent 6 dispatch is currently string guessing

Current Agent 6:

```python
source_family = _resolve_source_family(extraction_plan)
```

This guesses from `source_id` and `operations`. That proves Agent 5 did not pass the actual dispatch key.

Fix direction:

```python
if not extraction_plan.adapter_name:
    return NoDataExplanationArtifact(... "missing_adapter_name")

dispatch = {
  "extract_fedstat_dataset": extract_fedstat_dataset,
  "extract_world_bank_dataset": extract_world_bank_dataset,
  "extract_ckan_dataset": extract_ckan_dataset,
}
tool = dispatch[extraction_plan.adapter_name]
```

Remove `_resolve_source_family()` from product path. Keep only as migration/test fallback if absolutely required, and mark non-jury.

#### Agent 4 -> Agent 5 target handoff

Target state fields:

```text
state["coverage_bundle"] = CoverageBundleArtifact
state["coverage_reports"] = coverage_bundle.reports  # temporary compatibility
```

`CoverageBundleArtifact`:

```python
artifact_id: str
reports: list[CoverageReport]
aggregate_status: str
selected_report_ids_for_extraction: list[str]
selected_candidate_ids_for_extraction: list[str]
coverage_decision_trace: list[dict[str, Any]]
```

Agent 5 input:

```python
class ExtractionPlannerInput(BaseModel):
    run_id: str
    intent: IntentFrame
    research_design: ResearchDesignArtifact | None
    coverage_bundle: CoverageBundleArtifact
    planner_policy: ExtractionPlannerPolicy
```

Agent 5 output:

```python
ExtractionPlan:
    coverage_report_ids
    source_candidate_ids
    source_family
    adapter_name
    adapter_filters
    steps
    compile_mode
```

#### Additional tests specifically for 4 -> 5

```text
test_planner_rejects_ok_report_without_extraction_ready
  CoverageReport(status="ok", extraction_ready=False) -> no ok plan

test_planner_uses_coverage_bundle_selected_report_ids
  if CoverageBundle selects report B, planner cannot pick report A just because row_count is larger

test_planner_scores_indicator_geography_period_not_row_count_only
  wrong geography with larger row_count loses to correct geography with smaller row_count

test_agent6_does_not_merge_raw_intent_into_plan_filters
  validated filters remain unchanged during deterministic tool dispatch

test_agent6_dispatches_by_adapter_name_not_source_id
  source_id ambiguous but adapter_name explicit -> correct extractor called

test_existing_source_candidate_card_is_preserved
  SourceCandidateCard.card_id/dataset_id/resource_id survives Agent 3 -> Agent 4 -> Agent 5
```

### Agent 6 extraction audit: what is actually extracted and what is wrong

Agent 6 `Deterministic Tools` is the first stage that should actually read/download data rows. It must not use LLM for numeric extraction. The LLM's role ends at planning/validation; numbers must come from deterministic source adapters.

Correct division:

```text
Agent 5 Extraction Planner
  decides/compiles:
    adapter_name
    source_family
    dataset_id/resource_id
    validated adapter filters
    extraction steps

Agent 6 Deterministic Tools
  executes exactly that plan:
    FedStat parquet/local archive
    World Bank parquet/local archive
    CKAN promoted CSV/CSV.GZ/Parquet resource
  outputs:
    DatasetArtifact with canonical rows
    ScriptArtifact that truly reproduces the extraction
    NoDataExplanationArtifact when extraction fails honestly
```

Agent 6 should not decide what source to use, should not rewrite filters from raw intent, and should not silently pick arbitrary resources.

#### Current Agent 5 -> Agent 6 handoff

Current Agent 6 reads:

```python
extraction_plan = state["extraction_plan"]
source_family = _resolve_source_family(extraction_plan)
filters = dict(extraction_plan.filters or {})
filters.update(intent.known_fields)
```

Then it dispatches by inferred `source_family`.

This handoff is unsafe:

- `ExtractionPlan` lacks explicit `source_family` and `adapter_name`.
- Agent 6 infers source family from `source_id` string or operation names.
- Agent 6 mutates plan filters by merging raw `intent.known_fields` after planning.
- Agent 6 does not receive a typed source card/hydrated resource reference from Agent 5.
- Agent 6 looks up source cards again by `source_id`, or invents minimal fallback source cards.

Required handoff:

```python
class ExtractionPlan(BaseModel):
    artifact_id: str
    source_family: Literal["fedstat", "world_bank", "ckan"]
    adapter_name: Literal[
        "extract_fedstat_dataset",
        "extract_world_bank_dataset",
        "extract_ckan_dataset",
    ]
    source_candidate_ids: list[str]
    coverage_report_ids: list[str]
    source_card_ref: str | None
    source_card: dict[str, Any] | None
    dataset_id: str
    resource_id: str | None
    adapter_filters: FedStatExtractionFilters | WorldBankExtractionFilters | CkanExtractionFilters
    steps: list[ExtractionStep]
```

Agent 6 must dispatch only from `adapter_name`.

#### Severe bug: World Bank workflow extraction wrapper is broken

Current Agent 6 wrapper:

```python
return _extract(
    source_card=source_card,
    filters=filters,
    output_dir=output_dir,
    artifact_id=artifact_id,
)
```

But `app.data.world_bank_adapter.extract_world_bank_dataset()` signature is:

```python
extract_world_bank_dataset(
    source_card,
    *,
    countries: list[str],
    periods: list[str],
    indicator_id: str,
    output_dir: Path,
    artifact_id: str,
)
```

So the workflow wrapper passes a non-existent `filters` parameter. That raises `TypeError`, is caught, and becomes:

```text
NoDataExplanationArtifact(rejection_reasons=["world_bank_extraction_error"])
```

This can turn valid World Bank cases into false `not_found`.

Fix:

```python
wb_filters = WorldBankExtractionFilters.model_validate(extraction_plan.adapter_filters)
return _extract(
    source_card=source_card,
    countries=wb_filters.countries,
    periods=wb_filters.periods,
    indicator_id=wb_filters.indicator_id,
    output_dir=output_dir,
    artifact_id=artifact_id,
)
```

Add test:

```text
test_agent6_world_bank_dispatch_uses_adapter_signature
  given ExtractionPlan(adapter_name="extract_world_bank_dataset", adapter_filters={countries, periods, indicator_id})
  deterministic tools calls WB adapter without filters=...
  returns DatasetArtifact, not NoDataExplanationArtifact
```

#### FedStat extraction can produce ok dataset with zero or irrelevant rows

Current FedStat adapter:

```python
filtered = _filter_rows(rows, indicator=indicator, geography=geography)
records = []
for row in filtered:
  for period in period_columns:
    records.append(...)
DatasetArtifact(status="ok", rows=len(records))
```

Problems:

- If filtered rows are empty, it still returns `DatasetArtifact(status="ok", rows=0)`.
- If period filter produces no period columns, it returns `rows=0` but status still `ok`.
- Missing values are included as records with `value=None`; for a direct numeric answer that may be unacceptable unless explicitly marked and handled downstream.
- `_filter_rows()` has a risky branch:
  ```python
  if indicator_matches or indicator_column:
      result = indicator_matches
  ```
  If there is no indicator column, indicator filtering may be skipped and unrelated rows can remain.
- It reads the full parquet table into memory via `parquet.read()` and `SELECT *`, which can pull more than necessary.

Fix:

```python
if not filtered:
    return NoDataExplanationArtifact(... rejection_reasons=["fedstat_no_matching_rows"])
if not period_columns:
    return NoDataExplanationArtifact(... rejection_reasons=["fedstat_no_matching_periods"])
if not records or all(record["value"] is None for record in records):
    return NoDataExplanationArtifact(... rejection_reasons=["fedstat_no_numeric_values"])
```

And change status behavior:

```text
DatasetArtifact(status="ok") only when rows > 0 and at least one non-null value exists.
```

For direct lookup, missing-value rows should not become the only final dataset. For research/comparison, they may be retained with quality flags if at least some values exist.

Also add adapter-level projection/filtering where possible:

```text
read only required columns when schema is known
filter period columns before row expansion
cap output rows according to ExtractionPlan row policy
```

Tests:

```text
test_fedstat_zero_filtered_rows_returns_no_data
test_fedstat_no_requested_periods_returns_no_data
test_fedstat_all_missing_values_not_ok_for_direct
test_fedstat_does_not_skip_indicator_filter_when_no_indicator_column_without_warning
```

#### World Bank adapter extracts correctly, but wrapper and empty-result status are wrong

Real adapter:

```python
rows = _load_rows(source_card)
filtered = _filter_rows(rows, country_codes, periods, indicator_id)
records = [...]
DatasetArtifact(status="ok", rows=len(records))
```

Problems:

- Workflow wrapper currently calls it incorrectly, as above.
- If filters produce zero records, adapter still returns `DatasetArtifact(status="ok", rows=0)`.
- `_load_rows()` reads the full parquet table into memory and then filters in Python.
- If `indicator_id` is missing/empty and rows contain multiple indicators, the filter may allow more data than intended.

Fix:

```python
if not indicator_id:
    return NoDataExplanationArtifact(... rejection_reasons=["world_bank_missing_indicator_id"])
if not filtered:
    return NoDataExplanationArtifact(... rejection_reasons=["world_bank_no_matching_rows"])
if all(row.get("value") is None for row in filtered):
    return NoDataExplanationArtifact(... rejection_reasons=["world_bank_no_numeric_values"])
```

Use DuckDB/PyArrow filtering/projection when possible:

```sql
SELECT indicator_id, indicator_name, country_id, country_name, date, value
FROM parquet
WHERE indicator_id = ?
  AND country_id IN (...)
  AND date IN (...)
```

Tests:

```text
test_world_bank_zero_filtered_rows_returns_no_data
test_world_bank_missing_indicator_id_fails_closed
test_world_bank_projection_does_not_return_unrequested_countries
test_agent6_world_bank_wrapper_does_not_catch_signature_error_as_not_found
```

#### CKAN extraction downloads entire resource and ignores filters

Current CKAN flow:

```python
promoted = promote_ckan_package(source_id)
resource_id = filters.get("resource_id") or first promoted resource
requests.get(resource.url)
parse whole CSV/Parquet
_to_canonical_records(records, ...)
DatasetArtifact(status="ok", rows=len(canonical_records))
```

Problems:

- If Agent 5 did not specify `resource_id`, Agent 6 silently picks the first promoted resource.
- `_parse_csv_text()` and `_parse_parquet_bytes()` ignore `filters`.
- `_to_canonical_records()` maps all rows into canonical records, even if indicator/geography/period filters were requested.
- It downloads the whole resource with no size cap or streaming policy.
- It returns `DatasetArtifact(status="ok", rows=0)` if canonical records are empty.
- It does not write parquet/manifest like FedStat/World Bank path; it only writes CSV.
- CKAN is allowed to use network because CKAN is a trusted catalog/resource adapter, but failures must be explicit. There should be no fake offline fallback.

Fix:

```python
class CkanExtractionFilters(BaseModel):
    resource_id: str
    indicator_id: str | None = None
    geographies: list[str] = []
    periods: list[str] = []
    columns: list[str] = []
    max_download_bytes: int = 50_000_000
```

Agent 6 must require `resource_id`:

```python
if not filters.resource_id:
    return NoDataExplanationArtifact(... rejection_reasons=["ckan_missing_resource_id"])
```

Parsing must apply filters:

```python
records = parse_resource(...)
records = apply_ckan_filters(records, filters)
if not records:
    return NoDataExplanationArtifact(... rejection_reasons=["ckan_no_matching_rows"])
```

Add resource size guards:

```text
check Content-Length when available
stream download or reject above max_download_bytes
do not load unbounded resources into memory
```

Export through shared `export_csv_parquet_manifest()` so manifest/parquet behavior is consistent.

Tests:

```text
test_ckan_missing_resource_id_fails_closed
test_ckan_filters_period_geography_indicator
test_ckan_empty_filtered_rows_returns_no_data
test_ckan_download_size_cap
test_ckan_exports_manifest_and_parquet_when_possible
```

#### Reproducibility script is currently a placeholder, not reproducible

`app/workflow/nodes/deterministic_tools.py::export_dataset_with_script()` writes a script that says:

```python
# NOTE: Replace the call below with the adapter matching your source family.
print("Extraction script ready. Configure source-specific parameters above.")
```

This is not a reproducibility script. It is a stub. It can falsely satisfy tests/UI that only check the `.py` path exists.

Fix:

- Remove this custom placeholder generator.
- Use `app.data.deterministic_tools.export_dataset_with_script()` with a real generated `script_text`, or implement real script generation per adapter.
- The generated script must call the exact adapter with the exact `source_card`/resource reference and validated filters from `ExtractionPlan`.
- The script should reproduce the same canonical dataset artifact, not just print instructions.

Script test:

```text
test_generated_script_executes_and_recreates_dataset
  run generated script in temp dir
  assert output CSV exists
  assert row count and key records match DatasetArtifact
```

#### Agent 6 should not use LLM, but must not compensate for missing Agent 5 reasoning

This is the important policy distinction:

```text
Correct:
  Agent 6 uses deterministic code to read rows and compute source-bound numeric outputs.

Incorrect:
  Agent 6 uses code heuristics to choose source family, resource, filters, or operation strategy because Agent 5 failed to plan.
```

So "it uses code instead of LLM" is a bug only for planning decisions, not for numeric extraction.

Allowed in Agent 6:

```text
open parquet
run DuckDB/PyArrow filters
download explicitly selected CKAN resource
parse CSV/parquet
export CSV/parquet/manifest
produce NoDataExplanationArtifact
```

Not allowed in Agent 6:

```text
guess source family from source_id
pick first CKAN resource when plan omitted resource_id
merge raw intent fields over validated filters
turn adapter exceptions into generic not_found without typed error reason
return ok dataset with zero rows/non-values
generate placeholder scripts
read unbounded full resources when plan requested a small slice
```

#### Agent 5 -> Agent 6 target interface

```python
class DeterministicToolInput(BaseModel):
    run_id: str
    extraction_plan: ExtractionPlan
    source_card: SourceCandidateCard | dict[str, Any]
    output_dir: Path


def run_deterministic_tools(input: DeterministicToolInput) -> DeterministicToolResult:
    ...
```

`DeterministicToolResult`:

```python
class DeterministicToolResult(BaseModel):
    status: Literal["ok", "not_found", "gated", "error", "skipped"]
    dataset_artifacts: list[DatasetArtifact] = []
    script_artifacts: list[ScriptArtifact] = []
    no_data_artifacts: list[NoDataExplanationArtifact] = []
    tool_calls: list[dict[str, Any]]
```

Dispatch:

```python
adapter = extraction_plan.adapter_name
filters = extraction_plan.adapter_filters
source_card = input.source_card

if adapter == "extract_fedstat_dataset":
    result = fedstat.extract_fedstat_dataset(source_card, filters=filters, ...)
elif adapter == "extract_world_bank_dataset":
    result = world_bank.extract_world_bank_dataset(
        source_card,
        countries=filters.countries,
        periods=filters.periods,
        indicator_id=filters.indicator_id,
        ...
    )
elif adapter == "extract_ckan_dataset":
    result = ckan.extract_ckan_dataset(
        promoted,
        resource_id=filters.resource_id,
        filters=filters.model_dump(),
        ...
    )
```

No source-family regex guessing. No intent merge. No first-resource default.

### Systemic status bug: `not_found` / NoData is used too late and too broadly

This is a cross-workflow bug.

The workflow currently allows `NoDataExplanationArtifact` to appear in Agent 6 for many situations:

```text
unsupported source family
adapter signature mismatch
adapter exception
missing source card
CKAN download failure
CKAN parse failure
resource not found
empty extracted rows
```

That is wrong because these cases are not the same.

#### Correct meaning of each stage

```text
Agent 3 Source Scouts
  "I found candidate source cards."
  Failure here:
    no_candidate
    retrieval_gated
    retrieval_error

Agent 4 Coverage & Schema
  "These candidates do / do not cover the requested slice."
  Failure here:
    no_covered_slice
    needs_clarification
    coverage_gated
    coverage_error

Agent 5 Extraction Planner
  "This is a validated extraction plan for an extraction-ready coverage report."
  Failure here:
    no_extraction_ready_report
    planner_llm_error
    invalid_plan
    unsupported_operation

Agent 6 Deterministic Tools
  "I executed the already validated extraction plan."
  Failure here:
    extraction_error
    source_unavailable_at_execution
    resource_download_failed
    parse_error
    empty_result_after_validated_plan
```

`not_found` should mean:

```text
The workflow searched/checked the appropriate trusted sources and established that the requested data is not available.
```

It should not mean:

```text
The adapter crashed.
The wrapper called the adapter with the wrong signature.
The planner forgot resource_id.
The local cache is missing.
The script guessed the wrong source family.
The network failed while downloading an already selected CKAN resource.
```

Those are implementation/runtime failures or gated states, not honest no-data outcomes.

#### Your intuition is correct, with one nuance

If Agent 4 and Agent 5 were implemented correctly, Agent 6 should almost never discover "no data" for ordinary direct cases.

Correct expectation:

```text
Agent 4:
  verified slice coverage
  verified resource availability
  verified extraction readiness

Agent 5:
  compiled exact adapter/resource/filters

Agent 6:
  executes and returns DatasetArtifact
```

If Agent 6 returns NoData often, it means one of these is broken:

- Agent 4 did not actually verify coverage/resource readiness.
- Agent 5 compiled an incomplete/incorrect plan.
- Agent 6 ignored/overrode the validated plan.
- The data/resource changed between coverage and extraction.
- Runtime infrastructure failed.

Only the last two are legitimate Agent 6 failure classes, and even then they should not become plain `not_found`.

#### Legitimate Agent 6 "no data" edge cases

Agent 6 may still produce a data-absence artifact only in narrow cases:

```text
source changed after coverage:
  coverage saw resource, extraction resource no longer available

time-sensitive CKAN/resource drift:
  package metadata changed between promotion and extraction

coverage was intentionally partial:
  Agent 4 allowed extraction despite unknown CKAN period/geography coverage
  extraction then proves zero matching rows

race/cache corruption:
  local parquet existed at coverage time but cannot be read at extraction time
```

But these should be typed as:

```text
stale_source
resource_drift
execution_no_matching_rows_after_partial_coverage
source_unavailable_at_execution
```

not generic `not_found`.

#### Required status taxonomy

Replace generic late `NoDataExplanationArtifact` use with typed artifacts/statuses:

```python
class WorkflowFailureArtifact(BaseModel):
    artifact_id: str
    stage: Literal[
        "retrieval",
        "coverage",
        "planning",
        "extraction",
        "finalization",
    ]
    failure_type: Literal[
        "no_candidate",
        "no_covered_slice",
        "needs_clarification",
        "llm_unavailable",
        "llm_timeout",
        "llm_error",
        "adapter_error",
        "invalid_plan",
        "source_unavailable_at_execution",
        "resource_download_failed",
        "parse_error",
        "resource_drift",
        "empty_result_after_partial_coverage",
    ]
    user_outcome_candidate: Literal[
        "needs_clarification",
        "not_found",
        "system_error",
        "retryable_error",
    ]
    checked_sources: list[dict[str, Any]] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False
```

Keep `NoDataExplanationArtifact` only for true source-bound no-data conclusions:

```text
coverage/no-data:
  trusted source checked
  requested slice absent
  not caused by adapter/runtime/plan error
```

#### Stage-specific mapping

```text
Agent 3 no candidates:
  internal status: no_candidate
  final outcome candidate: not_found only after Critic verifies search scope was adequate

Agent 4 no covered slice:
  internal status: no_covered_slice
  final outcome candidate: not_found if checked sources are sufficient

Agent 5 invalid/incomplete plan:
  internal status: invalid_plan
  final outcome candidate: system_error / gated, not not_found

Agent 6 adapter exception:
  internal status: adapter_error
  final outcome candidate: system_error / retryable_error, not not_found

Agent 6 download failure:
  internal status: resource_download_failed
  final outcome candidate: retryable_error, not not_found

Agent 6 zero rows after Agent 4 said extraction_ready:
  internal status: plan_coverage_mismatch
  final outcome candidate: system_error unless Agent 4 marked coverage partial/unknown
```

#### Agent 6 fix

Agent 6 should return:

```python
DeterministicToolResult(
    status="ok",
    dataset_artifacts=[...],
)
```

or:

```python
DeterministicToolResult(
    status="error",
    failure_artifact=WorkflowFailureArtifact(
        stage="extraction",
        failure_type="adapter_error",
        user_outcome_candidate="system_error",
    ),
)
```

It should not return `NoDataExplanationArtifact` for adapter exceptions or wrapper bugs.

For empty rows:

```python
if plan.coverage_mode == "verified_full" and rows == 0:
    failure_type = "plan_coverage_mismatch"
    user_outcome_candidate = "system_error"
elif plan.coverage_mode == "partial_or_unknown":
    failure_type = "empty_result_after_partial_coverage"
    user_outcome_candidate = "not_found"
```

#### Critic/final outcome fix

Final `not_found` must be assigned only after Critic verifies:

```text
the failure came from retrieval/coverage absence, not implementation failure
checked sources are adequate for the query
no required adapter/LLM/tool crashed
the system did not skip extraction due to invalid plan
```

If Agent 6 has `adapter_error`, `invalid_plan`, `signature_mismatch`, `llm_error`, or `source_unavailable_at_execution`, final response should be a gated/system-error style internal state and must fail acceptance readiness. It must not become user-facing `not_found`.

#### Tests required

```text
test_agent6_adapter_exception_is_system_error_not_not_found
  adapter raises -> WorkflowFailureArtifact(stage="extraction", failure_type="adapter_error")

test_agent6_world_bank_signature_bug_cannot_be_mapped_to_not_found
  wrong wrapper call is test-detected as implementation failure

test_empty_rows_after_verified_coverage_is_plan_coverage_mismatch
  Agent 4 said extraction_ready true, Agent 6 rows=0 -> system_error/internal failure

test_empty_rows_after_partial_ckan_coverage_can_be_not_found_candidate
  only when coverage mode was partial/unknown

test_final_not_found_requires_coverage_no_covered_slice
  final not_found cannot originate from adapter_error or invalid_plan

test_acceptance_fails_on_late_no_data_from_extraction_error
  golden passed case cannot be accepted as not_found when extraction failed
```

This bug explains why `not_found` appears all over the workflow: the system lacks a strict status taxonomy and uses NoData as a convenient bucket for runtime failures.

### Retrieval sources vs data sources: local corpus, Qdrant, graph, CKAN

Terminology must stay strict here. `local source-card corpus`, `Qdrant`, and `graph RAG` are not three separate authoritative data sources. They are retrieval channels over source-card metadata.

Current retrieval storage roles:

```text
local source-card corpus
  JSONL/source-card metadata loaded from the Phase 1 index manifest
  used for lexical BM25
  used to build the in-memory KnowledgeGraphStore
  contains metadata/cards, not the final statistical data table

Qdrant dense vector DB
  vector index over the same phase1_source_cards/source-card corpus
  used for semantic ANN search
  stores embeddings + payload for source cards
  does not replace the local corpus and does not itself prove extractable data exists

KnowledgeGraphStore / graph RAG
  graph derived from the same source-card metadata
  no separate graph database in current code
  graph_first maps deterministic query concepts to SourceCard ids
  graph_expansion expands from dense seed cards to neighbouring cards
  may fetch neighbour card payloads from Qdrant by card_id

CKAN bounded search
  external trusted catalog discovery channel
  only used when query/source preferences indicate CKAN/НЦСЭД/ЕМИСС/code-like lookup
```

So the correct Source Scouts behavior is hybrid, not either/or:

```text
Source Scouts
  -> lexical over local corpus
  -> dense search in Qdrant
  -> graph_first over KnowledgeGraphStore
  -> graph expansion from dense seeds
  -> optional CKAN package search
  -> fusion + rejection
```

This is expected for hybrid Graph RAG. The bug is not that local corpus, vector DB, and graph are all used. The bug is when the workflow describes them as if they were independent data sources or treats retrieval candidates as verified data.

Required naming fix:

- Use `retrieval_channels` for lexical, dense, graph_first, graph_expansion, ckan_discovery.
- Use `data_sources` only for systems/adapters that can actually provide rows: FedStat, World Bank, CKAN promoted resources, local parquet/cache.
- In artifacts, `selected_sources` should be renamed or clarified as `selected_for_coverage`.
- Carry per-channel status so partial retrieval is visible:
  - `lexical_status`
  - `qdrant_status`
  - `graph_status`
  - `ckan_status`

### Research Designer boundary: LLM-only planning before retrieval

For complex/non-direct requests, Agent 5 `Research Designer` should be an LLM planning step, not a database lookup step.

Correct boundary:

```text
Agent 5 - Research Designer
  input:
    RequestEnvelope
    SupervisorDecision
    IntentFrame
  does:
    LLM structured reasoning only
    expands the user's intent into search/research strategy
  must not:
    call Qdrant
    call CKAN
    call FedStat/World Bank adapters
    read golden expected source_id/outcome
  output:
    ResearchDesignArtifact:
      hypotheses
      indicators_to_search
      dimensions
      grouping_policy
      source_family_hypotheses
      search_queries_for_scouts
      assumptions
```

Current implementation:

- `_node_research_designer()` receives `IntentFrame`.
- It reads `.planning/phases/02-jury-mvp/golden-coverage-matrix.json` when `_case_id` exists and builds `matrix_hint`.
- `design_research()` sends `intent.query`, `intent.category`, `intent.known_fields`, `intent.source_preferences`, and optional `matrix_hint` to Qwen.
- It returns `ResearchDesignArtifact(hypotheses, dimensions, indicators, grouping_policy, assumptions)`.
- It does not query Qdrant, CKAN, FedStat, World Bank, or a local catalog DB.

Errors at this boundary:

- Reading `golden-coverage-matrix.json` makes Research Designer partially answer-key driven in acceptance mode.
- The artifact lacks explicit `search_queries_for_scouts`, `source_family_hypotheses`, and `required_coverage_fields`, so it is too weak as a handoff contract.
- The next node, `Source Scouts`, ignores `state["research_design"]` and searches only with raw `state["query"]` plus `intent.source_preferences`.
- Therefore the LLM expansion exists, but it does not reliably shape retrieval. Complex queries can collapse back into the same raw-query search path.

Required fix:

- Remove matrix hints from Research Designer runtime.
- Keep Research Designer LLM-only.
- Extend `ResearchDesignArtifact` with scout-facing fields.
- Change Source Scouts input from `(query, expected_sources)` to `(RequestEnvelope, IntentFrame, ResearchDesignArtifact, RetrievalPolicy)`.
- Add a contract test proving a complex query's ResearchDesignArtifact changes the generated retrieval/scout queries.

## Target Runtime Data Flow

Нужная цепочка должна быть такой:

```text
User query
  -> RequestEnvelope
       query_text
       locale/language
       user_context (optional, non-secret)
       runtime_options (timeouts, live/mock policy)
       no golden expected answer
  -> Supervisor
       decides route budget only
       direct | research | clarification | no_data_candidate
  -> Intent Analyst
       produces IntentFrame:
         category
         metric/concept candidates
         geography candidates
         period policy
         source preferences explicitly stated by user
         missing critical fields
         confidence + ambiguity reasons
  -> Research Designer
       only for research/comparative/derived cases
       produces ResearchDesignArtifact:
         hypotheses
         indicators needed
         dimensions
         join/formula policy
         assumptions
       must not receive golden expected source_id
  -> Source Scouts
       FedStat scout
       World Bank scout
       CKAN scout
       each scout receives IntentFrame + optional ResearchDesignArtifact
       each scout returns SourceCandidateCard-like selected/rejected evidence
       graph-aware retrieval may add SubgraphContext as context/evidence
       graph output is not itself proof of coverage or extractability
  -> Coverage & Schema
       deterministic adapter inspection first
       checks available periods/geographies/units/frequency/missing values
       returns CoverageReport per candidate
  -> Extraction Planner
       receives only IntentFrame + ResearchDesignArtifact + CoverageReports
       emits allowlisted operations and typed filters
       no arbitrary SQL from user/LLM
  -> Deterministic Tools
       executes source adapters
       emits DatasetArtifact + ScriptArtifact or NoDataExplanationArtifact
  -> Methodology Critic
       verifies data/source/methodology consistency
       can request repair or clarification
  -> Visualization
       builds chart/table spec only from DatasetArtifact
  -> Narrator
       produces user-facing message from artifacts
       numbers only from DatasetArtifact records/provenance
  -> WorkflowResponse
       final_outcome: passed | needs_clarification | not_found
       includes trace, sources, coverage, extraction, dataset/script, limitations
```

Eval should wrap this same path from outside:

```text
Golden case
  -> run normal user query without expected source_id/source_family hints
  -> compare WorkflowResponse to expected rubric
  -> fail if expected passed but response is not_found/needs_clarification without evidence
```

## Finding 1 - Golden Matrix Leaks Into Runtime

**Symptom:** Phase 2 code can behave differently when invoked by golden-case eval than when invoked by a real user.

**Evidence:**

- `WorkflowRunConfig` carries `case_id`; service copies it into internal `_case_id`.
- `graph.py` checks `_case_id`, loads `.planning/phases/02-jury-mvp/golden-coverage-matrix.json`, builds `matrix_hint`, and passes it to `design_research`.
- `state.py` explicitly adds `matrix_hint` into the Research Designer prompt as "Подсказка из матрицы покрытия".

**Why this likely happened:** the team tried to force all 20 golden cases to pass quickly. The golden matrix was originally useful as an external coverage plan, but then became part of the agent's thinking.

**Why this is bad:** the agent is no longer solving the user request. It is solving "user request + hidden answer key". Any success under this mode is not evidence that arbitrary jury queries work.

**How it should be implemented:**

- `case_id` may exist only in eval metadata, not inside `Phase2State`.
- `golden-coverage-matrix.json` may be used by acceptance scorer after a response is produced.
- Runtime may use source catalog, retrieval index, source cards, and deterministic adapters.
- Runtime must never use expected terminal outcome, expected adapter, expected source family, expected source id, or expected filters from golden fixtures.

**Fix direction:**

- Remove `_case_id` from `Phase2State`.
- Remove `matrix_hint` from `design_research`.
- Keep `case_id` only in `run_acceptance` result rows and artifact folder naming.
- Add a test that fails if `app/workflow/**` reads `golden-coverage-matrix.json` or `golden-cases.yaml`.

## Finding 2 - Acceptance Scoring Allows Empty `not_found` For Expected `passed`

**Symptom:** existing `.planning/phases/02-jury-mvp/phase2-golden-results.json` reports `unacceptable=0` while it contains 16 `not_found` outcomes, many with `sources_count=0`, `dataset_count=0`, `script_count=0`, and expected `passed`.

**Evidence:**

- `phase2-golden-results.json` summary: `passed=0`, `needs_clarification=4`, `not_found=16`, `unacceptable=0`.
- Many cases have `matrix_expected_terminal_outcome="passed"` and `final_outcome="not_found"` with no sources/datasets/scripts.
- `scripts/run_phase2_acceptance.py::_check_matrix_alignment` allows any valid terminal outcome when expected outcome is `passed`.

**Why this likely happened:** the acceptance bar was encoded as "avoid invalid statuses" instead of "meet the case-specific expected behavior". That made `not_found` a universal escape hatch.

**How it should be implemented:**

For each golden case:

- If expected is `passed`, `final_outcome` must be `passed`.
- If expected is `needs_clarification`, response must include specific clarification questions and no extraction.
- If expected is `not_found`, response must include checked sources, rejected sources, and rejection reasons.
- For `passed`, acceptance must require non-empty selected sources, coverage reports, at least one ok dataset when the request asks for data, script artifact, trace events, and source-bound citations.
- A `not_found` for expected `passed` can be acceptable only if the matrix explicitly allows an alternative and records the evidence reason. That exception must be rare and machine-readable.

**Fix direction:**

- Rewrite `_check_matrix_alignment` to treat `expected=passed, got=not_found` as failure by default.
- Add artifact-count and evidence-count checks to `_score_response`.
- Fail empty `not_found`: no checked sources or no rejection reasons must be unacceptable.
- Update demo readiness to depend on passed counts, not just `unacceptable=0`.

## Finding 3 - Product CLI Is Not Reproducible From Windows PowerShell

**Symptom:** `python scripts\run_phase2_acceptance.py --limit 3` fails with `ModuleNotFoundError: No module named 'app'`.

**Evidence:** direct run from repo root failed until `PYTHONPATH=.` was set.

**Why this matters:** if the primary verification command does not run in the user's shell, downstream agents will make local assumptions, skip the command, or produce stale evidence.

**How it should be implemented:**

- Either package the repo in editable mode, or make scripts add repo root to `sys.path` consistently.
- All docs should provide Windows-compatible and POSIX-compatible commands.
- CI/test commands should use the same import path as local scripts.

**Fix direction:**

- Add a small bootstrap at top of `scripts/run_phase2_acceptance.py`, or move it to `python -m scripts.run_phase2_acceptance`.
- Update README and Phase 2 docs with exact commands.

## Finding 4 - Acceptance Can Hang Without Bounded Component Timeouts

**Symptom:** `PYTHONPATH=.; python scripts\run_phase2_acceptance.py --limit 3` timed out after more than 180 seconds.

**Likely causes:**

- multiple live LLM calls per query: supervisor, intent analyst, research designer, coverage assessment, extraction planner, critic, narrator;
- dense retrieval can call query embeddings/Qdrant;
- CKAN scout can hit network;
- no per-node budget in `WorkflowRunConfig`.

**How it should be implemented:**

Each workflow run should carry explicit budgets:

```text
WorkflowRunConfig
  total_timeout_s
  node_timeout_s
  llm_timeout_s
  retrieval_timeout_s
  ckan_timeout_s
  qdrant_timeout_s
  max_llm_calls
  max_selected_sources
  max_rejected_sources
```

Each node should return a typed gate/failure artifact when budget is exceeded. The final response can be `not_found` or `needs_clarification` only if evidence supports it; otherwise verification should fail as `runtime_timeout`.

**Fix direction:**

- Add timeouts to config and pass them into Yandex, Qdrant, CKAN, and node execution.
- Acceptance runner should have per-case timeout and produce `run_timeout` unacceptable reason.
- Trace events should include duration and timeout reason.

## Finding 5 - Russian Query Handling Is Too Narrow, Not Encoding-Broken

**Symptom:** Russian strings are correctly encoded, but query understanding still depends on small handcrafted alias maps and synonyms.

**Evidence:**

- `query_understanding.py` has limited `CONCEPTS`, `_GEO_ALIASES`, and source aliases.
- `hybrid_retrieval.py` uses limited `_STOPWORDS`, `_SYNONYM_MAP`, and query phrase filters.
- This is okay as a retrieval helper, but risky as the main source of semantic robustness.

**Why this likely caused bad behavior:** Russian economic requests have morphology, abbreviations, mixed source names, and ambiguous concepts. A narrow alias list can overfit to the 20 golden cases while failing natural variations.

**How it should be implemented:**

Use a layered query understanding contract:

```text
Raw user text
  -> LanguageNormalizer
       lowercase/casefold
       ё/е policy
       punctuation and dash normalization
       Russian morphology/stemming where practical
       abbreviation expansion: РФ, Росстат, ЕМИСС, ИПЦ, ВВП, ППС
  -> Intent Analyst LLM
       structured JSON with confidence
       missing field detection
       candidate concepts, not single forced answer
  -> Deterministic Concept Resolver
       maps concepts to known catalog concepts and source families
       keeps alternatives with scores
  -> Source Scouts
```

The LLM should not directly choose a hidden golden source. It should produce structured intent candidates; deterministic resolvers and retrieval should ground them.

**Fix direction:**

- Add `QueryUnderstandingArtifact` before `IntentFrame`, or expand `IntentFrame` with normalized query, concept candidates, confidence, and alternatives.
- Add tests with Russian paraphrases outside the 20 golden cases.
- Separate "source preference explicitly stated by user" from "source family guessed by system".

## Finding 5A - Graph RAG Helps Recall But Can Hide Semantic Overfit

**Symptom:** graph-aware retrieval introduces `graph_first` and graph expansion, but the graph is built from the same source-card metadata and the same narrow query understanding aliases.

**Current implementation shape:**

- `query_understanding.py` parses concepts, geographies, years, and source families.
- `graph_store.py` builds an in-memory SQLite graph with SourceCard, Indicator, Dataset, Provider, Unit, Geography, Period, Resource, Concept, and Alias nodes.
- `HybridRetriever.search()` fuses lexical, dense, graph-first, and graph-neighbour candidates with RRF.
- `SubgraphContext` can be passed upstream as structured context.

**Why this matters:** Graph RAG can improve recall for semantically adjacent cards, but it can also amplify bad aliases or weak concepts. If "ВВП" maps too broadly, graph expansion can return plausible-but-wrong GDP-adjacent cards. If source preference is treated as expected source instead of user-stated preference, graph filtering can reject useful alternatives too early.

**How it should be implemented:**

Graph RAG should be treated as retrieval evidence:

```text
Graph candidate
  -> SourceCandidateArtifact
  -> CoverageReport
  -> ExtractionPlan
  -> DatasetArtifact or NoDataExplanationArtifact
```

It should not produce terminal decisions directly. A graph neighbour is only "interesting", not "correct", until deterministic coverage and extraction confirm it.

**Fix direction:**

- Include `retrieval_path` / `fusion_modes` / `subgraph_context` in source candidate evidence so downstream agents can see why a card appeared.
- Add exact-source and extraction-ready top-k retrieval metrics for `hybrid_graph`, not just source-family hits.
- Add paraphrase tests where graph-first should help, and adversarial tests where graph expansion must not over-select broad period/geography/unit neighbours.
- Update `graph_store.py` documentation if needed: current code uses in-memory SQLite metadata graph, not a separate graph embedding collection.

## Finding 6 - Agents Are Nodes, But Their Interfaces Are Too Implicit

**Symptom:** The graph names agents, but many handoffs are plain dicts inside `Phase2State`, and downstream nodes infer meaning from ad hoc fields.

**Examples:**

- Scouts return selected/rejected source dicts, not a stricter `SourceCandidateArtifact`.
- Coverage receives `intent_fields` from `IntentFrame.known_fields`, which may lack normalized countries/periods/indicator IDs.
- Extraction planner picks primary report by source_id and available periods, then deterministic tools infer source family from `source_id` string.
- `_resolve_source_family` uses string heuristics like uppercase/dot patterns.

**How it should be implemented:**

Each agent handoff should have an explicit contract:

```text
Intent Analyst -> IntentFrame
  normalized_query
  category
  concepts[]
  geographies[]
  periods[]
  source_preferences_from_user[]
  missing_fields[]
  ambiguity_reasons[]

Research Designer -> ResearchDesignArtifact
  required_indicators[]
  dimensions[]
  formulas[]
  join_keys[]
  assumptions[]

Source Scout -> SourceCandidateArtifact[]
  source_family
  source_id
  card_id
  indicator_id
  title
  match_mode
  retrieval_path
  fusion_modes
  subgraph_context_id
  confidence
  provenance_url
  coverage_hints
  extraction_readiness
  rejection_reasons[]

Coverage -> CoverageReport[]
  source_family
  source_id
  requested_filters
  available_periods
  available_geographies
  unit
  frequency
  status
  reason

Extraction Planner -> ExtractionPlan
  source_family
  source_id
  adapter_name
  typed_filters
  operations
  formula/join plan if needed
```

**Fix direction:**

- Add `source_family` and `adapter_name` directly to `ExtractionPlan`.
- Stop inferring source family from string patterns.
- Replace generic selected source dicts with Pydantic artifacts or typed models.
- Add contract tests that create each artifact and pass it to the next node without golden fixtures.

## Finding 7 - Offline/No-Response LLM Fallbacks Are A Product Bug

**Symptom:** Phase 2 accumulated many workarounds whose purpose is to keep the workflow "working" when the LLM is unavailable, offline, missing credentials, or not responding. This is the wrong product behavior.

Examples already visible in the codebase:

- `WorkflowRunConfig.live_llm_required=False` lets callers request a non-live path.
- `app/workflow/run_graph.py` exposes `--no-live-llm` and describes deterministic fallback for tests.
- `app/workflow/service.py::continue_user_query` merges clarification manually if LLM re-analysis fails.
- `app/workflow/nodes/coverage.py` returns deterministic reports as-is when LLM assessment fails.
- `app/workflow/nodes/extraction_planner.py` falls back to rule-based operation/filter selection on LLM error.
- `app/workflow/nodes/narrator.py` still contains test-only fallback scaffolding and message markers.
- Tests still normalize the idea that `live_llm_required=False` can return terminal responses in some service paths.

**Why this is bad:** the target product requires real Yandex/Qwen calls for Supervisor, Intent Analyst, Research Designer, Coverage assessment where used, Extraction Planner reasoning, Methodology Critic, and Narrator. If the LLM is unavailable, the system must not silently continue with keyword/rule/manual substitutes and must not produce a jury-ready response.

This is not a useful offline feature. It hides integration failures and encourages agents to build around no-internet/no-response behavior instead of fixing the live path.

**How it should be implemented:**

```text
RuntimeMode:
  LIVE_JURY
    requires Qwen credentials
    requires embedding/Qdrant readiness
    requires network/API response within timeout
    no offline or no-response fallback
    LLM failure -> explicit gated/error artifact, not terminal success
  UNIT_TEST
    may mock YandexAIStudioClient.structured_chat at test boundary only
    verifies contracts and routing
```

There should be no product/runtime mode that says "LLM unavailable, keep going with local heuristics". Unit tests can mock the LLM dependency, but runtime code must not contain fake LLM behavior.

**Fix direction:**

- Remove `live_llm_required=False` as a product/runtime path. If retained for tests, keep it outside product service entrypoints or make it raise immediately.
- Remove `--no-live-llm` from product workflow CLI, or mark it as unit-test-only and ensure it cannot generate acceptance/readiness artifacts.
- Delete/manual-fail all no-response fallbacks in workflow nodes:
  - no manual clarification merge when LLM re-analysis fails;
  - no rule-based extraction planner fallback after Qwen failure;
  - no silent coverage "LLM failed, continue anyway" path for product mode;
  - no narrator fallback response.
- Replace these with explicit `llm_unavailable`, `llm_timeout`, or `llm_error` component status and trace evidence.
- Acceptance/demo readiness must fail if any LLM node used offline fallback, no-response fallback, or skipped live model execution.
- Tests should mock the Yandex client directly and assert the runtime called it, not ask product code to run "without LLM".

## Finding 8 - Trace Exists, But It Is Not Strong Enough As Evidence

**Symptom:** trace count can be 0 or 1 in `phase2-golden-results.json`, yet the result is still acceptable.

**How it should be implemented:**

For a `passed` response, trace should contain at least:

```text
supervisor
intent_analyst
source_scouts
coverage_schema
extraction_planner
deterministic_tools
critic
narrator
```

For `needs_clarification`:

```text
supervisor
intent_analyst
clarification decision with missing fields
```

For `not_found`:

```text
supervisor
intent_analyst
source_scouts
coverage_schema or bounded search evidence
not_found explanation
```

**Fix direction:**

- Acceptance should check required trace states by final outcome.
- Trace events should carry node input summary, output artifact id, decision, duration, and warnings.
- UI should render trace from the same `WorkflowResponse`, not from separate debug-only artifacts.

### UI trace must be a human reasoning trace, not raw technical logs

Current UI code:

```text
app/ui/streamlit_app.py::_render_trace_events
  -> st.json(event.model_dump())
```

Current `TraceEvent` contains technical fields:

```text
state
agent
input_summary
tool_calls
output_artifact
decision
warnings
payload
duration_ms
```

This is useful for debugging, but it is not the trace the user should read.

The UI should show a human-facing reasoning/search trace:

```text
1. Понял запрос как поиск показателя ВВП России за 2024 год.
2. Сначала проверил локальный каталог источников и нашел карточку Росстата.
3. Проверил покрытие: источник содержит показатель, но период 2024 пока неполный.
4. Поэтому дополнительно проверил World Bank как альтернативный источник.
5. World Bank содержит сопоставимый показатель за нужный период.
6. Извлек строки за 2024 год, проверил единицы измерения и provenance.
7. Критик подтвердил, что данные соответствуют запросу.
8. Сформировал краткий ответ и приложил источник.
```

It should not show as the main trace:

- HTTP method names;
- raw GET/POST details;
- API payload JSON;
- raw SQL unless user opens debug details;
- stack traces;
- internal file paths;
- full tool call dumps;
- embedding/vector internals;
- graph/Qdrant payloads.

Those details may remain available in a collapsed developer/debug section, but the default product trace should explain decisions in plain language.

Target structure:

```python
class UserTraceStep(BaseModel):
    step_id: str
    order: int
    agent: str
    title: str
    message: str
    decision: str
    evidence_refs: list[str]
    status: Literal["ok", "warning", "skipped", "error"]
    user_relevant_details: list[str]
```

`WorkflowResponse` should include:

```python
user_trace: list[UserTraceStep]
trace_events: list[TraceEvent]  # debug/internal
```

Agent responsibilities:

```text
Source Scouts:
  "Проверил локальный каталог, Qdrant и graph RAG; выбрал такие-то источники, потому что..."

Coverage & Schema:
  "Источник содержит нужный период/географию/показатель" or
  "Источник отклонен, потому что не покрывает нужный период"

Extraction Planner / Deterministic Tools:
  "Извлек такие-то строки из такого-то ресурса; получил N строк"

Critic:
  "Проверил соответствие данных запросу; подтвердил/не подтвердил"

Data Analyst:
  "Для этого запроса нужен точный ответ / сравнение / тренд; рассчитал..."

Narrator:
  "Собрал ответ из проверенных данных и источников"
```

Fix direction:

- Keep `TraceEvent` for internal audit/eval.
- Add `UserTraceStep` or `PublicTraceStep`.
- Add a trace projection layer:

```text
TraceEvent[] + artifacts -> UserTraceStep[]
```

- Render `user_trace` by default in Streamlit as readable timeline/cards.
- Put raw `trace_events` JSON behind "Debug trace" collapsed expander.
- Do not expose raw payloads with request bodies, API calls, source-card internals, or stack traces by default.
- Ensure user-facing trace is source-bound and honest: if a source was rejected, say why in human terms.

Tests to add:

```text
test_public_trace_hides_raw_tool_payloads
test_public_trace_mentions_selected_and_rejected_sources
test_public_trace_explains_search_expansion_after_insufficient_source
test_streamlit_renders_user_trace_before_debug_trace
test_public_trace_contains_agent_decision_messages_for_passed_response
```

### Chat response layout: reasoning trace first, then final answer

The user-facing trace should be rendered directly inside the chat response, not as a separate unrelated debug panel.

Target chat layout:

```text
Ход поиска и анализа
1. Понял запрос как ...
2. Проверил источник ...
3. В первом источнике не хватило ...
4. Расширил поиск на ...
5. Извлек данные ...
6. Проверил соответствие запросу ...

---

Итоговый ответ
...

Источники
...

Артефакты
...

График / таблица
...
```

Important UI rule:

```text
Do not split the main product experience into "answer" in one place and "reasoning/trace" somewhere else.
```

The user should see the reasoning trace first, then a small divider line, then the final answer. This makes the product feel like an analytical agent, not a black-box search result.

The raw technical trace can still exist, but only under a collapsed developer/debug expander:

```text
Debug trace
  raw TraceEvent JSON
  tool calls
  payloads
  durations
```

Target `WorkflowResponse` shape:

```python
class WorkflowResponse(BaseModel):
    user_trace: list[UserTraceStep]
    message: str
    answer_blocks: list[dict[str, Any]]
    citations: list[Citation]
    dataset_artifacts: list[DatasetArtifact]
    script_artifacts: list[ScriptArtifact]
    visualizations: list[VisualizationSpec]
    trace_events: list[TraceEvent]  # debug-only
```

Target Streamlit render order:

```text
_render_chat_response(response):
  _render_user_trace_inline(response.user_trace)
  st.divider()
  _render_final_answer(response.message, response.answer_blocks)
  _render_sources(response.citations, response.selected_sources)
  _render_artifacts(response.dataset_artifacts, response.script_artifacts)
  _render_visualizations(response.visualizations)
  _render_limitations_and_feedback(response)
  _render_debug_trace_collapsed(response.trace_events)
```

Source/artifact/chart sections should be below the final answer because they support the conclusion. They should not interrupt the reasoning trace.

Fix direction:

- Add `user_trace` to `WorkflowResponse`.
- Change `_render_workflow_response()` in `app/ui/streamlit_app.py` so the first visible block is the public reasoning trace.
- Use a small divider before the final answer.
- Move raw `trace_events` JSON to a collapsed "Debug trace" expander.
- Keep sources, artifacts, downloads, and visualization under the final answer.
- Ensure `Agent 9 Narrator / Response Composer` gets `user_trace` from the trace projection layer and composes the chat response around it.

Tests to add:

```text
test_chat_response_renders_user_trace_before_answer
test_chat_response_includes_divider_between_trace_and_answer
test_sources_artifacts_visualization_render_below_final_answer
test_raw_trace_events_are_debug_only
```

## Post-Extraction Stage - What Happens After Correct Data Was Extracted

At this point the workflow should already have:

```text
Agent 1 Request Intake / Query Normalizer
  -> RequestEnvelope + QueryNormalizationReport

Agent 2 Intent Analyst
  -> IntentFrame

Agent 3 Research Designer
  -> ResearchDesignArtifact

Agent 4 Source Scouts
  -> EvidenceBundleArtifact with typed source candidates

Agent 5 Coverage & Schema
  -> CoverageBundleArtifact with extraction-ready coverage reports

Agent 6 Extraction Planner
  -> ExtractionPlan

Agent 7 Deterministic Tools
  -> DatasetArtifact + ScriptArtifact
```

The next stages are not allowed to search again, repair extraction silently, invent numbers, or convert internal errors into `not_found`.

The correct post-extraction chain should be:

```text
Agent 8 Methodology Critic
  input:
    RequestEnvelope
    IntentFrame
    ResearchDesignArtifact
    EvidenceBundleArtifact
    CoverageBundleArtifact
    ExtractionPlan
    DeterministicToolResult
    DatasetArtifact[]
    ScriptArtifact[]
    WorkflowFailureArtifact[]
    TraceEvent[]
  output:
    CritiqueReport
    FinalOutcomeDecision

Agent 9 Visualization Builder
  input:
    FinalOutcomeDecision
    DatasetArtifact[]
    IntentFrame
    ExtractionPlan
  output:
    VisualizationSpec[]

Agent 10 Narrator / Response Composer
  input:
    RequestEnvelope
    IntentFrame
    CritiqueReport
    FinalOutcomeDecision
    DatasetArtifact[]
    ScriptArtifact[]
    VisualizationSpec[]
    source/citation ledger
    TraceEvent[]
  output:
    WorkflowResponse
```

### Agent 8 Methodology Critic - current bug

Current code:

- `app/workflow/service.py::_finalize_state` calls `run_methodology_critic`, then `derive_final_outcome`.
- `app/workflow/nodes/critic.py::derive_final_outcome` maps multiple internal failures to `not_found`.
- If the critic verdict is `needs_repair` or unknown, the final outcome becomes `not_found`.
- If coverage is not "all ok", if there is no ok dataset, or if provenance is missing, `derive_final_outcome` returns `not_found`.
- `_coverage_all_ok()` requires every coverage report to be `ok`, even if Agent 5/6 selected one valid extraction-ready report and the other reports are rejected alternatives.

This is wrong after successful extraction.

If Agent 7 has produced correct `DatasetArtifact` rows with provenance, the critic's job is:

- verify that the extracted dataset answers the original normalized request;
- verify that all numeric values are source-bound;
- verify that provenance points to the source used by the extraction plan;
- verify that units, geography, periods, and indicator match the intent;
- decide whether the answer can be `passed`, `passed_with_warnings`, `needs_clarification`, `not_found`, or `system_error`.

It must not use `not_found` as a bucket for:

- invalid extraction plan;
- adapter exception;
- missing script file;
- narrator failure;
- LLM failure;
- source-card mismatch;
- internal status mismatch;
- "some unselected coverage reports were not ok".

### Agent 8 target structures

Add a separate final decision object instead of returning only a string:

```python
class FinalOutcomeDecision(BaseModel):
    decision_id: str
    terminal_outcome: Literal[
        "passed",
        "needs_clarification",
        "not_found",
        "system_error",
        "gated",
    ]
    confidence: float
    based_on_dataset_artifact_ids: list[str]
    based_on_coverage_report_ids: list[str]
    based_on_extraction_plan_id: str | None
    blocking_failures: list[WorkflowFailureArtifact]
    warnings: list[str]
    user_visible_limitations: list[str]
    internal_repair_plan: list[str]
```

`CritiqueReport` should stay as the methodological assessment, but `FinalOutcomeDecision` should be the authoritative status mapping.

Required critic checks:

```text
selected coverage reports extraction_ready == true
selected extraction plan status == ok
dataset status == ok
dataset rows > 0
dataset source_id matches selected source candidate / coverage report
dataset provenance contains concrete source adapter/resource evidence
dataset columns satisfy requested indicator/geography/period/unit fields
script artifact exists and reproduces the same adapter call
no WorkflowFailureArtifact with terminal severity exists
```

Coverage should not be checked as "all reports ok". It should be checked as:

```text
all selected_report_ids are ok/extraction_ready
unselected reports may be rejected/partial/not_found if their rejection reasons are preserved
at least one selected report must cover each required request dimension
```

### Agent 8 fix direction

- Replace `_coverage_all_ok(coverage_reports)` with selection-aware validation:

```text
CoverageBundleArtifact.selected_report_ids
  -> only these reports are required to be extraction_ready

CoverageBundleArtifact.rejected_report_ids
  -> must have reasons, but do not block passed outcome
```

- `derive_final_outcome()` must not return `not_found` for `needs_repair`, `unknown`, missing script, missing provenance, adapter failure, or narrator failure.
- Add `system_error` or `gated` as internal terminal states for product readiness. If the public API cannot expose them yet, acceptance must still fail and the UI should show "internal workflow error" rather than "data not found".
- If dataset rows exist but critic finds unit/geography/period mismatch, return `needs_repair`/`system_error`, not `not_found`.
- If dataset rows exist and match the request, final outcome should be `passed` even if other candidate sources were rejected.
- If all selected trusted sources were checked and truly do not contain the requested slice, only then use `not_found`.

Tests to add:

```text
test_final_pass_allows_rejected_unselected_candidates
test_critic_needs_repair_does_not_become_not_found
test_missing_provenance_is_system_error_not_not_found
test_adapter_failure_after_selected_plan_is_system_error
test_pass_requires_dataset_matches_selected_coverage_report
test_not_found_requires_no_extraction_ready_selected_reports
```

### Agent 8 repair routing - do not rerun the whole workflow by default

The Methodology Critic is a post-extraction validator, not a second search agent.

It should answer:

```text
Do the extracted rows answer the normalized user request?
Are numbers source-bound?
Do dataset provenance, coverage report, extraction plan, and selected source candidate all refer to the same source?
Are period/geography/indicator/unit aligned with IntentFrame?
Is the issue user ambiguity, source absence, planning bug, extraction bug, or presentation bug?
```

If the data is good:

```text
Agent 8 -> FinalOutcomeDecision(passed)
        -> Agent 9 Visualization Builder
        -> Agent 10 Narrator / Response Composer
```

If the data is bad, the critic must route repair to the smallest responsible prior stage, not restart the entire workflow blindly:

```text
problem: extracted rows answer a different geography/period/indicator
route_to: Agent 6 Extraction Planner or Agent 7 Deterministic Tools
reason: selected source may be correct, but filters/adapter execution are wrong

problem: selected coverage report was not actually extraction_ready
route_to: Agent 5 Coverage & Schema
reason: source validation allowed an unextractable or mismatched slice

problem: source candidate family is wrong or retrieval provenance is weak
route_to: Agent 4 Source Scouts
reason: retrieval selected the wrong candidate source

problem: original request is ambiguous and cannot be judged even after extraction
route_to: Agent 2 Intent Analyst / Clarification Manager
reason: ask user inside the same run_id, not as a fresh query

problem: trusted selected source truly has no requested slice
route_to: terminal not_found candidate
reason: only after checked source evidence proves absence

problem: adapter exception, script mismatch, narrator error, LLM error
route_to: system_error / gated
reason: internal workflow failure, not data absence
```

Target structure:

```python
class RepairRoute(BaseModel):
    target_agent: Literal[
        "intent_analyst",
        "clarification_manager",
        "source_scouts",
        "coverage_schema",
        "extraction_planner",
        "deterministic_tools",
        "narrator",
        "none",
    ]
    restart_from_stage: str
    preserve_artifact_ids: list[str]
    invalidate_artifact_ids: list[str]
    reason: str
    required_changes: list[str]
```

`FinalOutcomeDecision` should include:

```python
repair_route: RepairRoute | None
```

This prevents a bad pattern where the workflow sees one post-extraction mismatch and repeats expensive Source Scouts/CKAN/Qdrant/Graph RAG work unnecessarily. Full restart should be rare and explicit, for example when Agent 1/2 normalized the original request incorrectly.

### Simplified numbering: Agent 7 -> Agent 8 handoff

For product explanation, the post-extraction agents can be numbered as:

```text
Agent 7 Methodology Critic
Agent 8 Output Builder
```

In code today, `Agent 8 Output Builder` is split into two files:

```text
app/workflow/nodes/visualization.py
  deterministic chart/table artifact

app/workflow/nodes/narrator.py
  LLM-written final response
```

So the real current sequence in `app/workflow/service.py::_finalize_state` is:

```text
state after extraction
  contains:
    dataset_artifacts
    script_artifacts
    coverage_reports
    evidence
    intent

run_methodology_critic(state)
  -> CritiqueReport

derive_final_outcome(state, critique)
  -> final_outcome string

if final_outcome == "passed":
  build_visualization(ok_datasets[0])
    -> VisualizationSpec | None

build_workflow_response(
  state,
  final_outcome,
  critique,
  visualization
)
  -> WorkflowResponse
```

Current handoff problem:

- Agent 7 does not produce a durable `FinalOutcomeDecision`.
- Agent 7 does not produce `RepairRoute`.
- Agent 8 receives only `final_outcome: str`, `CritiqueReport`, and maybe one `VisualizationSpec`.
- Visualization receives only the first ok dataset, not the full selected dataset bundle.
- Narrator reads raw `state` again, which lets old weak fields like `selected_sources` leak into final output.
- If Agent 8/narrator fails, service converts it to `not_found`, which is wrong.

Target Agent 7 -> Agent 8 handoff:

```python
class CriticToOutputHandoff(BaseModel):
    run_id: str
    request: RequestEnvelope
    intent: IntentFrame
    final_decision: FinalOutcomeDecision
    critique: CritiqueReport
    selected_datasets: list[DatasetArtifact]
    selected_scripts: list[ScriptArtifact]
    selected_coverage_reports: list[CoverageReport]
    selected_source_candidates: list[SourceCandidate]
    answer_ledger: AnswerLedger
    trace_events: list[TraceEvent]
```

Agent 8 should not recompute the final outcome. It should only:

```text
if final_decision.terminal_outcome == passed:
  create visualization bundle
  create source-bound final answer
  include citations from answer_ledger

if final_decision.terminal_outcome == needs_clarification:
  render clarification questions

if final_decision.terminal_outcome == not_found:
  render checked sources and rejection reasons

if final_decision.terminal_outcome == system_error/gated:
  render internal failure state for UI/readiness
  do not call it not_found
```

Implementation fix:

- Add `FinalOutcomeDecision` and `CriticToOutputHandoff` artifacts.
- Store them in `Phase2State`, not just local variables in `_finalize_state`.
- Change `build_visualization()` to receive `CriticToOutputHandoff` or `VisualizationInput`.
- Change `build_workflow_response()` to receive `CriticToOutputHandoff`, not raw `state` plus loose `final_outcome`.
- Remove narrator's ability to downgrade `passed` to `not_found`; narrator validation failure should produce `WorkflowFailureArtifact(stage="narrator")`.
- Add a contract test:

```text
test_agent7_to_agent8_handoff_contains_final_decision_and_answer_ledger
```

### Hard gate: Agent 7 must only pass good data to Agent 8

Agent 7 is the final quality gate before user-facing output.

Correct rule:

```text
Agent 7 may send data to Agent 8 only when the data is already verified as answer-ready.
```

This means Agent 8 should never receive:

- candidate data;
- partially checked data;
- data that "probably" matches the query;
- extraction results with unresolved warnings about geography/period/indicator/unit;
- datasets whose source/provenance chain does not match the selected source and extraction plan;
- datasets that Agent 7 wants repaired.

If Agent 7 decides the data is bad, Agent 7 must return a repair route instead of an output handoff:

```text
bad data
  -> FinalOutcomeDecision(terminal_outcome="system_error" or "repair_needed")
  -> RepairRoute(target_agent=...)
  -> no CriticToOutputHandoff for Agent 8
```

If Agent 7 decides the data is good:

```text
good data
  -> FinalOutcomeDecision(terminal_outcome="passed")
  -> AnswerLedger
  -> CriticToOutputHandoff
  -> Agent 8 Output Builder
```

Agent 8's job is not to decide whether the data is good. Agent 8's job is to choose the right output form:

```text
if the user asked for a chart/comparison/time series:
  build VisualizationSpec / VisualizationBundle

if the user asked for a simple factual answer:
  build a concise source-bound text answer

if both are useful:
  build both, with citations
```

However, this should not be implemented as scattered brittle `if/else` logic everywhere.

Required architecture:

```text
Agent 7 semantic quality analysis:
  LLM-assisted critique + deterministic contract checks
  output is typed FinalOutcomeDecision

Agent 8 output mode selection:
  use typed IntentFrame.category, OutputPreference, DatasetShape, and FinalOutcomeDecision
  avoid keyword-only branching over raw Russian text
```

Acceptable deterministic logic:

- checking that `FinalOutcomeDecision.terminal_outcome == "passed"` before building user output;
- checking schema fields exist;
- checking row counts, provenance, artifact ids, source ids, and script files;
- routing by typed enum fields produced by previous agents.

Bad logic to remove:

- raw text keyword `if/else` branches for semantic decisions;
- source-family guessing from `source_id` strings;
- choosing chart/output mode from hardcoded words in the original Russian query;
- mapping any unexpected exception to `not_found`;
- letting Agent 8 re-judge data quality because Agent 7 did not pass a strong contract.

Target output-mode structure:

```python
class OutputPreference(BaseModel):
    mode: Literal["text", "table", "chart", "chart_and_text"]
    reason: str
    requested_by_user: bool
    confidence: float

class DatasetShape(BaseModel):
    row_count: int
    has_time_axis: bool
    has_geo_axis: bool
    has_category_axis: bool
    metric_count: int
    suitable_visualizations: list[str]

class OutputBuilderInput(BaseModel):
    handoff: CriticToOutputHandoff
    output_preference: OutputPreference
    dataset_shape: DatasetShape
```

The LLM can help decide `OutputPreference` from the normalized user request and final decision. Deterministic code should then validate and execute that decision against the dataset shape.

Tests to add:

```text
test_agent7_does_not_emit_output_handoff_for_bad_data
test_agent8_refuses_input_without_passed_final_decision
test_agent8_uses_output_preference_not_raw_query_keywords
test_simple_answer_can_skip_visualization_but_still_return_passed
test_chart_request_gets_visualization_when_dataset_shape_supports_it
test_agent8_output_error_does_not_change_data_quality_decision
```

### Agent 8 -> Agent 9 handoff: visualization/output mode to final narrator

Using compact post-extraction numbering:

```text
Agent 7 Methodology Critic
Agent 8 Data Analyst / Output Planner
Agent 9 Narrator / Response Composer
```

Important correction: Agent 8 must not be reduced to "Visualization Builder".

Visualization is only one tool inside Agent 8. The product should not remain a smart search engine that only finds datasets and prints them. After Agent 7 has verified source-bound data, Agent 8 should turn those data into task-appropriate analysis.

The desired product behavior:

```text
User asks for exact value / lookup
  -> Agent 8 returns a compact factual answer plan:
       value, unit, period, geography, source, citation
       visualization optional or skipped

User asks for comparison
  -> Agent 8 compares selected rows:
       differences, ranking, percent/absolute deltas where source-bound
       table/chart if useful

User asks for trend/dynamics
  -> Agent 8 analyzes time series:
       direction, peaks/lows, latest value, change over period
       line chart if dataset shape supports it

User asks for research/statistical overview
  -> Agent 8 synthesizes across multiple verified sources:
       what each source covers
       where sources agree/disagree
       limitations and caveats
       no invented causal claims unless data supports them

User asks "find data/source"
  -> Agent 8 emphasizes search trace and source suitability:
       where searched
       why source was selected
       what exact data slice was extracted
```

This means the system needs a distinction between:

```text
retrieval/search intent:
  "find the source / show exact data / where did this number come from"

analytical intent:
  "compare / explain dynamics / summarize statistics / analyze indicator behavior"
```

That distinction should not be implemented as scattered raw `if "compare" in query` checks. It should be part of the structured request understanding and then refined after data shape is known.

Target responsibility split:

```text
Agent 7 Critic
  receives extracted data and sources
  verifies they are good enough for user-facing analysis
  emits only verified answer-ready handoff
  if data is bad: repair route, no Agent 8 call

Agent 8 Data Analyst / Output Planner
  receives only verified data from Agent 7
  decides what analytical work is needed for this user query
  performs source-bound analysis over DatasetArtifact rows
  computes only allowed deterministic metrics from extracted data
  chooses output mode: text/table/chart/chart_and_text
  creates AnalysisArtifact + VisualizationBundle when relevant

Agent 9 Narrator / Response Composer
  receives Agent 8's analysis artifact, answer ledger, citations, and visualization bundle
  writes the final user-facing Russian response
  does not redo data analysis
  does not introduce new numbers or causal claims
  does not change passed into not_found
```

So the better naming is:

```text
Agent 8 = Data Analyst / Output Planner
Agent 8 tools = statistics/comparison/trend/table/visualization builders
Agent 9 = Narrator / Response Composer
```

#### Target Agent 8 analytical structures

```python
class UserTaskProfile(BaseModel):
    task_type: Literal[
        "exact_lookup",
        "source_discovery",
        "comparison",
        "trend_analysis",
        "statistical_summary",
        "research_synthesis",
        "data_table_request",
    ]
    needs_precise_value: bool
    needs_source_explanation: bool
    needs_computation: bool
    needs_visualization: bool
    needs_methodology_explanation: bool
    reason: str
    confidence: float

class AnalysisOperation(BaseModel):
    operation_id: str
    operation_type: Literal[
        "select_value",
        "rank",
        "difference",
        "percent_change",
        "trend_summary",
        "aggregate",
        "compare_sources",
        "describe_coverage",
    ]
    input_dataset_artifact_ids: list[str]
    required_columns: list[str]
    output_fields: list[str]
    source_bound_formula: str | None

class AnalysisArtifact(BaseModel):
    artifact_id: str
    task_profile: UserTaskProfile
    operations: list[AnalysisOperation]
    computed_results: list[dict[str, Any]]
    source_bound_claims: list[dict[str, Any]]
    limitations: list[str]
    citation_ids: list[str]
    visualization_recommendation: OutputModeDecision
```

Agent 8 should use LLM for semantic planning:

```text
What kind of analytical answer does this user want?
Which operations are needed?
What should be explained?
Should output be mostly text, table, chart, or chart+text?
```

But Agent 8 must use deterministic code for numeric computations:

```text
select exact values
sort/rank
calculate difference
calculate percent change
aggregate rows
build chart specs
```

The LLM can choose the operation plan; it cannot invent computed numbers.

#### Why current code fails this product goal

Current code has only:

```text
IntentFrame.category = simple | comparative | research | derived_metric | ambiguous | no_data
ResearchDesignArtifact for research routes
VisualizationSpec from first dataset
Narrator summary/methodology/how_found
```

This is not enough to become an analyst.

Examples:

- A user asks "compare Russia and Kazakhstan GDP growth from 2015 to 2022".
  Current system may retrieve and extract rows, then narrator summarizes samples. It lacks an explicit comparison operation, ranking/difference plan, and citation-bound computed claims.

- A user asks "what happened to inflation after 2020?"
  Current system may return rows and a line-like chart type, but it lacks trend analysis semantics: latest value, direction, peak, change from start to end, and limitation that this is descriptive not causal.

- A user asks "where can I find official data on unemployment?"
  This is more search/source-discovery than analysis. Agent 8 should emphasize source suitability, checked catalogs, coverage, and extraction path, not overproduce statistical interpretation.

- A user asks "summarize the statistics for migration in CIS countries".
  This is research/statistical overview. Agent 8 should synthesize multiple verified data slices and explain source coverage/limitations, not only return a first dataset table.

#### Request understanding must feed Agent 8

Earlier agents should produce enough structure for Agent 8:

```python
class IntentFrame(BaseModel):
    category: ...
    known_fields: ...
    missing_fields: ...
    source_preferences: ...
    user_task_profile_hint: UserTaskProfile | None
```

Research Designer should add:

```python
class ResearchDesignArtifact(BaseModel):
    analytical_questions: list[str]
    expected_operations: list[str]
    source_comparison_strategy: str | None
    explanation_depth: Literal["brief", "normal", "deep"]
```

Agent 7 should validate:

```text
Do verified datasets support the requested analytical operations?
```

Agent 8 should finalize:

```text
Which operations can be performed from the verified rows?
Which requested operations are unsupported?
What limitations must be shown to the user?
```

#### Agent 8 -> Agent 9 after this correction

Agent 8 should pass:

```python
class AnalystToNarratorHandoff(BaseModel):
    run_id: str
    final_decision: FinalOutcomeDecision
    task_profile: UserTaskProfile
    analysis_artifact: AnalysisArtifact
    visualization_bundle: VisualizationBundle
    answer_ledger: AnswerLedger
    citations: list[Citation]
```

Agent 9 should not receive raw datasets as its main reasoning object. It may receive compact tables for context, but its authoritative input is `AnalysisArtifact` + `AnswerLedger`.

Agent 9 output rules:

```text
exact_lookup:
  short answer first, then source/methodology

source_discovery:
  source first, coverage and how_found next, extracted data if available

comparison:
  comparative conclusion first, table/chart next, limitations last

trend_analysis:
  trend statement first, time-series evidence, chart if available

statistical_summary/research_synthesis:
  structured findings, source coverage, limitations, citations
```

These are response templates selected from `UserTaskProfile`, not raw keyword branches.

Tests to add:

```text
test_agent8_distinguishes_source_discovery_from_statistical_analysis
test_agent8_exact_lookup_returns_value_plan_without_forcing_chart
test_agent8_comparison_creates_difference_or_ranking_operations
test_agent8_trend_analysis_creates_source_bound_trend_operations
test_agent8_research_synthesis_uses_multiple_verified_sources
test_agent9_uses_analysis_artifact_not_raw_dataset_samples
test_agent9_does_not_add_causal_explanation_without_analysis_claim
test_agent9_response_shape_changes_by_user_task_profile
```

Current implementation:

```text
service._finalize_state
  -> build_visualization(ok_datasets[0], query_category=intent.category)
       returns VisualizationSpec | None
  -> build_workflow_response(
       state,
       final_outcome,
       critique,
       visualization
     )
       returns WorkflowResponse
```

Current code locations:

- `app/workflow/service.py::_finalize_state`
- `app/workflow/nodes/visualization.py::build_visualization`
- `app/workflow/nodes/narrator.py::build_workflow_response`
- `app/ui/streamlit_app.py::_render_visualization`
- `app/workflow/graph_contract.py`

#### Current Agent 8 responsibilities

Current Agent 8 is only a thin deterministic helper:

```text
input:
  first ok DatasetArtifact only
  query_category string

logic:
  inspect dataset columns
  choose chart_type:
    period + one geo -> line
    period + multi geo -> grouped_line
    comparative/no period -> bar
    otherwise -> table

output:
  VisualizationSpec
```

This is not enough for a jury MVP.

Agent 8 should not merely "make any chart". It should choose the correct output mode from already structured intent and dataset shape:

```text
text answer
table answer
chart answer
chart + text answer
no visualization, with explicit reason
```

#### Current Agent 8 -> Agent 9 handoff

Current handoff is too thin:

```python
visualization: VisualizationSpec | None
```

Agent 9 receives this parameter, but the live narrator prompt does not include a structured visualization summary. It receives:

```text
query
final_outcome
critique verdict/warnings
dataset_summaries
script_summaries
selected_sources
rejected_sources
missing_fields
```

It does not receive:

- `VisualizationSpec.status`;
- `VisualizationSpec.chart_type`;
- visualization skip reason;
- output mode chosen by Agent 8;
- dataset shape used to justify chart/table/text;
- whether the user asked for visualization;
- whether visualization is optional or required;
- a `VisualizationBundle` containing all selected datasets.

So Agent 8 is currently not a real upstream contract for Agent 9. It is mostly a side object that gets attached to the final `WorkflowResponse` if `final_outcome == "passed"`.

#### Bugs in Agent 8

1. **Only first dataset is visualized.**

Current code:

```python
ok_datasets = [...]
visualization = build_visualization(ok_datasets[0], ...)
```

If the answer is comparative, multi-source, or multi-indicator, Agent 8 ignores all other datasets.

2. **Visualization is silently dropped on errors.**

Current code catches visualization exceptions and sets `visualization = None`.

This loses evidence. The UI then shows "No visualization", but cannot tell whether:

- no chart was needed;
- chart was impossible for the dataset shape;
- visualization code failed;
- Agent 8 was skipped because final outcome was not passed.

3. **Agent 8 uses a weak `query_category` string instead of typed output preference.**

Chart choice is not based on `OutputPreference`, `IntentFrame`, `DatasetShape`, or `FinalOutcomeDecision`. It is a local heuristic over columns plus one category string.

4. **Deterministic renderer does not really render the intended chart.**

`app/data/deterministic_tools.py::render_visualization_from_dataset_artifact` currently creates an Altair `mark_text()` that displays "`N rows`" or falls back to a table-like spec. Then `visualization.py` overwrites `chart_type` to `line`, `bar`, etc., but the underlying `encoding` may still be a text/table spec.

This can produce a mismatch:

```text
VisualizationSpec.chart_type = "line"
encoding.spec = mark_text / table fallback
```

5. **Graph contract order conflicts with service implementation.**

`app/workflow/graph_contract.py` lists `Narrator` before `Visualization`, but `service.py` actually runs visualization before narrator.

The target should be explicit:

```text
Agent 8 Output Mode / Visualization Builder
  -> Agent 9 Narrator / Response Composer
```

Narrator needs to know what output artifacts exist and what should be described.

6. **No visualization trace event.**

`graph_contract.py` says Visualization emits `TraceEvent`, but current `build_visualization()` does not append a trace event and `_finalize_state` does not add one either.

7. **UI renders visualization as raw JSON only.**

`streamlit_app.py::_render_visualization` prints `response.visualization.model_dump()`. It does not render the chart. For a demo/jury UI, the visualization artifact should be displayed as a real chart/table when possible, with JSON kept as debug evidence.

#### Bugs in Agent 9

1. **Agent 9 reads raw state instead of the Agent 8/Agent 7 handoff.**

Narrator reads `state`, `final_outcome`, `critique`, and `visualization`, but it does not receive `CriticToOutputHandoff` or `OutputBuilderInput`.

This lets old weak fields leak into final answer composition:

```text
EvidenceBundleArtifact.selected_sources
EvidenceBundleArtifact.rejected_sources
raw state["query"]
raw state["coverage_reports"]
```

2. **Agent 9 can downgrade passed data to `not_found`.**

If narrator generates unsupported numeric claims, current code sets:

```python
final_outcome = "not_found"
```

This is wrong. If Agent 7 passed the data, narrator numeric failure is an output-stage bug:

```text
WorkflowFailureArtifact(stage="narrator", failure_type="unsupported_numeric_claim")
```

3. **Agent 9 does not use a strong answer ledger.**

The current numeric guard builds a regex number ledger from dataset records/provenance. This is better than nothing, but it is still too weak:

- it does not bind each number to a citation;
- it can confuse years, source ids, row counts, and metric values;
- it cannot verify computed claims like "increased by 10%";
- it checks only `message`, not all answer blocks;
- it does not verify methodology/how_found numeric claims.

4. **Agent 9 citations are too weak.**

Current citations are:

```python
{"source_id": d.source_id, "artifact_id": d.artifact_id}
```

This is not enough for source-bound answers. Citations should point to:

```text
source_candidate_id
coverage_report_id
extraction_plan_id
dataset_artifact_id
provenance resource/package/table
row/period/indicator evidence where possible
```

5. **Agent 9 prompt does not include visualization context.**

The final text may mention or ignore charts inconsistently because narrator does not receive:

```text
chart_type
visualization status
visualization skip reason
dataset_shape
output_preference
```

6. **Agent 9 fallback/no-response behavior still exists as scaffolding.**

`_build_response_fallback` raises now, which is better than fake output, but the service catches narrator exceptions and converts them into `not_found`. That reintroduces the same bad fallback at the service layer.

#### Target Agent 8 structure

```python
class OutputModeDecision(BaseModel):
    decision_id: str
    mode: Literal["text", "table", "chart", "chart_and_text"]
    requested_by_user: bool
    reason: str
    confidence: float

class DatasetShape(BaseModel):
    dataset_artifact_ids: list[str]
    row_count: int
    metric_columns: list[str]
    dimension_columns: list[str]
    time_columns: list[str]
    geo_columns: list[str]
    supports_chart_types: list[str]

class VisualizationBundle(BaseModel):
    artifact_id: str
    status: Literal["ok", "skipped", "error"]
    output_mode: OutputModeDecision
    dataset_shape: DatasetShape
    specs: list[VisualizationSpec]
    skip_reason: str | None
    error: str | None
```

Agent 8 input:

```text
CriticToOutputHandoff from Agent 7
```

Agent 8 output:

```text
VisualizationBundle
AnswerLedger extension with output-ready table/chart references
```

#### Target Agent 9 structure

```python
class ResponseComposerInput(BaseModel):
    handoff: CriticToOutputHandoff
    visualization_bundle: VisualizationBundle
    answer_ledger: AnswerLedger

class Citation(BaseModel):
    citation_id: str
    source_candidate_id: str
    coverage_report_id: str
    extraction_plan_id: str
    dataset_artifact_id: str
    provenance_ref: dict[str, Any]

class ResponseComposerOutput(BaseModel):
    workflow_response: WorkflowResponse
    unsupported_claims: list[str]
    output_failures: list[WorkflowFailureArtifact]
```

Agent 9 must treat Agent 8 output as part of the answer contract:

```text
if output_mode includes chart:
  include visualization artifact in WorkflowResponse
  mention chart/table only if VisualizationBundle.status == ok

if output_mode is text:
  do not create a fake chart
  still return passed if Agent 7 passed the data

if VisualizationBundle.status == error:
  preserve passed data answer if text output is still possible
  record visualization_error
  do not return not_found
```

#### Fix direction

- Introduce `VisualizationBundle` and `OutputModeDecision`.
- Change Agent 8 to process all selected datasets, not only `ok_datasets[0]`.
- Make Agent 8 produce explicit `skipped` and `error` statuses instead of `None`.
- Pass `VisualizationBundle` into Agent 9 prompt and response assembler.
- Make `WorkflowResponse.visualization` support either a bundle/list or add `visualizations: list[VisualizationSpec]`.
- Make UI render real chart/table from `VisualizationSpec.encoding`, not only JSON.
- Add visualization trace event.
- Remove service-layer narrator exception fallback to `not_found`.
- Replace regex-only numeric guard with answer-ledger validation across `message` and `answer_blocks`.
- Strengthen citations from dataset-only to source/coverage/plan/dataset provenance.

Tests to add:

```text
test_agent8_visualizes_all_selected_datasets_not_only_first
test_agent8_returns_skipped_visualization_with_reason
test_agent8_chart_type_matches_encoding_spec
test_agent8_emits_trace_event
test_agent9_receives_visualization_bundle_in_prompt_context
test_agent9_does_not_claim_chart_exists_when_visualization_skipped
test_agent9_text_only_output_can_still_pass_without_visualization
test_agent9_unsupported_number_is_output_failure_not_not_found
test_workflow_response_citations_include_source_coverage_plan_dataset
test_streamlit_renders_visualization_not_only_json
```

### Agent 9 Visualization Builder - current bug

Current code:

- `service._finalize_state` passes only `ok_datasets[0]` into `build_visualization`.
- `visualization.py` chooses chart type by simple column inspection.
- It ignores multiple extracted datasets, comparative questions, requested units, source family, and extraction plan semantics.

This stage should be deterministic, so using code here is correct. The bug is not "no LLM". The bug is that it only visualizes the first ok dataset and does not receive enough structured intent/extraction context.

Correct behavior:

```text
Agent 9 should build visualization specs only after FinalOutcomeDecision.terminal_outcome == passed.
It should receive all selected DatasetArtifacts, not only the first one.
It should use IntentFrame.category and ExtractionPlan.output_shape to choose:
  single time series -> line
  multi-country / multi-region time series -> grouped_line
  category comparison -> bar
  table-first result -> table
  multiple metrics -> small_multiples or table with explicit limitation
```

Target structure:

```python
class VisualizationInput(BaseModel):
    final_decision: FinalOutcomeDecision
    datasets: list[DatasetArtifact]
    extraction_plan: ExtractionPlan
    intent: IntentFrame
    chart_policy: Literal["auto", "table_only", "time_series_preferred"]

class VisualizationBundle(BaseModel):
    status: Literal["ok", "skipped", "error"]
    specs: list[VisualizationSpec]
    skipped_reason: str | None
    dataset_artifact_ids: list[str]
```

Fix direction:

- Replace `build_visualization(ok_datasets[0])` with `build_visualization_bundle(VisualizationInput)`.
- Preserve a skipped visualization as an explicit artifact, not `None`, so the UI can explain why no chart exists.
- Do not let visualization failure change `passed` into `not_found`; visualization failure is a presentation error.
- Add tests for comparative/multiple datasets and for visualization failure not changing final outcome.

### Agent 10 Narrator / Response Composer - current bug

Current code:

- `build_workflow_response()` calls live Qwen when `live_llm_required=True`.
- It sends the narrator compact dataset samples, selected sources, rejected sources, and critique warnings.
- If narrator creates unsupported numeric claims, code downgrades the final outcome to `not_found`.
- If narrator raises, `service._finalize_state` catches it and returns `WorkflowResponse(final_outcome="not_found")` with `NoDataExplanationArtifact(rejection_reasons=["narrator_error:..."])`.
- `_assemble_response()` uses old `selected_sources` / `rejected_sources` from `EvidenceBundleArtifact`, not the typed source/coverage/extraction chain.

This is wrong.

If deterministic extraction already succeeded, narrator failure means:

```text
data exists
source exists
answer composition failed
```

It does not mean:

```text
not_found
```

Unsupported narrator numbers are also not evidence that data is missing. They are evidence that Agent 10 violated source-bound answer rules.

### Agent 10 target behavior

Narrator should receive a strict answer ledger:

```python
class AnswerLedger(BaseModel):
    dataset_values: list[dict[str, Any]]
    allowed_numbers: list[str]
    allowed_periods: list[str]
    allowed_units: list[str]
    citation_map: dict[str, list[str]]
    source_titles: dict[str, str]
    extraction_summary: dict[str, Any]
```

The narrator may transform this into readable Russian text, but it cannot add new factual claims.

Target output:

```python
class NarratorOutput(BaseModel):
    message: str
    answer_blocks: list[AnswerBlock]
    citations: list[Citation]
    limitations: list[str]
    clarification_questions: list[str]
    unsupported_claims: list[str]
```

Post-check:

```text
if unsupported_claims:
  return system_error / narrator_failed_source_bound_check
  do not return not_found

if narrator LLM unavailable:
  return gated / llm_unavailable
  do not produce fake terminal answer

if narrator raises:
  return WorkflowFailureArtifact(stage="narrator", failure_type="narrator_error")
  do not create NoDataExplanationArtifact
```

### Agent 10 fix direction

- Delete the `service._finalize_state` fallback that maps narrator exceptions to `not_found`.
- Replace narrator exception handling with `WorkflowFailureArtifact(stage="narrator", failure_type="narrator_error")`.
- Replace "unsupported numeric claim -> not_found" with "narrator failed source-bound validation".
- Do not give narrator raw untyped retrieval candidates as final citations. Give it the source/citation ledger derived from:

```text
DatasetArtifact.provenance
ExtractionPlan.source_candidate_ids
CoverageBundleArtifact.selected_report_ids
EvidenceBundleArtifact.selected_for_coverage
```

- The response composer should include datasets/scripts/visualizations whenever `FinalOutcomeDecision.terminal_outcome == passed`, independent of narrator wording.
- `NoDataExplanationArtifact` should only be created from true source-bound absence evidence, not from narrator/critic errors.

Tests to add:

```text
test_narrator_error_does_not_become_not_found
test_unsupported_numeric_claim_is_narrator_failure_not_not_found
test_passed_response_uses_dataset_provenance_as_citations
test_narrator_receives_answer_ledger_not_raw_source_candidates
test_visualization_failure_does_not_change_passed_outcome
```

## Priority Fix Order

1. **Separate eval fixtures from runtime.** Remove golden matrix hints from graph/state/research designer.
2. **Fix acceptance scorer.** `expected=passed` must not accept empty `not_found`.
3. **Make CLI reproducible and bounded.** Fix imports and add per-case timeout.
4. **Strengthen handoff contracts.** Add typed source candidate and extraction plan routing fields.
5. **Rebuild query understanding.** Add Russian normalization/concept candidates before retrieval.
6. **Make Graph RAG auditable.** Record graph-first/graph-neighbour evidence without treating graph hits as final truth.
7. **Define runtime modes.** LIVE_JURY vs LOCAL_DEV vs UNIT_TEST.
8. **Add non-golden smoke set.** Test arbitrary Russian paraphrases so code stops orbiting only the 20 cases.

## Notes For Future Agents

- Golden cases are an acceptance/eval set, not a product API and not a hidden prompt source.
- The agent must be source-bound: numbers from deterministic adapters only.
- CKAN is bounded trusted catalog search, not general web search.
- If the system cannot find data, it must show checked sources and rejection reasons.
- If the system asks clarification, it must name missing fields and concrete options.
- If a query is expected to pass, `not_found` is a failure unless an explicit evidence-backed alternative outcome is allowed.
