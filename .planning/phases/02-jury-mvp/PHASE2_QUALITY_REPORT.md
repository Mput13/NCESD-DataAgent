# Phase 2 Workflow Quality Report

**Date:** 2026-05-11  
**Target:** Jury MVP (Phase 2)  
**Status:** Verification Completed (with identified defects)

## Executive Summary
The headless workflow with the observability layer is functional. It successfully records node transitions, LLM prompts/responses, and tool interactions. However, systemic bugs in **schema validation** and **source adapters** prevent the agent from delivering accurate results and clear feedback. These issues must be addressed to ensure reliable data for subsequent analysis.

---

## 1. Workflow Defect Inventory

### 1.1 Critic Node Schema Mismatch (Critical)
*   **Trace ID:** `phase2-c2ff3a768048-q001` (and others)
*   **Symptom:** The `Methodology Critic` fails to parse LLM output.
*   **Technical Root Cause:** `_CritiqueSchema` expects `repair_plan` to be a `list[str]`. Qwen-3.5/3.6 sometimes returns a single `str` instead of a list when only one suggestion is made.
*   **Impact:** The system records a technical Python error in `rejection_reasons` instead of the actual LLM critique, making automated "self-correction" or human analysis of model feedback impossible.
*   **Log Evidence:**
    ```
    critic_error:1 validation error for _CritiqueSchema
    repair_plan
      Input should be a valid list [type=list_type, input_value="...", input_type=str]
    ```

### 1.2 FedStat Extraction "False Negative" (Critical)
*   **Query:** "ВВП России за 2011 год"
*   **Symptom:** Returns `not_found` (0 rows) despite data existing in the source file.
*   **Technical Root Cause:** Geography normalization mismatch. The agent looks for `"Российская Федерация"` or `"Россия"`, but the FedStat Parquet file (e.g., `40570.parquet`) uses codes and uppercase names like `"643 РОССИЯ"`.
*   **Impact:** Massive loss of data retrieval capability. The agent "sees" the indicator but "fails" to extract the specific row.
*   **Verification:** Manual DuckDB query confirmed 7867 rows exist in the file, including Russian data.

---

## 2. Observability Evaluation

### 2.1 Artifact Preservation
The system correctly saves the following to `.planning/phases/02-jury-mvp/batch-runs/<run_id>/items/<item_id>/audit/`:
*   `node-events.jsonl`: Successfully tracks state machine transitions.
*   `llm-calls.jsonl`: Captures raw system/user messages and raw model responses. **Crucial for prompt engineering analysis.**
*   `tool-calls.jsonl`: Captures inputs/outputs for `deterministic_tools`.
*   `retrieval.jsonl`: Captures index scores and metadata for matched chunks.

### 2.2 Gaps identified for Analysis
*   **Token Usage:** Currently not tracked per call in the JSONL. Adding this would help estimate costs.
*   **Latency Analysis:** While `duration_ms` exists in `node-events`, it's not present in individual `llm-calls.jsonl` entries.
*   **Payload Size:** Large dataset outputs in `tool-calls.jsonl` might become a storage issue; need a policy for truncation or external storage.

---

## 3. LLM Performance Analysis (Qwen-3.5/3.6)

*   **Instruction Following:** Generally high. The model successfully switches between `direct` and `research` routes.
*   **Reasoning Quality:** The `IntentFrame` extraction is robust (successfully extracted geography="Россия", period="2011" from free text).
*   **JSON Compliance:** Good, but sensitive to strict typing in Pydantic (see 1.1). Qwen tends to be descriptive, which sometimes overflows single-string fields.

---

## 4. Proposed Remediation Plan

1.  **Robust Schema Parsing:** Update `app/workflow/nodes/critic.py` to handle both `str` and `list[str]` for the `repair_plan` field, or use a Pydantic `BeforeValidator` to wrap strings into lists.
2.  **Fuzzy Geography Matching:** Implement a more permissive matcher in `app/data/fedstat_adapter.py` that handles `ID NAME` patterns (e.g., `643 РОССИЯ`).
3.  **Audit Session Refinement:** Add timing and token usage (if available from Yandex AI Studio API) to the `WorkflowAuditSession`.

---
*Report generated automatically following verification run.*
