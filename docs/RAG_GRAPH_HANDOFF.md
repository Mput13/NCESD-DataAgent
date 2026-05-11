# Graph-Aware RAG Handoff

Этот гайд для человека, который подтягивает нашу RAG-систему из ветки Phase 2 и уже имеет готовые embeddings / Qdrant snapshot.

Важно: не используйте ветку `experiment`. Актуальная работа с graph-aware RAG находится в ветке:

```bash
codex/phase-2-jury-mvp-planning
```

## Что реализовано

Это не отдельный "академический GraphRAG" с graph embeddings и community summaries. В продукте реализован graph-aware hybrid retrieval:

- dense search через Qdrant collection `phase1_source_cards`;
- lexical BM25 по `embedding_text`;
- graph-first вход по извлеченным из запроса сущностям/алиасам;
- graph expansion от найденных карточек;
- RRF-смешивание результатов.

Граф строится детерминированно из metadata source cards. Отдельную graph DB поднимать не нужно.

Ключевые файлы:

- `app/retrieval/hybrid_retrieval.py`
- `app/retrieval/graph_store.py`
- `app/retrieval/query_understanding.py`
- `scripts/evaluate_retrieval_modes.py`

## 1. Подтянуть ветку

```bash
git fetch origin
git switch codex/phase-2-jury-mvp-planning
git pull origin codex/phase-2-jury-mvp-planning
```

Проверить, что graph-aware RAG коммит на месте:

```bash
git log --oneline -5
```

В истории должен быть коммит:

```text
c12f771 feat: add graph-aware retrieval layer
```

## 2. Установить зависимости

```bash
python -m pip install -r requirements.txt
```

Если используется virtualenv:

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 3. Настроить `.env`

Создайте локальный `.env` по `.env.example`. Секреты не коммитить.

Минимально нужны:

```env
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=phase1_source_cards
QDRANT_MODE=remote
QDRANT_DISTANCE=cosine

YANDEX_API_KEY=<your-key>
YANDEX_AI_STUDIO_API_KEY=<your-key>
YANDEX_EMBEDDING_API_KEY=<your-key>
YANDEX_FOLDER_ID=<your-folder-id>

YANDEX_AI_STUDIO_BASE_URL=https://llm.api.cloud.yandex.net/v1
YANDEX_EMBEDDING_BASE_URL=https://llm.api.cloud.yandex.net:443/foundationModels/v1/textEmbedding

YANDEX_QWEN_MODEL=gpt://<folder-id>/qwen3.6-35b-a3b/latest
YANDEX_EMBEDDING_DOC_MODEL=emb://<folder-id>/text-search-doc/latest
YANDEX_EMBEDDING_QUERY_MODEL=emb://<folder-id>/text-search-query/latest
YANDEX_EMBEDDING_DIMENSIONS=256
```

Если человек запускает только retrieval smoke без live LLM, Yandex Qwen может не понадобиться. Для полного workflow/UI нужны live credentials.

## 4. Поднять Qdrant

```bash
docker compose -f docker-compose.qdrant.yml up -d qdrant
```

Проверить, что Qdrant отвечает:

```bash
curl http://localhost:6333/collections
```

## 5. Восстановить embeddings / collection

Если Qdrant collection `phase1_source_cards` уже восстановлена, этот шаг можно пропустить.

Если есть bundle `dataagent-phase1-embeddings-bundle.tar.gz`, восстановление описано в:

```text
HOW_TO_GET_DB.md
```

Критично, чтобы после восстановления существовали:

```text
.planning/phases/01-data-architecture-research/embedding-index-manifest.json
.planning/phases/01-data-architecture-research/embedding-corpus-manifest.json
.planning/phases/01-data-architecture-research/source-catalog-manifest.json
.planning/phases/01-data-architecture-research/source-cards-manifest.json
.planning/phases/02-jury-mvp/qdrant-server-manifest.json
```

И Qdrant collection:

```text
phase1_source_cards
```

Ожидаемый размер текущей collection:

```text
36321 vectors
```

Проверка через Python:

```powershell
@'
from qdrant_client import QdrantClient

client = QdrantClient(url="http://localhost:6333")
collection = "phase1_source_cards"

print(client.get_collection(collection).status)
print(client.count(collection_name=collection, exact=True).count)
'@ | python -
```

Ожидаемо:

```text
green
36321
```

## 6. Проверить graph-aware retrieval

Быстрая проверка тестами:

```bash
python -m pytest tests/test_hybrid_retrieval.py tests/test_retrieval_mode_comparison.py -q
```

Ожидаемо:

```text
9 passed
```

Проверка режимов retrieval:

```bash
python scripts/evaluate_retrieval_modes.py --case-limit 5
```

Скрипт сравнивает режимы:

- `dense_only`
- `lexical_only`
- `graph_first`
- `dense_plus_lexical`
- `hybrid_graph`

Результаты пишутся сюда:

```text
.planning/phases/02-jury-mvp/retrieval-mode-comparison.csv
.planning/phases/02-jury-mvp/retrieval-mode-comparison.json
.planning/phases/02-jury-mvp/retrieval-mode-comparison.md
```

Если `graph_first` или `hybrid_graph` падают, обычно причина одна из этих:

- нет `embedding-index-manifest.json`;
- Qdrant не поднят;
- collection называется не `phase1_source_cards`;
- в collection нет payload/source-card metadata;
- `.env` указывает на другой Qdrant.
- `.env` оставлен в embedded/local режиме вместо server mode (`QDRANT_MODE=remote` + `QDRANT_URL=http://localhost:6333`).

## 7. Запустить localhost

Вариант A: минимальный web UI:

```powershell
$env:PYTHONPATH=(Get-Location).Path
python -m app.web.server --port 8787
```

Открыть:

```text
http://127.0.0.1:8787
```

Вариант B: Streamlit UI:

```powershell
$env:PYTHONPATH=(Get-Location).Path
python -m streamlit run app/ui/streamlit_app.py --server.port 8501
```

Открыть:

```text
http://localhost:8501
```

Если сервер был запущен до `git pull`, его нужно перезапустить, иначе будет работать старый код.

## 8. Smoke-запросы

Для проверки retrieval и graph expansion можно спросить:

```text
Какой ВВП России в 2024 году?
Покажи ВВП России по ППС по Росстату.
Дай данные по инфляции.
Найди показатель ЕМИСС 57319 и покажи доступные ресурсы.
```

Ожидаемое поведение:

- система ищет source cards через Qdrant + BM25 + graph;
- граф может поднимать соседние карточки по indicator/dataset/geography/period;
- финальный ответ остается source-bound;
- если точного значения нет, система должна честно вернуть `not_found` или `needs_clarification`, а не придумывать число.

## 9. Что не надо делать

Не коммитить:

- `.env`;
- `.local/`;
- Qdrant storage;
- embeddings bundle;
- workflow-run артефакты, если они не нужны как evidence.

Не использовать:

```text
feat/experiment-resolve-agent-dumbness
```

Эта ветка не является нужной веткой для handoff graph-aware RAG.
