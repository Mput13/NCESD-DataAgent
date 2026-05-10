# Embedding / Retrieval Metrics: Human-Readable Report

## One-Sentence Summary

The Phase 1 embedding index is operational, but the current retrieval metric mostly proves that the system often finds the right source family, not that it reliably finds the exact dataset needed for a final answer.

## What Was Measured

The current retrieval evaluation runs each golden-case query through the Phase 1 hybrid retrieval stack:

```text
query
-> lexical BM25-style search over source-card text
-> dense Qdrant search with Yandex query embeddings when available
-> simple fallback reranking
-> top candidate written to retrieval eval CSV
```

The eval then checks whether the top accepted candidate belongs to one of the expected source families for that golden case.

Example:

```text
Query: "Какой ВВП России в 2024 году?"
Expected source families: FedStat, World Bank
Top candidate source family: FedStat
Metric result: match
```

This is useful, but it is a coarse check. It does not prove that the exact GDP indicator was selected.

## What The Current Numbers Mean

### Source Family Match

The previously discussed `19/20 = 95%` number means:

```text
In 19 of 20 golden cases, the top accepted candidate came from an expected source family.
```

It does not mean:

```text
In 19 of 20 cases, the exact correct dataset or indicator was selected.
```

This difference matters. A candidate from FedStat can be broadly related to GDP but still be the wrong indicator for answering the user's question.

### Dense Retrieval Ready

The `20/20 = 100%` dense-ready number means:

```text
For all 20 eval rows, the dense retrieval path was available and not gated.
```

It does not mean:

```text
Dense retrieval produced the best candidate in all 20 cases.
```

In the control run, dense Qdrant was the top retrieval mode in only some cases. The metric proves the dense path works operationally; it does not by itself prove dense quality.

## Why The Existing Metric Is Too Soft

The current metric is generous for four reasons:

1. It checks source family, not exact dataset or indicator.
2. Some golden cases accept several source families, so the match can be easy.
3. The fallback reranker receives expected source families during eval, which gives it a hint.
4. It does not check whether the candidate can actually pass coverage and deterministic extraction.

So the current metric is good for infrastructure readiness, but too weak for real product readiness.

## Better Practical Metric

For Phase 2, the most important retrieval question should be:

```text
Did retrieval put an extraction-ready source in the top results?
```

A source is extraction-ready if the next workflow steps can use it:

- Coverage & Schema can check geography, period, unit, and dimensions.
- Deterministic Tools can extract rows from the source.
- Narrator can cite it without inventing numbers.

## Recommended New Metrics

| Metric | Plain Meaning | Why It Matters |
|---|---|---|
| Top-1 source family match | Top result is from the expected family, such as FedStat or World Bank | Coarse routing sanity check |
| Top-1 exact source match | Top result is the exact expected dataset/card/indicator | Measures whether the first choice is actually usable |
| Top-3 exact source recall | A correct source appears in the first 3 candidates | Useful because the workflow can inspect a shortlist |
| Top-5 extraction-ready recall | An extractable correct source appears in the first 5 candidates | Best practical retrieval metric for the product |
| Dense-only top-k recall | Dense search alone finds the right source | Measures embedding quality directly |
| Lexical-only top-k recall | Keyword search alone finds the right source | Baseline for comparison |
| Hybrid lift | Hybrid beats lexical-only or dense-only | Shows whether combining methods helps |
| No-data false positive rate | Unsupported queries do not get confident irrelevant sources | Protects against misleading answers |
| Near-miss rejection rate | Similar but wrong sources are rejected | Prevents plausible-looking wrong answers |

## Suggested Strict Scoring Levels

| Level | Meaning |
|---|---|
| L0 | Correct source family |
| L1 | Relevant dataset or indicator appears in top 5 |
| L2 | Relevant dataset or indicator appears in top 3 |
| L3 | Correct source is top 1 |
| L4 | Correct source is top 1 and coverage-compatible |
| L5 | Correct source is top 1, coverage-compatible, and deterministic extraction succeeds |

The current `source_family_match` metric is mostly an L0 metric. For real use, Phase 2 should target L2 to L4 for retrieval, and L5 for final end-to-end accepted cases.

## Practical Interpretation For The Project

The Phase 1 result is encouraging:

- The embedding/Qdrant path can run.
- The system can evaluate all golden cases.
- Hybrid retrieval often routes to a plausible source family.
- The workflow records evidence instead of silently pretending success.

But it is not enough to claim answer quality:

- Exact source selection is not yet measured.
- Coverage compatibility is not yet measured.
- Deterministic extraction success is not part of the retrieval metric.
- A wrong FedStat indicator may still count as a current source-family match.

## Recommended Reporting Language

Use this careful wording:

```text
Phase 1 demonstrates operational dense retrieval and coarse source-family routing over the prepared source-card corpus. In a controlled run, the top accepted candidate matched an expected source family for 19 of 20 golden cases, and the dense path was available for all 20 cases. This does not yet prove exact dataset selection or final answer correctness. Phase 2 should replace this soft metric with top-k extraction-ready recall and exact source/indicator matching.
```

Avoid this wording:

```text
Retrieval accuracy is 95%.
```

That overstates what was measured.

## Next Step

Create a stricter retrieval eval file where each case defines:

- acceptable source families;
- acceptable card IDs or indicator IDs;
- required concepts;
- near-miss rejection rules;
- required coverage hints;
- whether the case should answer, clarify, or return not found.

Then run each query in three modes:

```text
lexical_only
dense_only
hybrid
```

This will tell us whether embeddings are truly helping real user workflows, not just whether the vector index is switched on.
