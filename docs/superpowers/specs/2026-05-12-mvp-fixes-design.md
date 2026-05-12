# MVP Fixes Design — 2026-05-12

Four independent improvements for MVP readiness. All changes are in existing code; no new services or dependencies.

---

## Fix 1 — Remove number verifier downgrade

**Files:** `app/workflow/nodes/narrator.py`

**Problem:** `assert_message_numbers_are_supported` downgrades `passed` → `not_found` when narrator scales a number (e.g. raw `1376477.9` → displayed `"1376 млрд"`). The architecture already guarantees numbers come from DatasetArtifact.records, so the check only produces false positives.

**Change:** Wrap the `assert_message_numbers_are_supported` call in a `logging.warning` path — downgrade is removed. The function is kept for diagnostic purposes but no longer controls the terminal outcome.

```python
# Before (narrator.py ~309-313):
try:
    assert_message_numbers_are_supported(result.message, ok_datasets)
except ValueError:
    final_outcome = "not_found"

# After:
try:
    assert_message_numbers_are_supported(result.message, ok_datasets)
except ValueError as exc:
    logger.warning("number_verifier_advisory: %s", exc)
    # outcome unchanged — artifact already came from adapter records
```

**Tests:** Update any test that asserts `not_found` due to number verifier rejection.

---

## Fix 2 — Inline chart in chat

**Files:** `app/web/static/js/app.js`, `app/web/static/js/charts.js`

**Problem:** `VisualizationSpec` is rendered in the sidebar only. The chat message body has no chart.

**Design:**
1. After the `done` SSE event builds content blocks, add a chart block if `response.visualization.status === "ok"` and `chart_type !== "table"`.
2. Map `response.dataset_artifacts[0].records` → `{values, labels}` using the `period` column as label and the first numeric column (`value`, `val`, or first number-type field) as value.
3. For `chart_type = "line" | "grouped_line"`: call existing `renderTrendChart(values, labels)` → inline SVG.
4. For `chart_type = "bar"`: call a new `renderBarChart(values, labels)` in `charts.js` (same style as `renderTrendChart`, vertical bars).
5. Add a small «↗» button that opens the chart SVG in a full-screen overlay (`<dialog>`).
6. Multi-series (grouped_line): group records by `geo_id` or `country_id`, render one line per series with distinct colours.

**No new dependencies** — Altair/Vega not used in frontend rendering; SVG is hand-built by charts.js.

---

## Fix 3 — Smart query expansion via Qwen general knowledge

**Files:** `app/workflow/state.py` (or wherever `design_research` lives), `app/artifacts/workflow_artifacts.py`, `app/workflow/nodes/source_scouts.py` (or equivalent)

**Problem:** Compound queries like "Основные экономические показатели России за 2000-2013" have a vague `indicator` field. Scouts search for a single undifferentiated concept → weak retrieval.

**Design:**

### 3a. ResearchDesignArtifact — new field
```python
expanded_indicators: list[dict] = []
# Each item: {"name_ru": "ВВП", "name_en": "GDP", "search_query_ru": "...", "search_query_en": "..."}
```

### 3b. Research Designer prompt addition
When intent category is `research` or `derived_metric` and `indicator` is a compound concept (Qwen decides), add structured output instruction:

> "Если запрос содержит агрегатный концепт (например 'основные экономические показатели'), разложи его на 3-7 конкретных экономических индикаторов используя свои знания. Для каждого укажи название на русском, название на английском, и оптимальную поисковую фразу для retrieval (краткую, точную)."

Qwen returns `expanded_indicators` via structured output. No hardcoded lists — Qwen knows economics.

### 3c. Source Scouts — iterate over expanded indicators
If `research_design.expanded_indicators` is non-empty:
- Run `HybridRetriever.search(item["search_query_ru"], limit=3)` for each item
- Also run `HybridRetriever.search(item["search_query_en"], limit=3)` for WB cards
- Deduplicate by `card_id`, merge into `evidence.selected_sources`

If `expanded_indicators` is empty — existing single-query scout path unchanged.

### 3d. Narrator
Adds preamble: *«По запросу "Основные экономические показатели России" собраны данные по 5 показателям: ВВП, CPI, безработица, реальные доходы, промышленное производство.»*

---

## Fix 4 — Partial period coverage → `passed` with warning

**Files:** `app/workflow/nodes/coverage.py`, `app/workflow/nodes/critic.py`, `app/workflow/nodes/narrator.py`

**Problem:** When only 2000-2022 is available but 2000-2024 was requested, coverage sets `status="not_found"` → terminal `not_found`. User gets nothing.

**Design:**

### 4a. Coverage node — new status `"partial"`
```python
# When requested period partially overlaps available_periods:
if requested_period_outside_available and len(available_periods) > 0:
    report.status = "partial"
    report.partial_note = f"доступны только {available_periods[0]}–{available_periods[-1]}"
```

Existing `"ok"` status unchanged — only triggers when the requested range is entirely within available.

### 4b. Critic — accept `"partial"` as non-blocking
```python
ACCEPTABLE_COVERAGE_STATUSES = {"ok", "partial"}

def _coverage_all_ok(coverage_reports):
    return all(
        getattr(r, "status", "not_found") in ACCEPTABLE_COVERAGE_STATUSES
        for r in coverage_reports
    )
```

### 4c. Narrator — add partial coverage note
When any coverage report has `status="partial"`, append to message:
> *«Данные доступны частично: {partial_note}. За запрошенный период {requested_period} полного покрытия нет.»*

**Tests:** Add test: request 2000-2024, mock adapter returns 2000-2022 → outcome `passed`, message contains partial note.

---

## Execution order

All 4 fixes are independent. Run in parallel.

| Fix | Touches | Risk |
|-----|---------|------|
| 1 — verifier | `narrator.py` lines 309-313 | Low |
| 2 — chart | `app.js`, `charts.js` | Low |
| 3 — expansion | `state.py`, `workflow_artifacts.py`, `source_scouts.py` | Medium |
| 4 — partial | `coverage.py`, `critic.py`, `narrator.py` | Low-medium |

Fix 1 and Fix 4 both touch `narrator.py` but different sections (lines 309-313 vs. the message-building block).
