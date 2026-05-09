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
- The assistant is source-bound: numbers must come from deterministic code or trusted source adapters, never from LLM memory.
- CKAN is a trusted NSED catalog API, not general web search. Use it through bounded package/resource search and cache only promoted metadata.
- Keep local secrets in `.env`; never commit API keys.
- Prefer traceable artifacts: research notes, source candidates, rejection reasons, generated SQL/code, extraction logs, and verification results.
- Streamlit is the first demo UI target. The UI must expose the state machine, trace, artifacts, and user feedback/fix requests.

