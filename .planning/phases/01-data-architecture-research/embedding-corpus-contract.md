# Embedding Corpus Contract

Updated: 2026-05-10

This contract defines the source-card chunks consumed by later retrieval and indexing plans. The corpus is source-bound metadata only: it is not raw numeric data, not raw numeric series, and not generated answer text.

## Provider Target

- Document model target: Yandex AI Studio `text-search-doc`.
- Query model target: Yandex AI Studio `text-search-query`.
- Environment contract:
  - `YANDEX_EMBEDDING_DOC_MODEL=emb://<folder_id>/text-search-doc/latest`
  - `YANDEX_EMBEDDING_QUERY_MODEL=emb://<folder_id>/text-search-query/latest`
  - `YANDEX_EMBEDDING_DIMENSIONS=256`
- If credentials are absent, dense indexing must record a gated skip while preserving the same local source-card chunks and manifest.

## Document Query Split

- Source-card chunks are embedded with `text-search-doc`.
- User queries are embedded with `text-search-query`.
- Retrieval joins query results back to `card_id`, then to the source-card catalog.

## Source-Card Chunks

Each `EmbeddingDocument` represents one deterministic source-card chunk. Its `embedding_text` is built from stable metadata fields:

- title or name;
- source family;
- dataset, indicator, package, or resource codes;
- geography and period coverage hints;
- units and dimensions;
- source URL or resource URL;
- descriptive metadata such as methodology, topics, organization, license, and source notes.

The source-card chunks must exclude raw table values, raw numeric series, generated factual answers, and unsupported numeric claims from an LLM.

## Chunk Identity

Required fields:

- `source_id`
- `card_id`
- `chunk_id`
- `source_family`
- `language`
- `metadata_version`
- `input_format_version`
- `content_hash`
- `embedding_text`
- `provenance_url`
- `resource_url`
- `builder_source`

`chunk_id` is derived from `card_id`, `metadata_version`, and the leading prefix of the document `content_hash`.

## Hashing And Versioning

- `metadata_version`: `source-card-v1`
- `input_format_version`: `source-card-embedding-text-v1`
- `content_hash`: SHA-256 over the exact UTF-8 `embedding_text`.
- Corpus manifest `content_hash`: SHA-256 over the ordered JSONL embedding corpus bytes.
- Version changes must force a new manifest and later index compatibility check.

## Local Artifact Boundaries

Generated runtime artifacts are written under `.local/dataagent/phase1/` and are not committed. Committed manifests live in `.planning/phases/01-data-architecture-research/`.

Expected local artifacts:

- `.local/dataagent/phase1/source-cards.json`
- `.local/dataagent/phase1/source-catalog.sqlite`
- `.local/dataagent/phase1/embedding-corpus.jsonl`

Expected committed manifests:

- `.planning/phases/01-data-architecture-research/source-cards-manifest.json`
- `.planning/phases/01-data-architecture-research/source-catalog-manifest.json`
- `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json`

## Manifest Fields

`EmbeddingCorpusManifest` records:

- provider and document/query model hints;
- `metadata_version` and `input_format_version`;
- local artifact path and committed manifest path;
- chunk count and source-family coverage;
- corpus `content_hash`;
- per-chunk hashes;
- provider hints for the later Qdrant indexing plan.
