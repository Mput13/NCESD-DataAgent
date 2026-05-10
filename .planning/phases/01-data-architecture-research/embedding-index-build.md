# Embedding Index Build

- Status: `gated_skip`
- Dense status: `gated_skip`
- Vector store: `qdrant_client` / Qdrant
- QDRANT_MODE: `local`
- QDRANT_PATH: `.local/qdrant`
- QDRANT_URL: ``
- QDRANT_COLLECTION / collection_name: `phase1_source_cards`
- YANDEX_EMBEDDING_DOC_MODEL: `emb://<folder_id>/text-search-doc/latest`
- YANDEX_EMBEDDING_QUERY_MODEL: `emb://<folder_id>/text-search-query/latest`
- YANDEX_EMBEDDING_DIMENSIONS: `256`
- Chunk count: `11`
- Corpus hash: `1853358e6135e2843127fee929de50e597a4ad8a14ea5d746795df9c9aadda09`
- Metadata version: `source-card-v1`
- Vector count: `0`

## Credential Gate

Vector population was gated_skip because embedding credentials were missing.
- Missing env vars: `YANDEX_AI_STUDIO_API_KEY or YANDEX_EMBEDDING_API_KEY`
- Qdrant mode/path or URL and collection configuration were still materialized in the manifest.

## Rebuild

```bash
PATH="$PWD/.local/bin:$PATH" python scripts/build_embedding_index.py --corpus-manifest .planning/phases/01-data-architecture-research/embedding-corpus-manifest.json --manifest .planning/phases/01-data-architecture-research/embedding-index-manifest.json --build-log .planning/phases/01-data-architecture-research/embedding-index-build.md
```
