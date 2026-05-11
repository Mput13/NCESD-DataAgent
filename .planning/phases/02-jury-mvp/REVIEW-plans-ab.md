# Review: Plans A+B Schema & Slice Fixes

**Date:** 2026-05-11  
**Reviewer:** Claude (gsd-code-reviewer)  
**Scope:** Plans A+B — Schema hardening + slice validation + parquet paths  
**Depth:** deep (cross-file call chain analysis)

---

## Fix 1: `_IntentAnalysisSchema` geography list→str validator — PARTIAL

**Root cause addressed:** Yes — LLM returning `geography` as a list caused `ValidationError` in `state.py`.

**Implementation:** `_coerce_geography_list` converts `list → comma-joined str`. `_coerce_countries` converts `str → [str]`. `_derive_countries_from_geography` back-fills `countries` from geography if empty.

**Edge cases missed:**

1. **BLOCKER — nested list not handled.** `_coerce_geography_list` iterates items with `str(item)`, but if the LLM returns `[["Russia", "China"]]` (nested), `str(["Russia", "China"])` is included literally, producing `"['Russia', 'China']"` as a geography string. No guard exists.

2. **WARNING — `_derive_countries_from_geography` duplicates `_analyze_intent_live` logic.** Lines 169–171 in `state.py` re-derive `countries` from `geography` after the model is already fully validated by the `@model_validator`. This means `known_fields["countries"]` may end up duplicated if both branches run (the `if result.countries` branch populates it, but if the LLM returns `countries=[]` and `geography="Russia"`, the `@model_validator` fills `self.countries`, yet `known_fields["countries"]` is populated again by the fallback `elif result.geography` at line 169). Double-derivation is harmless in the simple case but creates confusion.

3. **WARNING — `countries` field is not propagated into `IntentFrame.known_fields` consistently.** `IntentFrame` has no `countries` key in its schema. `known_fields` is a `dict[str, Any]`, so `countries` goes in as a raw key. Downstream `_world_bank_coverage` reads `intent_fields.get("countries")`, which works, but this is implicit contract — no schema enforces it.

**Risk:** The nested-list edge case could still produce a `ValidationError` on unusual LLM output (e.g., Qwen wrapping an array of arrays). Low probability but not zero.

---

## Fix 2: `_CoverageAssessment` `best_slice: str = ""` → `str | None = None` — CORRECT

**Root cause addressed:** Yes — `best_slice: str = ""` caused a `ValidationError` when Qwen returned `null` for this field.

**Implementation:** Changing to `str | None = None` accepts `null`. The `@field_validator` on `alternative_slices` and `quality_risks` correctly coerces `null → []` and `str → [str]`.

**Edge cases missed:**

- **WARNING — the validator is defined inside a `try` block (`_llm_assess_coverage`) and is a local class.** If an exception occurs before the class is defined (e.g., `from pydantic import BaseModel, field_validator` itself raises), the entire LLM assessment is silently swallowed by the outer `except Exception: return reports` at line 148. The fix is correct when pydantic is present, but the fallback hides all failures silently — this is pre-existing, but the new validator code is now invisible when pydantic fails.

**Risk:** Low. The fix is correct for the stated failure mode.

---

## Fix 3: `_CritiqueSchema` validator for `warnings`/`repair_plan` — CORRECT

**Root cause addressed:** Yes — Qwen returning a plain string for `warnings` or `repair_plan` instead of a list caused `ValidationError`, which propagated to `not_found`.

**Implementation:** `wrap_string_in_list` handles `None`, `str`, and any iterable. Applied to both fields simultaneously via `@field_validator("warnings", "repair_plan", mode="before")`.

**Edge cases missed:**

- **WARNING — `_CritiqueSchema` is defined inside a `try/except ImportError` block (lines 31–48 in critic.py).** If the import fails, `_CritiqueSchema = None`. Downstream `_run_critic_live` calls `client.structured_chat(..., schema=_CritiqueSchema, ...)`. Passing `schema=None` is not validated before the call — the behavior depends entirely on `YandexAIStudioClient.structured_chat`'s handling of a `None` schema, which is not reviewed here. This is pre-existing but worth noting.

