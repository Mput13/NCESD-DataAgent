Ты находишься в корне репозитория matmod. Тебе передали файл dataagent-phase1-embeddings-bundle.tar.gz и рядом dataagent-phase1-embeddings-bundle.tar.gz.sha256.

Задача: восстановить локальные Phase 1 embedding/source artifacts и Qdrant collection phase1_source_cards.

Важно:
- Не коммить архив, .local, Qdrant storage, .env или любые секреты.
- Работай из корня репозитория.
- Если docker compose уже держит Qdrant на 6333, используй его; иначе подними через docker-compose.qdrant.yml.

Шаги:

1. Проверить checksum архива:

shasum -a 256 -c dataagent-phase1-embeddings-bundle.tar.gz.sha256

Ожидаемо:
dataagent-phase1-embeddings-bundle.tar.gz: OK

2. Распаковать bundle:

mkdir -p .local/share
tar -xzf dataagent-phase1-embeddings-bundle.tar.gz -C .local/share

3. Проверить checksums файлов внутри:

cd .local/share/dataagent-phase1-embeddings
shasum -a 256 -c SHA256SUMS.txt
cd -

Все строки должны быть OK.

4. Восстановить локальные data files:

mkdir -p .local/dataagent/phase1

cp .local/share/dataagent-phase1-embeddings/embedding-corpus.jsonl .local/dataagent/phase1/
cp .local/share/dataagent-phase1-embeddings/embedding-cache.jsonl .local/dataagent/phase1/
cp .local/share/dataagent-phase1-embeddings/source-catalog.sqlite .local/dataagent/phase1/
cp .local/share/dataagent-phase1-embeddings/source-cards.json .local/dataagent/phase1/

5. Восстановить manifests Phase 1:

cp .local/share/dataagent-phase1-embeddings/embedding-corpus-manifest.json .planning/phases/01-data-architecture-research/
cp .local/share/dataagent-phase1-embeddings/embedding-index-manifest.json .planning/phases/01-data-architecture-research/
cp .local/share/dataagent-phase1-embeddings/source-catalog-manifest.json .planning/phases/01-data-architecture-research/
cp .local/share/dataagent-phase1-embeddings/source-cards-manifest.json .planning/phases/01-data-architecture-research/

6. Восстановить manifest Qdrant server:

mkdir -p .planning/phases/02-jury-mvp
cp .local/share/dataagent-phase1-embeddings/qdrant-server-manifest.json .planning/phases/02-jury-mvp/

7. Поднять Qdrant server:

docker compose -f docker-compose.qdrant.yml up -d qdrant

Если docker-compose.qdrant.yml отсутствует в репозитории, взять его из bundle:

cp .local/share/dataagent-phase1-embeddings/docker-compose.qdrant.yml .
docker compose -f docker-compose.qdrant.yml up -d qdrant

8. Восстановить Qdrant collection из snapshot:

SNAP_FILE=$(ls .local/share/dataagent-phase1-embeddings/*.snapshot | head -1)
SNAP_SHA=$(shasum -a 256 "$SNAP_FILE" | awk '{print $1}')

curl -X POST \
  "http://localhost:6333/collections/phase1_source_cards/snapshots/upload?wait=true&priority=snapshot&checksum=$SNAP_SHA" \
  --form "snapshot=@$SNAP_FILE"

9. Установить runtime env для текущей shell-сессии:

export QDRANT_URL=http://localhost:6333
export QDRANT_COLLECTION=phase1_source_cards

10. Проверить Qdrant collection:

python3 - <<'PY'
from qdrant_client import QdrantClient

client = QdrantClient(url="http://localhost:6333")
collection = "phase1_source_cards"

print(client.get_collection(collection).status)
print(client.count(collection_name=collection, exact=True).count)
PY

Ожидаемо:
green
36321

11. Проверить manifests:

python3 - <<'PY'
import json
from pathlib import Path

paths = [
    ".planning/phases/01-data-architecture-research/embedding-corpus-manifest.json",
    ".planning/phases/01-data-architecture-research/embedding-index-manifest.json",
    ".planning/phases/01-data-architecture-research/source-catalog-manifest.json",
    ".planning/phases/01-data-architecture-research/source-cards-manifest.json",
    ".planning/phases/02-jury-mvp/qdrant-server-manifest.json",
]

for path in paths:
    p = Path(path)
    print(path, "OK" if p.exists() else "MISSING")

index = json.loads(Path(".planning/phases/01-data-architecture-research/embedding-index-manifest.json").read_text())
server = json.loads(Path(".planning/phases/02-jury-mvp/qdrant-server-manifest.json").read_text())

print("index_status:", index.get("status"), index.get("dense_status"))
print("index_vectors:", index.get("vector_count"))
print("server_status:", server.get("status"))
print("server_vectors:", server.get("vector_count"))
print("collection:", server.get("collection"))
PY

Ожидаемые ключевые значения:
- index_status: ready ready
- index_vectors: 36321
- server_status: ready
- server_vectors: 36321
- collection: phase1_source_cards

12. Прогнать retrieval smoke:

QDRANT_URL=http://localhost:6333 \
QDRANT_COLLECTION=phase1_source_cards \
python3 scripts/run_retrieval_spike.py \
  --index-manifest .planning/phases/01-data-architecture-research/embedding-index-manifest.json \
  --output /tmp/retrieval-eval-check.csv \
  --comparison /tmp/retrieval-comparison-check.md \
  --limit 20

Ожидаемо: команда завершается без ошибки и пишет 20 строк в /tmp/retrieval-eval-check.csv.

13. Коротко отчитаться:

- checksum архива: OK / не OK
- internal checksums: OK / не OK
- Qdrant status и vector count
- retrieval smoke: success / failure
- если была ошибка, приложить точный traceback или curl response
