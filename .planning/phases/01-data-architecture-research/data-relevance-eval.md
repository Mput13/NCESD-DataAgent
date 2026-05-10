# Data Relevance Evaluation

The Phase 1 quality gate prioritizes source relevance, source rejection, qdrant/dense status, coverage, deterministic extraction, no-data honesty, and trace completeness. Gated embedding or extraction states are explicit and do not count as retrieval or extraction success.

## Aggregate

- Total cases: 20
- Passed: 0
- Failed: 12
- Gated: 8
- Qdrant status: `gated_skip`
- Extraction probe status: `skipped_with_reason`

## Cases

| Case | Category | Status | Score | Reason |
|---|---|---:|---:|---|
| GC-001 | simple | gated | 5 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-002 | simple | gated | 3 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-003 | comparative | gated | 1 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-004 | comparative | failed | 0 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials |
| GC-005 | research | failed | 0 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials |
| GC-006 | research | failed | 0 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials |
| GC-007 | derived_metric | failed | 0 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials |
| GC-008 | derived_metric | failed | 0 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials |
| GC-009 | ambiguous | gated | 2 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-010 | ambiguous | failed | 0 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials |
| GC-011 | no_data | gated | 4 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-012 | no_data | failed | 0 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials |
| GC-013 | simple | gated | 2 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-014 | research | failed | 0 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials |
| GC-015 | comparative | failed | 0 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials |
| GC-016 | simple | failed | 0 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials |
| GC-017 | research | failed | 0 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials |
| GC-018 | no_data | failed | 0 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials |
| GC-019 | research | gated | 2 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-020 | simple | gated | 2 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
