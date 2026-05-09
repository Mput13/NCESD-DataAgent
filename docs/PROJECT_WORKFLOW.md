# Project Workflow: GSD + Source-Bound DataAgent

GSD is the main development workflow for this repository. It gives the project a stable memory layer (`.planning/*`), phase-based execution, explicit verification, and a clean way to keep architectural decisions visible to reviewers.

## Why GSD Fits This Project

The DataAgent task is not a single coding ticket. It combines source research, architecture, data normalization, retrieval quality, deterministic extraction, UI traceability, and demo evaluation. GSD is useful here because it forces every large change through a visible loop:

1. Discuss assumptions and unresolved decisions.
2. Plan small implementation tasks.
3. Execute only planned work.
4. Verify against requirements and real cases.
5. Keep durable planning artifacts in `.planning/`.

This matters for the case study because reviewers will inspect not only the working product, but also the clarity of the architecture and engineering process.

## Commands We Use

| Step | Command | Purpose |
|---|---|---|
| Rebuild codebase context | `$gsd-map-codebase` | Refresh GSD's understanding after major repo changes. |
| Initialize or rebuild planning | `$gsd-new-project` | Build project context, requirements, and roadmap. |
| Clarify a phase | `$gsd-discuss-phase <N>` | Capture choices before planning implementation. |
| Plan a phase | `$gsd-plan-phase <N>` | Produce small verifiable plans. |
| Execute a phase | `$gsd-execute-phase <N>` | Implement planned tasks. |
| Verify work | `$gsd-verify-work <N>` | Check that the phase actually works. |
| Inspect next step | `$gsd-progress --next` | Let GSD identify the next workflow action. |

## Local Installation

GSD was installed globally for Codex with:

```powershell
npx get-shit-done-cc@latest --codex --global --config-dir C:\Users\HONOR\.codex
```

The installer placed Codex skills in `C:\Users\HONOR\.codex\skills\gsd-*`, agent configs in `C:\Users\HONOR\.codex\agents`, hooks in the Codex config directory, and configured non-Anthropic model resolution with `resolve_model_ids: "omit"`.

Project-level GSD settings live in `.planning/config.json`.

## How This Changes Our Work

We should stop treating architecture notes as loose chat output. If a choice affects implementation, it should land in one of these places:

- `.planning/STATE.md` for current state and decisions.
- `.planning/PROJECT.md` for product scope and durable constraints.
- `.planning/ROADMAP.md` for phase boundaries.
- `docs/ARCHITECTURE_STACK.md` for the current technical architecture.
- Phase-specific GSD files under `.planning/phases/` once phase planning starts.

For this DataAgent, verification is not just "tests pass". A phase is not done until it demonstrates the source-bound contract:

- relevant sources were found or honestly rejected;
- numeric values came from deterministic code;
- generated artifacts include citations and trace;
- user-facing output can explain what was searched, selected, and rejected;
- failure cases return a clear "data not found" path instead of hallucinating.

## Important Adaptation

GSD is the development workflow, not the runtime architecture of the DataAgent. The application can still use LangGraph, source adapters, DuckDB, CKAN, embeddings, Streamlit, and deterministic extraction. GSD only governs how we plan, implement, and verify those pieces.

