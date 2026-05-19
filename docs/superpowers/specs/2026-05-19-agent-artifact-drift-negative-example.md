# Negative Example: Agent Artifact Drift Under Context Pressure - 2026-05-19

Status: durable workflow-refactor guardrail.

This artifact records a recurring failure mode in agent-assisted architecture
work. It is intentionally concrete because future agents treat specs and ADRs as
near-executable instructions.

## Failure Pattern

The user discusses architecture over several turns and asks the agent to capture
the final decision in durable artifacts. The conversation reaches a clear
decision, but older artifacts still contain obsolete alternatives or softer
language. The agent then writes a new artifact that mixes:

- the final decision from the discussion;
- stale options from earlier artifacts;
- migration convenience shortcuts from the current codebase;
- compressed-context assumptions.

The resulting artifact looks plausible, but it contains a subtle contradiction.
A later coding agent follows the contradictory phrase literally and implements
the wrong architecture.

## Concrete Incident

The accepted decision for pre-retrieval workflow was:

```text
Intent Analyst -> Retrieval Planner -> Source Scouts
```

The accepted boundary was:

- Intent Analyst produces durable semantic `UserIntentArtifact`.
- Retrieval Planner is a live LLM structured-output node that turns intent into
  metadata-oriented `RetrievalInput` probes.
- Deterministic code inside Retrieval Planner may only validate/post-process the
  LLM output: schema validation, stable IDs, explicit constraint preservation,
  safety bounds, and traceable raw-query fallback.
- Deterministic-only probe generation is not accepted.

The bad artifact text said the Retrieval Planner "can be implemented as a
deterministic transformation over LLM-produced fields." That contradicted the
accepted boundary. A later implementation then produced a deterministic-only
retrieval planner artifact instead of calling the live/mock structured LLM path
for primary probe generation.

## Why This Was Wrong

The phrase collapsed two different responsibilities:

- semantic search-strategy design, which belongs to the LLM Retrieval Planner;
- mechanical validation/post-processing, which may be deterministic.

For this project, probe choice, aliases, official terms, and source-family search
wording are not mechanical transformations. They are the Retrieval Planner's
main work and must be traceable as LLM structured output.

## Required Agent Behavior

Before writing a "final" architecture artifact after a long discussion, the agent
must perform an artifact drift check:

1. Search all required workflow-refactor artifacts for the key disputed terms.
2. Identify stale alternatives and open questions that the discussion resolved.
3. Replace or explicitly supersede stale language instead of carrying it forward.
4. Add "Not Doing" bullets for implementation shortcuts that would violate the
   decision.
5. Add acceptance tests that fail if the shortcut is implemented.
6. Update `.planning/STATE.md` when the failure mode affects future work.

For this incident, the minimum search terms were:

```text
deterministic planner
deterministic transformation
deterministic-only
if implemented as an LLM node
Retrieval Planner
SearchProbe
RetrievalInput
```

## Required Implementation Gate

The Retrieval Planner slice is not accepted unless tests prove:

- the planner calls the live/mock Qwen/Yandex structured-output path for primary
  `RetrievalInput` generation;
- deterministic-only probe generation cannot satisfy the slice acceptance tests;
- deterministic code is limited to validation/post-processing/fallback behavior;
- trace output distinguishes LLM-produced probes from mechanical post-processing.

## General Rule

When the user says "capture the final spec based on the discussion," the agent
must not merely summarize the newest message. It must reconcile the full artifact
set and remove or supersede obsolete alternatives. Ambiguous compatibility
language is dangerous because future agents implement it as permission.