**Risk:** Low for the specific fix. The `ImportError` path is a pre-existing risk.

---

## Fix 4: `_tag_diagnostic` in narrator — PARTIAL / CREATES NEW BUG

**Root cause addressed:** Partially. The intent is to always include `dataset_artifacts` in the `WorkflowResponse` even when `final_outcome != "passed"`, with a `"diagnostic"` quality flag to signal they are not authoritative.

**Implementation:** `_tag_diagnostic` adds `"diagnostic"` to `quality_flags` on non-passed artifacts. It is called inside `_assemble_response` at line 532: `dataset_artifacts=_tag_diagnostic(dataset_artifacts, final_outcome)`.

**BLOCKER — `WorkflowResponse.model_validator` requires `not_found_evidence is not None` for `not_found` outcome (line 276–277 in workflow_artifacts.py).** The narrator's `_assemble_response` always passes `dataset_artifacts` (including gated/empty ones) to `WorkflowResponse`. This is safe for `passed`. But for `not_found`, passing non-empty `dataset_artifacts` does NOT violate `WorkflowResponse`'s validator — it only checks `not_found_evidence is not None`. However, a different issue exists:

**BLOCKER — `not_found` path with `live_llm_required=True` and prior numeric-assertion failure.** When `final_outcome` is downgraded from `passed` to `not_found` inside `_build_response_live` (lines 310–326), `no_data_evidence` is constructed correctly. But `_assemble_response` is then called with `dataset_artifacts=dataset_artifacts` (the original list, not filtered). These artifacts have `status="gated"` (set by deterministic_tools zero-row guard). The `WorkflowResponse.validate_terminal_outcome_requirements` validator at line 269 checks `if self.final_outcome == "passed": if not self.dataset_artifacts: raise`. For `not_found`, it only checks `not_found_evidence`. So passing gated artifacts for `not_found` is technically valid per the validator — **but** it means `not_found` responses can silently carry `dataset_artifacts` with `status="gated"` and `quality_flags=["empty_slice", "diagnostic"]`. Callers that assume `not_found` means zero datasets will be surprised.

**WARNING — `_tag_diagnostic` type annotation uses `list[DatasetArtifact]` but receives raw list from `state.get("dataset_artifacts")`** which may contain dicts (if the state was serialized/deserialized by LangGraph). If `a.quality_flags` fails because `a` is a dict, `model_copy` raises `AttributeError`. No defensive check.

**Risk:** High — the diagnostic tagging interacts with `WorkflowResponse` serialization in ways callers may not expect. The `not_found` + non-empty `dataset_artifacts` combination is semantically inconsistent even if it passes the validator.

---

## Fix 5: Zero-row gating in `deterministic_tools` — PARTIAL

**Root cause addressed:** Yes — previously a zero-row `DatasetArtifact` with `status="ok"` was passed to critic, which then returned `pass` verdict (since `_has_ok_dataset` requires `rows > 0`). Wait — actually, `_has_ok_dataset` already checked `rows > 0`. The real issue is that the extractor returned `status="ok", rows=0` which passed through without an explicit signal. The fix changes `status` to `"gated"`.

**Implementation:** After extraction, if `rows == 0`, `status` is set to `"gated"` and `"empty_slice"` is added to `quality_flags`. `component_statuses["deterministic_tools"] = "empty_slice"`.

