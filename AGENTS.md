# Project Workflow For Codex

This repository uses GSD as the primary planning and execution workflow.

## Default Loop

Use the GSD loop for non-trivial work:

1. `$gsd-map-codebase` when the codebase or architecture context has changed.
2. `$gsd-new-project` only when rebuilding the project planning context from scratch.
3. `$gsd-discuss-phase <N>` before implementation to capture unresolved decisions.
4. `$gsd-plan-phase <N>` to create small, verifiable implementation plans.
5. `$gsd-execute-phase <N>` to implement planned work.
6. `$gsd-verify-work <N>` before considering a phase complete.

For small direct fixes, keep the change scoped, update `.planning/STATE.md` when the decision matters, and preserve the same evidence-first discipline.

## Project-Specific Rules

- Treat `.planning/PROJECT.md`, `.planning/ROADMAP.md`, `.planning/REQUIREMENTS.md`, and `.planning/STATE.md` as durable project memory.
- The roadmap now explicitly defines Phase 1 as accepted infrastructure and Phase 2 as the full jury MVP phase. Do not infer additional numbered follow-up phases unless the roadmap is explicitly changed again.
- Execute work single-track through the canonical phase plans. Do not recreate a three-person Core/Data/UI owner split or owner-specific onboarding artifacts.
- The `research` slug is historical. Phase 1 is implementation-oriented: produce code, scripts, tests, evidence artifacts, and summaries where the plans require them.
- Phase 2 must target all 20 golden cases. Do not lower acceptance to a small demo subset; staged implementation is allowed, but final acceptance is all cases with correct pass / needs_clarification / not_found outcomes and no stale/gated/skipped final states.
- The assistant is source-bound: numbers must come from deterministic code or trusted source adapters, never from LLM memory.
- CKAN is a trusted NSED catalog API, not general web search. Use it through bounded package/resource search and cache only promoted metadata.
- Keep local secrets in `.env`; never commit API keys.
- Prefer traceable artifacts: research notes, source candidates, rejection reasons, generated SQL/code, extraction logs, and verification results.
- The web UI (`app/web/`) is the demo target. It exposes the state machine, trace, artifacts, and user feedback/fix requests via the built-in HTTP server with SSE streaming.
