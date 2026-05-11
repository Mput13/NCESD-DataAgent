---
phase: 01-data-architecture-research
plan: 02
subsystem: source-catalog
tags: [source-cards, sqlite, embedding-corpus, ckan, fedstat, world-bank]

requires:
  - phase: 01-data-architecture-research
    provides: Plan 01 evaluation foundation, golden cases, and source-bound rubric
provides:
  - Typed source-card, evidence-bundle, embedding-document, and corpus-manifest contracts
  - Deterministic FedStat, World Bank, and CKAN source-card builders
  - Local SQLite catalog for source cards, coverage hints, embedding chunks, and rejection metadata
  - Generated source-card, source-catalog, and embedding-corpus manifests
affects: [retrieval, qdrant-indexing, coverage-preview, deterministic-extraction, streamlit-demo]

tech-stack:
  added: []
  patterns:
    - Metadata-only embedding documents with stable content hashes
    - Bounded CKAN catalog discovery through trusted NSED APIs
    - SQLite catalog interface queryable by later DuckDB/Qdrant retrieval work

key-files:
  created:
    - .planning/phases/01-data-architecture-research/embedding-corpus-contract.md
    - .planning/phases/01-data-architecture-research/source-cards-manifest.json
    - .planning/phases/01-data-architecture-research/source-catalog-manifest.json
    - .planning/phases/01-data-architecture-research/embedding-corpus-manifest.json
    - app/catalog/__init__.py
    - app/catalog/source_catalog.py
    - scripts/build_source_catalog.py
    - scripts/build_embedding_corpus.py
    - tests/test_source_catalog_and_corpus.py
  modified:
    - .planning/phases/01-data-architecture-research/data-inventory.md
    - app/artifacts/source_cards.py
    - app/data/source_card_builders.py
    - scripts/build_source_cards.py
    - tests/test_source_cards_contract.py
    - tests/test_source_card_builders.py

key-decisions:
  - "Use source-card metadata as the only embedding input; raw numeric observations and generated answer text stay out of the corpus."
  - "Use SQLite for the local catalog while keeping it DuckDB-compatible for later deterministic extraction and catalog queries."
  - "Reuse and harden existing partial 01-02 task commits instead of rewriting equivalent accepted work."

patterns-established:
  - "SourceCandidateCard.to_embedding_chunk() produces stable EmbeddingDocument records keyed by content hash."
  - "Builder scripts write runtime artifacts under .local/dataagent/phase1/ and committed manifests under the phase directory."
  - "Catalog manifests must include table counts and queryability checks, not just artifact paths."

requirements-completed:
  - SRCH-03
  - SRCH-04

duration: 5 min
completed: 2026-05-10
---

# Phase 01 Plan 02: Prepared Data Contract Summary

**FedStat, World Bank, and CKAN source cards now share a typed metadata contract, SQLite catalog, and deterministic embedding-corpus manifest**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-10T00:49:01Z
- **Completed:** 2026-05-10T00:53:37Z
- **Tasks:** 2
- **Files modified:** 15

## Accomplishments

- Added explicit `EmbeddingDocument` and `EmbeddingCorpusManifest` contracts plus `embedding-corpus-contract.md` for Yandex `text-search-doc` / `text-search-query` split, hashing, metadata versioning, and local artifact boundaries.
- Built a deterministic source-card pipeline covering FedStat, World Bank, and bounded CKAN discovery, with committed `source-cards-manifest.json`.
- Added a SQLite `SourceCatalog` storing `source_cards`, `coverage_hints`, `embedding_chunks`, and `rejection_metadata`, verified by `source-catalog-manifest.json`.
- Added an embedding corpus generator that emits metadata-only JSONL chunks and `embedding-corpus-manifest.json` without calling an embedding API.

## Task Commits

Each task was committed atomically:

1. **Task 1: Define source-card, evidence-bundle, and embedding document contracts**
   - `aca40f5` test: add failing source card contract tests
   - `554a0b3` feat: implement source card artifact contracts
   - `04e6d52` test: add failing embedding chunk contract test
   - `ba0cbbf` feat: add source card embedding chunk contract
   - `77e5bd8` test: add failing embedding manifest contract tests
   - `972e5be` feat: finalize embedding corpus contracts
2. **Task 2: Build deterministic inventory, source-card builders, local catalog, and embedding corpus generator**
   - `6c95372` test: add failing source card builder tests
   - `a8856d9` feat: build deterministic source card inventory
   - `7c163d7` test: add failing catalog and corpus tests
   - `e505ac4` feat: build source catalog and embedding corpus

## Files Created/Modified

- `app/artifacts/source_cards.py` - Pydantic v2 contracts for source cards, evidence bundles, embedding documents, and corpus manifests.
- `app/data/source_card_builders.py` - FedStat, World Bank, and CKAN source-card builders.
- `app/catalog/source_catalog.py` - SQLite catalog interface for cards, coverage hints, chunks, and rejection metadata.
- `scripts/build_source_cards.py` - Deterministic source-card builder and manifest writer.
- `scripts/build_source_catalog.py` - Local SQLite catalog builder and queryability manifest writer.
- `scripts/build_embedding_corpus.py` - Metadata-only embedding corpus JSONL and manifest writer.
- `.planning/phases/01-data-architecture-research/data-inventory.md` - Inventory and generated artifact handoff.
- `.planning/phases/01-data-architecture-research/*-manifest.json` - Source-card, catalog, and embedding-corpus manifests.
- `tests/test_source_cards_contract.py`, `tests/test_source_card_builders.py`, `tests/test_source_catalog_and_corpus.py` - Contract, builder, catalog, and corpus tests.

