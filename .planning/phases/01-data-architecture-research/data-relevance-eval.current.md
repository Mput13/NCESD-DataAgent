# Data Relevance Evaluation

The Phase 1 quality gate prioritizes source relevance, source rejection, qdrant/dense status, coverage, deterministic extraction, no-data honesty, and trace completeness. Gated embedding or extraction states are explicit and do not count as retrieval or extraction success.

## Aggregate

- Total cases: 20
- Passed: 0
- Failed: 0
- Gated: 20
- Qdrant status: `gated_skip`
- Extraction probe status: `skipped_with_reason`

## Cases

| Case | Category | Status | Score | Reason |
|---|---|---:|---:|---|
| GC-001 | simple | gated | 4 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-002 | simple | gated | 2 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-003 | comparative | gated | 1 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-004 | comparative | gated | 2 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-005 | research | gated | 1 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-006 | research | gated | 2 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-007 | derived_metric | gated | 2 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-008 | derived_metric | gated | 1 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-009 | ambiguous | gated | 2 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-010 | ambiguous | gated | 2 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-011 | no_data | gated | 2 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-012 | no_data | gated | 2 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-013 | simple | gated | 2 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-014 | research | gated | 2 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-015 | comparative | gated | 1 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-016 | simple | gated | 2 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-017 | research | gated | 1 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-018 | no_data | gated | 2 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-019 | research | gated | 2 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
| GC-020 | simple | gated | 2 | deterministic extraction probes are skipped_with_reason; qdrant/dense retrieval gated by embedding credentials; retrieval row records dense_status=gated_skip |