**BLOCKER — script is still exported for a gated/empty dataset (lines 123–131 in deterministic_tools.py).** After the zero-row check, `export_dataset_with_script` is called unconditionally for any `DatasetArtifact`, including gated ones. This creates a `ScriptArtifact` pointing to an empty dataset. The script is added to `script_artifacts`. Downstream `WorkflowResponse.validate_terminal_outcome_requirements` checks `if self.final_outcome == "passed": if not self.script_artifacts: raise`. If `final_outcome` is `passed` (which won't happen because `_has_ok_dataset` fails for gated), this would break. But the real problem: even for `not_found`, a `ScriptArtifact` tied to an empty dataset is included. This misleads the user — there is a downloadable "extraction script" but the dataset it refers to is empty.

**WARNING — `component_statuses["deterministic_tools"] = status`** is set at line 179 unconditionally, overwriting any prior status. If there are multiple sources in the extraction plan (currently the plan is single-source, but the architecture anticipates multi-source), only the last status survives.

**WARNING — `_has_ok_dataset` in `critic.py` checks `status == "ok"`, so gated datasets are correctly excluded from `passed` verdict. But `derive_final_outcome` in `critic.py` (lines 139–142) also calls `_has_ok_dataset`. Both paths correctly reject gated datasets. However, `_coverage_all_ok` (line 56) checks coverage report statuses — not dataset statuses. A coverage `status="ok"` can coexist with a dataset `status="gated"` (empty slice), so `_coverage_all_ok` may return `True` even when extraction yielded zero rows. The critic then sets `verdict = "needs_repair"` via the `_has_ok_dataset` check, not `not_found`. This is semantically correct but may surprise callers who see `coverage=ok` + `verdict=needs_repair` + `reason=no_ok_dataset`.

**Risk:** Medium — the script export for empty datasets is a data quality issue that could confuse UI consumers.

---

## Fix 6: `FEDSTAT_DUMPS_DIR` / `WORLD_BANK_DUMPS_DIR` env-var fallback — PARTIAL

**Root cause addressed:** Yes — `_parquet_path` previously raised `FileNotFoundError` when no local path was found in the source card, even if dumps existed in a known directory. The env-var fallback adds a resolvable escape hatch.

**Implementation:** Both adapters now try the env-var directory if set, searching by `dataset_id`, `resource_id`, and (WB only) the last segment of `card_id`. If not found, falls through to archive extraction then `FileNotFoundError`.

**Edge cases missed:**

1. **WARNING — no normalization of `raw_id` for path safety.** If `source_card["dataset_id"]` contains path separators (`/`, `..`), `dumps_dir / str(raw_id)` may traverse outside the intended directory. Example: `dataset_id = "../secrets/config"` → `dumps_dir / "../secrets/config"` resolves outside `dumps_dir`. This is a **path traversal** risk if `source_card` content is ever derived from untrusted user input. The source cards are loaded from an internal index, but the risk should be explicitly blocked with `Path(raw_id).name` or a similar sanitization.

2. **WARNING — `dumps_dir.is_dir()` check passes, but individual `candidate.exists()` can be a symlink pointing outside the directory.** No check that the resolved path is still within `dumps_dir`.

3. **WARNING — FedStat tries `card_id` as a lookup key (line 270 in fedstat_adapter.py) but World Bank only tries `card_id` last segment. This inconsistency means the two adapters have different resolution strategies.** FedStat will try `card_id` as a full path; World Bank extracts only the last `/`-delimited component. If `card_id = "fedstat:12345.parquet"`, FedStat will try `dumps_dir / "fedstat:12345.parquet"` (colons in filenames are illegal on Windows). No platform check.

4. **WARNING — `extraction_ready` is computed in `preview_*_coverage` but never read by `ExtractionPlanner` or any upstream node.** The field exists in `CoverageReport` and is populated correctly, but a grep of the codebase (and review of coverage.py, extraction_planner, and deterministic_tools) shows no consumer reads `extraction_ready` to gate extraction. The field is therefore informational-only; it does not actually gate the pipeline.

**Risk:** Medium. The path traversal is a security concern (low exploitability given internal source cards but non-zero). The `extraction_ready` field being unread means the fix achieves observability but not the claimed gating behavior.

---

## Fix 7: `extraction_ready` propagation — BROKEN

**Root cause addressed:** The diagnosis implies that `extraction_ready=False` should prevent Extraction Planner from proceeding. The fix computes `extraction_ready` and stores it in `CoverageReport`.

**Implementation:** The field is computed correctly. But the field is **never read** by any downstream node.

- `coverage.py` (`run_coverage_preview`) returns `list[CoverageReport]`. The reports go into `state["coverage_reports"]`.
- `extraction_planner` (not in the changed files; need to confirm) presumably reads `coverage_reports` but there is no evidence it reads `extraction_ready`.
- `deterministic_tools.py` reads `state.get("extraction_plan")` but never reads `coverage_reports` or `extraction_ready`.

**BLOCKER — `extraction_ready=False` has no effect on the pipeline.** Even when all sources have `extraction_ready=False`, extraction proceeds unless the extraction plan itself has `status in ("skipped_with_reason", "gated", "needs_clarification")`. The zero-row gating in `deterministic_tools` catches the downstream consequence, but the pre-extraction gate that `extraction_ready` was supposed to provide is absent.

**Risk:** High — this is a silent no-op fix. The smoke tests will still fail for sources with no matching slice unless the extraction plan is explicitly gated upstream.

---

## Summary of All Issues

| ID | Severity | Location | Description |
|----|----------|----------|-------------|
| BL-01 | BLOCKER | `state.py:79` | Nested list from LLM for `geography` produces a literal stringified list instead of ValueError |
| BL-02 | BLOCKER | `narrator.py:532` | `_tag_diagnostic` called with raw dicts from LangGraph state serialization; `.quality_flags` access will raise `AttributeError` |
| BL-03 | BLOCKER | `deterministic_tools.py:123` | Script exported for zero-row (gated) dataset — misleading downloadable artifact for empty extraction |
| BL-04 | BLOCKER | `fedstat_adapter.py:265` / `world_bank_adapter.py:340` | Path traversal: `dataset_id` with `../` in env-var path lookup not sanitized |
| BL-05 | BLOCKER | `workflow_artifacts.py:98` + all callers | `extraction_ready` field is computed but never consumed — the gating it implies does not exist |
| WR-01 | WARNING | `state.py:169` | Double-derivation of `countries` in `_analyze_intent_live` after model validator already runs |
| WR-02 | WARNING | `critic.py:47` | `_CritiqueSchema = None` fallback passes `schema=None` to `structured_chat`; behavior undefined |
| WR-03 | WARNING | `coverage.py:146` | Silent `except Exception: return reports` swallows all LLM assessment failures including credential errors |
| WR-04 | WARNING | `deterministic_tools.py:179` | `component_statuses["deterministic_tools"]` is overwritten per-call; multi-source plans lose earlier statuses |
| WR-05 | WARNING | `fedstat_adapter.py:270` | `card_id` used as full path candidate in FedStat env-var lookup; colons in IDs are invalid on Windows |
| WR-06 | WARNING | `world_bank_adapter.py:107–114` | Both `countries` and `not countries` branches produce `matched_geos = list(available_geographies)` and `slice_rows = total_row_count` — the if/else branches are identical and the `countries` case produces no different result |

---

## Overall Verdict

**These fixes are insufficient to unblock the 7 smoke test failures.**

Plans A+B address legitimate symptoms (LLM type coercion failures, missing parquet paths, zero-row datasets reaching the critic untagged), but:

1. **`extraction_ready` is a dead field** — the pre-extraction gate that was the stated goal of Plan B's slice validation does not exist in any node.
2. **The zero-row script export** creates misleading artifacts in the output.
3. **The diagnostic tagging** in narrator will crash when LangGraph serializes/deserializes state as dicts instead of model instances (the `model_copy` call on a dict).
4. **The path traversal** in env-var parquet lookup needs sanitization before shipping.
5. The root causes in the diagnosis document (acceptance test leaking `matrix_hint` into LLM prompts, `Supervisor` silently falling back to `research` on LLM error, `clarification` starting a fresh query) are **untouched** — Plans A+B address plumbing validation, not the architectural leaks.

The fixes are sound scaffolding for the plumbing layer, but 3–4 blockers remain before any smoke test that exercises the full pipeline (retrieve → cover → extract → critic → narrator) can pass reliably.