## Verification

Commands run successfully:

```bash
PATH="$PWD/.local/bin:$PATH" python3 -m pytest
PATH="$PWD/.local/bin:$PATH" rg -n "class SourceCandidateCard|class EvidenceBundle|class EmbeddingDocument|class EmbeddingCorpusManifest|ckan_discovery|methodology_match|content_hash|metadata_version" app/artifacts/source_cards.py
PATH="$PWD/.local/bin:$PATH" rg -n "text-search-doc|text-search-query|content_hash|metadata_version|source-card chunks|not raw numeric" .planning/phases/01-data-architecture-research/embedding-corpus-contract.md
PATH="$PWD/.local/bin:$PATH" python scripts/build_source_cards.py --manifest .planning/phases/01-data-architecture-research/source-cards-manifest.json
PATH="$PWD/.local/bin:$PATH" python scripts/build_source_catalog.py --source-cards-manifest .planning/phases/01-data-architecture-research/source-cards-manifest.json --manifest .planning/phases/01-data-architecture-research/source-catalog-manifest.json
PATH="$PWD/.local/bin:$PATH" python scripts/build_embedding_corpus.py --source-cards-manifest .planning/phases/01-data-architecture-research/source-cards-manifest.json --manifest .planning/phases/01-data-architecture-research/embedding-corpus-manifest.json
```

Manifest validation printed `11 11`: 11 source cards and 11 embedding chunks. The source-card manifest includes FedStat, World Bank, and CKAN; the catalog queryability check passed.

## Decisions Made

- Embedding text is built only from source-card metadata fields, never raw numeric series or generated answer text.
- Runtime artifacts remain under `.local/dataagent/phase1/`; committed manifests are the durable handoff to later plans.
- SQLite is the first local catalog implementation because it is in the standard library and remains queryable by DuckDB later.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added explicit revised embedding contract symbols**
- **Found during:** Task 1 acceptance verification
- **Issue:** Existing partial work exposed a source-card embedding chunk but not the explicit `EmbeddingDocument` and `EmbeddingCorpusManifest` names required by the revised plan.
- **Fix:** Added failing tests, implemented the public models, preserved the existing `SourceCardEmbeddingChunk` alias, and wrote `embedding-corpus-contract.md`.
- **Files modified:** `app/artifacts/source_cards.py`, `tests/test_source_cards_contract.py`, `.planning/phases/01-data-architecture-research/embedding-corpus-contract.md`
- **Verification:** `python3 -m pytest tests/test_source_cards_contract.py`; Task 1 `rg` acceptance markers
- **Committed in:** `77e5bd8`, `972e5be`

**2. [Rule 3 - Blocking] Completed missing manifest/catalog/corpus builders**
- **Found during:** Task 2 acceptance verification
- **Issue:** Existing partial work had source-card builders but no catalog interface, catalog builder, embedding corpus builder, or committed manifests, blocking the plan verification command.
- **Fix:** Added `SourceCatalog`, catalog and corpus scripts, deterministic manifest writing, and generated the required committed manifests.
- **Files modified:** `app/catalog/source_catalog.py`, `scripts/build_source_cards.py`, `scripts/build_source_catalog.py`, `scripts/build_embedding_corpus.py`, plan manifests, and `data-inventory.md`
- **Verification:** `python3 -m pytest`; full plan builder/manifest validation command
- **Committed in:** `7c163d7`, `e505ac4`

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both fixes were required to satisfy the revised executable acceptance criteria. No architectural change was introduced.

## Issues Encountered

- The repository already contained clean, partial 01-02 TDD commits. I verified and reused them, then added corrective red/green commits for the revised plan gaps.

## Known Stubs

- `app/data/source_card_builders.py:203` and `app/data/source_card_builders.py:224` intentionally set CKAN `geography=[]` and `dimensions=[]` because package metadata alone does not guarantee geographic or dimensional coverage. Later coverage/extraction plans should fill these only after bounded resource inspection or deterministic extraction.

## User Setup Required

None - no external service configuration required. CKAN access used the public trusted NSED catalog API.

## Next Phase Readiness

Ready for `01-03-PLAN.md`: later Qdrant/indexing work can consume `.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json`, the local `.local/dataagent/phase1/embedding-corpus.jsonl`, and the queryable SQLite catalog without re-reading raw dump structures by default.

## Self-Check: PASSED

- Found created artifacts: `embedding-corpus-contract.md`, `source-cards-manifest.json`, `source-catalog-manifest.json`, `embedding-corpus-manifest.json`, `app/catalog/source_catalog.py`, `scripts/build_source_catalog.py`, `scripts/build_embedding_corpus.py`, and `01-02-SUMMARY.md`.
- Found task commits: `aca40f5`, `554a0b3`, `04e6d52`, `ba0cbbf`, `77e5bd8`, `972e5be`, `6c95372`, `a8856d9`, `7c163d7`, `e505ac4`.

---
*Phase: 01-data-architecture-research*
*Completed: 2026-05-10*
