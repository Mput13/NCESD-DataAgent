# Architecture Research: DataAgent Options

**Created:** 2026-05-09  
**Status:** exploratory, no stack decision made  
**Purpose:** разложить пространство технических вариантов по слоям системы, чтобы команда не зафиксировалась преждевременно на одном пути вроде "RAG + embeddings + agent".

---

## 0. Executive Summary

Главная мысль: для этого кейса нельзя начинать с вопроса "какой RAG сделать?". Правильный вопрос шире: какие способности нужны виртуальному data-специалисту и какие альтернативные реализации есть для каждой способности.

Из ТЗ следуют жесткие требования:

- Любой факт или число в ответе сопровождается ссылкой на источник.
- Если данных нет, система честно сообщает об этом.
- Числа из датасетов извлекает детерминированный код, возможно сгенерированный LLM; LLM отвечает за понимание, маршрутизацию и формулировки.
- На каждом шаге пользователь должен видеть промежуточный артефакт: определение исследования, дизайн, структуру датасета, скрипт, итоговый файл.
- UI не должен быть мессенджер-ботом.
- Библиотеки должны быть open-source; LLM/AI-инструменты можно использовать через Yandex Cloud / AI Studio, при необходимости локальные open-source модели.

Что **не** следует считать решением:

- Embeddings не обязательны. Они являются одним из способов поиска.
- RAG не равен "векторная база". RAG может быть keyword, SQL, hybrid, API-first, file-search, rerank pipeline.
- MCP не обязателен. Это интерфейс к инструментам, полезный при расширяемости, но не единственный способ.
- Agentic loop не обязателен. Возможен deterministic workflow с LLM только на отдельных шагах.
- Multi-agent почти точно не является обязательным для MVP; это вариант для сложной оркестрации и демонстрации trace.
- Fine-tuning не нужен для первой проверки архитектуры; его можно рассматривать позже, если базовые модели не справятся с доменной терминологией.

Важное исследовательское наблюдение: для числовых и табличных документов dense retrieval не всегда превосходит keyword/BM25. Свежий benchmark по text+table financial QA показывает, что BM25 может обгонять dense retrieval, а лучший класс решений там - two-stage hybrid retrieval + rerank. Это не доказывает, что у нас будет так же, но доказывает, что "сразу embeddings" - плохая аксиома.

---

## 1. Слои Системы

Ниже слои, которые можно проектировать независимо:

1. Source inventory: какие источники существуют, как их описывать и проверять.
2. Ingestion/preprocessing: как превратить файлы/API в удобный каталог и данные.
3. Indexing/retrieval: как найти релевантные источники и показатели.
4. Query understanding: как понять намерение, географию, период, метрики, неоднозначности.
5. Source routing: как выбрать между локальными дампами, CKAN, API, web/file search.
6. Data extraction: как достать числа детерминированным кодом.
7. Computation: как считать производные метрики и согласовывать единицы/периоды.
8. Answer assembly: как сформировать текст, таблицу, ссылки, датасет и скрипт.
9. Workflow/orchestration: pipeline, tool-calling loop, graph, multi-agent.
10. UX/UI: как пользователь видит процесс, исправляет артефакты и скачивает результат.
11. Evaluation/observability: как мерить качество, честность, trace и регрессии.

Сквозная рабочая схема, которую полезно держать как reference flow, но не как выбранную архитектуру:

```text
User query
  -> query understanding / optional clarification
  -> source discovery over local and live catalogs
  -> deterministic data extraction
  -> computations and derived metrics
  -> answer, dataset, script, provenance
```

В этой схеме возможны обратные петли: уточняющий диалог после NLU, повторный поиск после "нет покрытия", repair-loop после ошибки SQL/Python, пользовательские правки после любого промежуточного артефакта.

---

## 2. Source Inventory and Data Modeling

### Вариант A: Raw-file first

Сохраняем дампы как есть: Parquet/JSON/CSV/XLSX/PDF/API responses. Рядом минимальный manifest: path, source, format, updated_at.

**Плюсы**

- Самый быстрый старт.
- Минимум риск испортить исходные данные при нормализации.
- Хорошо для демонстрации воспроизводимости: "вот источник, вот скрипт".

**Минусы**

- Поиск сложнее: имена файлов и сырой metadata JSON часто недостаточны.
- Каждый запрос заново сталкивается с разнородностью схем.
- Трудно дать хороший UX "почему выбран этот источник".

**Когда уместно**

- Если данных мало: 15-30 датасетов из тестовой коллекции.
- Если основной фокус - end-to-end prototype, а не качество поиска.

### Вариант B: Normalized source catalog

Строим единую таблицу/JSONL/SQLite/DuckDB-таблицу `sources`, `datasets`, `indicators`, `dimensions`, `coverage`, `units`, `license`, `provenance`.

**Плюсы**

- Убирает хаос между Росстатом, World Bank, CKAN и локальными файлами.
- Позволяет фильтровать по source/country/period/unit/topic до LLM.
- Создает хорошую основу для trace: "рассмотрены такие-то источники, отфильтрованы по периоду".

**Минусы**

- Нужно понять фактические схемы дампа.
- Требует mapping-словарей: страны, регионы, единицы, индикаторы, синонимы.
- Часть семантики может потеряться, если слишком рано сплющить метаданные.

**Инструменты**

- SQLite/DuckDB как embedded catalog.
- JSONL для простого обмена.
- Pydantic-модели для валидации схемы.
- pandas/pyarrow для первичного профилирования.

### Вариант C: Semantic document catalog

Каждый источник превращается в набор "карточек": title, description, indicator names, methodology, geography, period, units, tags, examples, links. Эти карточки индексируются отдельно от числовых данных.

**Плюсы**

- Хорошо подходит для поиска по естественному языку.
- Позволяет использовать и keyword, и embeddings, и hybrid.
- Можно хранить объяснимые snippets для пользователя.

**Минусы**

- Нужно аккуратно проектировать chunking: слишком длинные карточки шумят, слишком короткие теряют контекст.
- Риск, что карточка найдена, но реальные данные не покрывают нужный период/географию.
- Требует отдельной проверки "source candidate -> actual data availability".

**Инструменты**

- Markdown/JSONL карточки.
- Yandex AI Studio Vector Store, FAISS, Chroma, Qdrant, LanceDB.
- DuckDB/SQLite FTS для lexical layer.

### Вариант D: Data cube / star schema

Нормализуем данные в "long format": `source_id`, `indicator_id`, `geo_id`, `time`, `value`, `unit`, dimensions, provenance.

**Плюсы**

- Запросы и агрегации становятся проще.
- Удобно сравнивать источники и строить derived metrics.
- Отлично для повторных запросов после загрузки.

**Минусы**

- Самый дорогой ingestion.
- Реальные статистические базы имеют разные измерения, методологии и granularities; наивная унификация может быть ложной.
- Для хакатона может съесть время, если охватить слишком много источников.

**Когда уместно**

- Для узкого набора тестовых кейсов и источников.
- Если хотим сильный "data engineer" demo, а не широкий source discovery.

### Вариант E: Case/sample library as first-class data

Используем 5-10 seed examples из ТЗ как отдельный индекс: "запрос -> определение исследования -> дизайн -> структура датасета".

**Плюсы**

- Помогает не только искать данные, но и проектировать исследование.
- Дает UX-подсказки и templates.
- Можно быстро улучшать качество через few-shot/case-based retrieval.

**Минусы**

- Не заменяет поиск реальных данных.
- Может переобобщать, если seed examples слишком узкие.

**Вывод по слою**

Обязательная способность: иметь машинно-читаемое описание источников, покрытия, единиц и provenance. Инструмент не выбран: это может быть JSONL, DuckDB, SQLite, Vector Store или комбинация.

---

## 3. Preprocessing and Storage Options

### Вариант A: No preprocessing, query-time scan

Агент/пайплайн на каждом запросе читает metadata и нужные файлы.

**Плюсы**

- Быстрый прототип.
- Нет риска устаревшего индекса.
- Меньше кода ingestion.

**Минусы**

- Медленно на больших дампах.
- Повторяется логика профилирования.
- Сложно объяснять отклоненные источники.

### Вариант B: Offline metadata index only

Перед запуском строим индекс только по metadata, не трогаем сами числовые таблицы.

**Плюсы**

- Хороший баланс для MVP.
- Быстро перестраивается.
- Сохраняет deterministic extraction отдельно.

**Минусы**

- Может найти источник, но не доказать наличие нужных строк/периодов без дополнительной проверки.
- Качество зависит от полноты metadata.

### Вариант C: Offline metadata + schema/profile index

Кроме описаний, сохраняем schema, columns, min/max periods, geo coverage, units, row counts, null rates, example values.

**Плюсы**

- Сильно повышает точность routing.
- Позволяет отвечать "данных нет" доказательно.
- Помогает генерировать SQL/Python скрипты.

**Минусы**

- Нужно прочитать много Parquet/CSV.
- Профилирование может быть медленным на 1-10 GB, но это приемлемо как offline step.

**Инструменты**

- PyArrow: хорош для чтения Parquet metadata, выборки колонок, row groups.
- DuckDB: может читать Parquet напрямую SQL-ом, включая globs и HTTPS.
- Polars lazy: удобен для column/predicate pushdown в dataframe-подходе.

### Вариант D: Materialized working datasets

Для выбранных тест-кейсов заранее собираем промежуточные normalized tables.

**Плюсы**

- Быстрый и стабильный demo.
- Хорошо для 5-8 тест-кейсов.
- Можно честно обозначить как "prepared cache", а не hardcoded answers.

**Минусы**

- Плохо масштабируется на произвольные вопросы.
- Есть риск выглядеть как зашитые ответы, если не показать скрипт сборки.

### Вариант E: Cloud-managed index

Загружаем source cards/files в Yandex AI Studio Vector Store/File Search.

**Плюсы**

- Быстро получить hosted hybrid file search.
- Нативная совместимость с Yandex AI Studio agents.
- Меньше локальной инфраструктуры.

**Минусы**

- Нужно учитывать лимиты и поддерживаемые форматы.
- Чанкование управляемого сервиса может быть неидеальным для табличных metadata; Yandex docs прямо отмечают, что auto-chunking может резать текст без учета семантики, а JSONL pre-chunks могут быть лучше.
- Сложнее тестировать и воспроизводить offline.

**Вывод по слою**

Для архитектурного отчета нельзя писать "строим embeddings". Корректнее: "строим обработанный каталог и один или несколько индексов; вид индекса выбирается экспериментом".

---

## 4. Retrieval / Search Layer

### Вариант A: Pure lexical search

Поиск по словам, точным названиям, кодам, аббревиатурам. Может быть простым `LIKE`, fuzzy matching, FTS, BM25.

**Инструменты**

- DuckDB FTS extension.
- SQLite FTS5.
- PostgreSQL full text search.
- Tantivy.
- Whoosh.
- RapidFuzz для fuzzy matching.

**Плюсы**

- Отлично ловит коды показателей, названия стран, "ВВП", "GDP", "SP.POP.TOTL".
- Прозрачный scoring.
- Не требует embedding API и затрат.
- Часто силен в числовых/table-heavy задачах.

**Минусы**

- Плохо ловит синонимы и перефразировки.
- Нужны словари: ВВП/GDP, инфляция/CPI, рождаемость/fertility.
- Морфология русского языка может потребовать stemmer/lemmatizer.

### Вариант B: Pure dense vector search

Все карточки источников превращаются в embeddings, запрос тоже, ищем nearest neighbors.

**Инструменты**

- Yandex embeddings (`text-search-doc`, `text-search-query`).
- FAISS: локальный dense vector index.
- Chroma/LanceDB: локальный векторный store с metadata.
- Qdrant/Milvus/Weaviate: vector DB с фильтрами и масштабированием.

**Плюсы**

- Хорошо работает с перефразированием.
- Удобно для длинных естественно-языковых описаний.
- Меньше ручных словарей на старте.

**Минусы**

- Может промахиваться по точным кодам, единицам, числам и аббревиатурам.
- Требует chunking и embedding model choice.
- Сложнее объяснять, почему источник найден.
- Для таблично-числовых запросов не стоит считать лучшим без benchmark.

### Вариант C: Hybrid retrieval

Смешиваем lexical/BM25 и dense search, затем объединяем результаты: RRF, weighted score, learned ranker или rules.

**Инструменты**

- Yandex Vector Store: по документации использует hybrid search by default для File Search.
- Qdrant hybrid queries: dense + sparse prefetch + RRF/weighted RRF.
- Custom: DuckDB/SQLite FTS + FAISS/Chroma + merge.
- Elasticsearch/OpenSearch: BM25 + vector/hybrid.

**Плюсы**

- Закрывает и точные совпадения, и смысловые перефразировки.
- Хороший общий кандидат для разнородных запросов.
- Позволяет отключать/взвешивать dense retrieval при точных numeric/code queries.

**Минусы**

- Больше moving parts.
- Нужна оценка качества и tuning weights.
- Без rerank может возвращать шумную смесь.

### Вариант D: Metadata-filter-first retrieval

Сначала жесткие фильтры: страна, регион, период, источник, формат, единицы, частота. Потом search внутри кандидатов.

**Плюсы**

- Очень важно для "нет данных".
- Уменьшает шум до LLM.
- Объяснимо для пользователя.

**Минусы**

- Нужны нормализованные поля coverage.
- Ошибка в slot extraction может слишком рано отрезать правильный источник.

### Вариант E: Reranking layer

Первый retrieval возвращает top 20-100, затем reranker сортирует top candidates.

**Инструменты**

- Cross-encoder reranker.
- LLM-as-reranker с structured rubric.
- Rule-based ranker: period coverage, unit match, official source priority, exact indicator match.
- Hybrid: rule score + LLM justification.

**Плюсы**

- Часто дает больше качества, чем замена search engine.
- Можно учесть критерии ТЗ: source reliability, coverage, methodology.
- Хорошо объясняется в trace.

**Минусы**

- Cross-encoder/LLM добавляет latency/cost.
- LLM-rerank может быть недетерминированным, если не ограничить схему.

### Вариант F: Unified index vs per-source search

Есть отдельная развилка не только "какой search engine", но и "как организовать источники".

**Unified index:** Росстат, World Bank, CKAN snapshots и source cards складываются в один общий индекс с общими полями.

**Плюсы**

- Один search interface для агента/пайплайна.
- Легче сравнивать источники в общем top-k.
- Проще сделать общий UX со списком candidates.

**Минусы**

- Нужна нормализация metadata до общего знаменателя.
- Можно потерять особенности источника: измерения Росстата, indicator IDs World Bank, CKAN resource formats.
- Общий score может нечестно сравнивать разные типы данных.

**Per-source search + merge:** каждый источник имеет свой search adapter, затем результаты сливаются и ранжируются общим merger/reranker.

**Плюсы**

- Легче добавлять новые источники.
- Сохраняется source-specific логика и фильтры.
- Лучше для trace: видно, где искали и почему источник не подошёл.

**Минусы**

- Нужен слой fusion/normalization после поиска.
- Больше кода и больше мест для tuning.

### Вариант G: Query expansion / decomposition

LLM или словари расширяют запрос: "инфляция" -> CPI, consumer price index, ИПЦ; "доходы" -> nominal/real disposable income.

**Плюсы**

- Помогает при неоднозначных запросах.
- Улучшает recall.

**Минусы**

- Может расширить слишком широко.
- Для точных числовых запросов HyDE/multi-query может ухудшить precision; benchmark по text+table QA отмечает ограниченную пользу query expansion для precise numerical queries.

**Вывод по слою**

Нужны как минимум два режима поиска: exact/lexical для кодов и терминов, semantic/hybrid для описательных запросов. Но конкретный инструмент должен быть выбран по retrieval eval на тест-кейсах, а не по модности.

---

## 5. Query Understanding Layer

### Вариант A: Rule-based parser + dictionaries

Правила и словари извлекают страны, периоды, источники, известные индикаторы, единицы.

**Плюсы**

- Детерминированно.
- Легко тестировать.
- Хорошо для 5-8 известных тест-кейсов.

**Минусы**

- Хрупко на свободном языке.
- Словари быстро растут.
- Сложно проектировать исследовательские гипотезы.

**Инструменты**

- Python regex/dateparser.
- Natasha/spaCy для NER русского языка.
- RapidFuzz для fuzzy matching географий/индикаторов.
- Pydantic для schema validation.

### Вариант B: LLM structured extraction

LLM возвращает JSON: query_type, geography, period, metrics, ambiguity, desired_artifact, derived_metrics.

**Плюсы**

- Быстро закрывает разнообразный язык.
- Хорошо для "проектирования исследования".
- Можно просить confidence и unresolved_fields.

**Минусы**

- Нужна строгая валидация результата.
- Может "додумать" поля.
- Требует fallback, если модель не уверена.

**Инструменты**

- YandexGPT/function calling/structured response.
- Pydantic validation.
- JSON schema.

### Вариант C: Few-shot / case-conditioned parsing

В prompt или retrieval context добавляются 5-10 размеченных примеров "запрос -> тип -> slots -> уточнения -> ожидаемый артефакт". Это может быть статический few-shot prompt или retrieval из case library.

**Плюсы**

- Дешево улучшает качество NLU без fine-tuning.
- Особенно полезно для шести типов запросов из ТЗ.
- Может связать NLU с downstream artifacts: определение исследования, дизайн, структура датасета.

**Минусы**

- Примеры могут bias-ить систему к одному стилю задач.
- Статический prompt плохо масштабируется при росте библиотеки.
- Не заменяет валидацию через реальные source coverage.

### Вариант D: Classifier + slot extraction

Отдельный классификатор типа запроса, затем slot extraction.

**Плюсы**

- Объяснимее, чем один большой prompt.
- Можно оценивать отдельно: type accuracy, slot F1.
- Удобно для маршрутизации UX.

**Минусы**

- Больше компонентов.
- Ошибка классификатора влияет на downstream.

### Вариант E: Clarification-first workflow

Если запрос недостаточно определен, система сначала строит варианты интерпретации и спрашивает пользователя.

**Плюсы**

- Соответствует ТЗ для неоднозначных запросов.
- Уменьшает риск ложных источников.
- Хороший UX: пользователь видит, какие решения нужно принять.

**Минусы**

- Может раздражать при слишком частых вопросах.
- Нужна политика: когда спрашивать, когда брать default.

### Вариант F: Research-design agent

Отдельный LLM-step формирует определение исследования, гипотезы, структуру датасета. Это не обязательно agent loop; может быть один structured generation step.

**Плюсы**

- Хорошо соответствует полному пути ТЗ.
- Дает полезный артефакт даже до сборки данных.

**Минусы**

- Может выглядеть красиво, но не быть связано с доступными данными.
- Нужно проверять через source coverage.

**Вывод по слою**

Нужно разделить: "понимание запроса" и "принятие data decisions". LLM может формализовать запрос, но реальные решения о наличии данных должны подтверждаться каталогом/кодом.

---

## 6. Source Routing Layer

### Источник A: Local Rosstat/EMISS dump

**Сильные стороны**

- Локально, воспроизводимо.
- Можно детерминированно читать Parquet.
- Вероятно лучше для российских региональных/социально-экономических данных.

**Риски**

- Нужно понять схему и коды.
- Может быть много разнородных измерений.
- Методологии и единицы нужно показывать явно.

### Источник B: Local World Bank dump

**Сильные стороны**

- Международное покрытие.
- Хорош для cross-country и time series запросов.
- API также доступен без ключей по World Bank docs.

**Риски**

- Не все показатели покрывают 2024-2025.
- Нужна нормализация стран, регионов, income groups.
- Индикаторы могут быть proxy, не точное соответствие запросу.

### Источник C: CKAN / NSED repository API

**Сильные стороны**

- Нативный путь к реестру НЦСЭД.
- CKAN Action API поддерживает `package_search`, `resource_search`, `package_show`, JSON responses.
- Хорош для live discovery и демонстрации расширяемости.

**Риски**

- API/репозиторий может быть нестабилен в момент хакатона.
- Search API не заменяет локальный quality ranker.
- Нужно кэшировать результаты для воспроизводимости.

### Источник D: Official open APIs

World Bank API, SDMX endpoints, госстатистика, международные организации.

**Плюсы**

- Актуальность.
- Можно закрывать запросы, которых нет в локальном дампе.
- Хорошо показывает "если данных нет локально, ищем в проверенных источниках".

**Минусы**

- Разные rate limits, schemas, availability.
- Нужно явно различать "данные не найдены" и "API недоступен".
- Может усложнить воспроизводимость.

### Источник E: Web Search over verified domains

Ищем только на доменах официальных организаций или в белом списке.

**Плюсы**

- Помогает найти методологию, документы, обновления.
- Хорош для объяснений, но не для извлечения чисел из произвольных страниц.

**Минусы**

- ТЗ запрещает опираться на непроверенный user content.
- Числа все равно должны извлекаться кодом из данных, не LLM из веб-страницы.
- Нужно сохранять ссылки и snapshots.

### Источник F: User-provided files

Пользователь загружает Excel/CSV/PDF, система строит временный source card.

**Плюсы**

- Увеличивает практическую ценность.
- Хорошо для demo "аналитик принес файл".

**Минусы**

- Не основной кейс ТЗ.
- PDF/table extraction может быть нестабильным.
- Требует UI и sandboxing.

**Вывод по слою**

Routing должен быть source-aware, а не просто "search all". Для каждого источника нужны поля: authority, freshness, coverage, method, format, deterministic extraction method, provenance.

---

## 7. Data Extraction Layer

### Вариант A: DuckDB SQL over Parquet

DuckDB умеет читать Parquet напрямую через SQL, globs, lists, HTTPS, и получать metadata/schema.

**Плюсы**

- Очень удобно для generated SQL/scripts.
- Хорош для фильтрации, агрегаций, joins.
- Можно читать только нужные файлы/колонки.
- Легко сохранять SQL как воспроизводимый артефакт.

**Минусы**

- Нужно генерировать корректный SQL.
- Сложные nested schemas/разные схемы файлов могут потребовать preprocess.
- Для dataframe-heavy transformations pandas/Polars иногда проще.

### Вариант B: pandas + pyarrow

`pandas.read_parquet` через pyarrow поддерживает columns и filters; PyArrow дает доступ к Parquet metadata, row groups, schemas.

**Плюсы**

- Самый знакомый Python data stack.
- Отлично для сгенерированных и читаемых пользователем скриптов.
- Много библиотек для Excel/CSV/cleaning.

**Минусы**

- Риск загрузить больше данных в память.
- Меньше декларативности, чем SQL.
- Сгенерированный pandas-код может быть менее проверяемым.

### Вариант C: Polars lazy

Lazy scan, predicate/projection pushdown, быстрые transformations.

**Плюсы**

- Производительно.
- Хорошо для pipeline transformations.
- Lazy plan может оптимизировать чтение.

**Минусы**

- Менее знакомо части пользователей.
- LLM может хуже генерировать Polars-код, чем pandas/SQL.

### Вариант D: PyArrow/DataFusion

Низкоуровневый слой для чтения/фильтрации/metadata, DataFusion для SQL execution.

**Плюсы**

- Хорош для columnar data engineering.
- Может быть основой для deterministic core.

**Минусы**

- Более инженерный путь.
- Меньше "понятный пользователю скрипт".

### Вариант E: Ibis abstraction

Python expression API, который может исполняться через DuckDB/Polars/SQL backends.

**Плюсы**

- Может дать portable logical plan.
- Хорошо для контролируемой генерации вместо raw SQL.

**Минусы**

- Дополнительная абстракция.
- Нужно проверять, насколько LLM хорошо генерирует Ibis expressions.

### Вариант F: Fixed domain tools, not generated code

Вместо генерации произвольного кода делаем инструменты: `load_indicator`, `filter_time_series`, `aggregate`, `join_indicators`, `compute_index`.

**Плюсы**

- Безопаснее и предсказуемее.
- Легко тестировать.
- Хороший fit для function calling.

**Минусы**

- Меньше гибкости.
- Нужно заранее предвидеть операции.

### Вариант G: Schema-first code generation

Перед генерацией SQL/Python система передает модели не "примерно какой файл", а проверенный контракт: schema, column meanings, types, allowed filters, min/max period, geography coverage, example rows, source_id.

**Плюсы**

- Сильно снижает риск неправильного SQL/Python.
- Делает trace понятнее: видно, на какой схеме основан код.
- Позволяет валидировать output до формирования ответа.

**Минусы**

- Нужен отдельный `inspect_schema` / `profile_source` step.
- Если schema metadata неполная, модель может получить ложное чувство определенности.

### Вариант H: Self-healing execution loop

Если SQL/Python падает или не проходит validation, система возвращает ошибку, schema contract и failed query/code в repair-step. Repair может быть LLM-driven или rule-driven.

**Плюсы**

- Практически важно для generated code.
- Хорошо показывает agentic behavior без full multi-agent.
- Можно ограничить числом попыток и логировать каждую попытку.

**Минусы**

- Может замаскировать системную проблему, если retries бесконечные.
- Нужны строгие stop conditions: максимум попыток, timeout, запрет расширять source scope без объяснения.

### Вариант I: Generated script with sandbox and validation

LLM генерирует Python/SQL, система запускает, валидирует output schema, row counts, citation coverage.

**Плюсы**

- Соответствует ТЗ: downloadable script, modifiable by user.
- Максимально гибко для исследовательских запросов.

**Минусы**

- Нужен sandbox, таймауты, запрет опасных операций.
- Для хакатонного MVP минимальный профиль безопасности может быть read-only allowlist на директории данных + запрет network/file writes кроме artifact output.
- Нужны retries/repair loops.
- Нельзя доверять коду без проверки.

**Вывод по слою**

Основное требование: deterministic execution. Это может быть fixed tools, generated SQL, generated Python, DuckDB, pandas, Polars или их комбинация. LLM не должна "читать таблицу глазами".

---

## 8. Derived Metrics and Methodology Layer

### Вариант A: Formula DSL

Описываем производные метрики в ограниченном JSON/DSL:

```json
{
  "metric": "real_disposable_income_index",
  "inputs": ["nominal_income", "cpi"],
  "base_year": 2014,
  "formula": "nominal_income / cpi * 100, normalized_to_base_year"
}
```

**Плюсы**

- Контролируемо и валидируемо.
- Можно показывать формулу пользователю.
- Меньше риска произвольного кода.

**Минусы**

- Нужно спроектировать DSL.
- Не все операции удобно выразить.

### Вариант B: SQL macros / DuckDB views

Производные метрики считаются SQL-выражениями и view.

**Плюсы**

- Прозрачно и воспроизводимо.
- Хорошо для joins, windows, aggregation.

**Минусы**

- Сложные статистические операции могут стать громоздкими.

### Вариант C: Python generated calculations

pandas/Polars код считает индексы, нормализации, joins.

**Плюсы**

- Гибко.
- Аналитику проще модифицировать.

**Минусы**

- Нужно валидировать формулы, units, missing values.
- Больше риска тихих ошибок.

### Вариант D: Methodology-first dialogue

Для неоднозначных производных метрик система сначала предлагает варианты методологии:

- nominal vs real.
- CPI source.
- base year.
- chain index vs fixed-base index.
- aggregation rule.

**Плюсы**

- Лучше для экономической корректности.
- Снижает риск "правильный код, неправильная методология".

**Минусы**

- Удлиняет UX.

**Вывод по слою**

Для derived metrics нужно явно хранить не только код, но и методологическое решение. Хороший artifact: `metric_definition.md` + `calculation.sql/py` + references.

---

## 9. Answer Assembly Layer

### Вариант A: Template-first answer

Ответ собирается шаблонами из structured facts:

- summary.
- table preview.
- source list.
- limitations.
- downloadable artifacts.

**Плюсы**

- Минимум галлюцинаций.
- Легко требовать citation coverage.
- Быстро.

**Минусы**

- Менее естественный текст.
- Сложнее для исследовательских выводов.

### Вариант B: LLM finalizer over verified facts

LLM получает только проверенные rows/aggregates/source cards и формирует human-readable answer.

**Плюсы**

- Хороший UX.
- Можно адаптировать стиль под экономиста.

**Минусы**

- Нужен guard: нельзя добавлять числа вне provided facts.
- Нужно проверять, что каждая цифра в тексте есть в fact table.

### Вариант C: Dataset-first answer

Главный output - файл CSV/XLSX/Parquet + script. Текст - короткое описание.

**Плюсы**

- Сильно соответствует "не общие слова, а артефакт".
- Меньше риска галлюцинации.

**Минусы**

- Для пользователя-непрограммиста нужен хороший preview и объяснение.

### Вариант D: Research notebook/report

Выход: notebook/HTML report с кодом, таблицами, графиками и provenance.

**Плюсы**

- Прозрачность и воспроизводимость.
- Сильный demo для аналитиков.

**Минусы**

- Дольше делать UI.
- Notebook может быть менее удобен как конечный продукт.

### Вариант E: Visualization as optional artifact

Графики добавляются не как основной ответ, а как derived artifact из уже проверенного датасета: line chart, bar chart, comparison chart, missingness chart.

**Плюсы**

- Быстро повышает понятность результата для демо.
- Хорошо работает с Streamlit/Gradio/Plotly.
- Может выявить странности данных: пропуски, скачки, несопоставимые единицы.

**Минусы**

- Не заменяет корректный dataset/script.
- Риск потратить время на polish вместо source quality.
- График тоже должен ссылаться на те же provenance records, что и таблица.

### Вариант F: Citation guard / numeric verifier

После final answer отдельный checker извлекает числа из ответа и проверяет, что они есть в structured facts и имеют source_id.

**Плюсы**

- Прямо закрывает главное требование ТЗ.
- Можно использовать в tests.

**Минусы**

- Требует парсинга чисел и нормализации форматов.
- Не ловит все методологические ошибки.

**Вывод по слою**

Финальный ответ должен быть downstream от fact table/provenance table. LLM может формулировать, но не быть источником чисел.

---

## 10. Agentic Workflow Options

### Runtime surface choices

Эти варианты ортогональны самой форме workflow. Один и тот же deterministic pipeline или light tool-calling agent можно запустить разными способами.

| Runtime | Плюсы | Минусы | Когда проверять |
|---------|-------|--------|-----------------|
| Custom loop | Полный контроль над retries, trace, tool budget, validation | Нужно самим писать state handling, tool protocol, streaming | Если нужен минимальный, прозрачный MVP |
| Yandex AI Studio / Responses-compatible API | Нативно для кейса, function calling, hosted search/MCP surfaces | Нужно проверить реальные возможности, лимиты и совместимость SDK | Если хотим опираться на Yandex Cloud как платформу |
| OpenAI-compatible SDK against Yandex base URL | Может ускорить разработку, если совместимость полная | Частичная совместимость может ломаться на streaming/tools/responses | Отдельный spike до выбора orchestration |
| LangGraph/LlamaIndex/Haystack | Готовые abstractions для graph, loops, HITL, observability | Overhead и learning curve для хакатона | Если нелинейный workflow важнее простоты |

### Вариант A: No-agent deterministic pipeline

Шаги фиксированы:

1. parse query.
2. retrieve candidates.
3. rank candidates.
4. generate plan.
5. execute extraction.
6. validate.
7. answer.

**Плюсы**

- Самый тестируемый и надежный.
- Понятный trace.
- Не надо отлаживать unpredictable tool loop.

**Минусы**

- Меньше гибкости.
- Сложнее обрабатывать неожиданные запросы.
- Может выглядеть менее "agentic" на демо.

**Когда подходит**

- MVP на 5-8 запросах.
- Если важнее качество и честность, чем автономность.

### Вариант B: Light tool-calling agent

Один LLM в цикле может вызвать ограниченные tools: `search_sources`, `inspect_schema`, `extract_data`, `ask_clarification`, `generate_script`, `validate_output`.

**Плюсы**

- Баланс гибкости и контроля.
- Хорошо ложится на Yandex function calling.
- Trace tool calls можно показать пользователю.

**Минусы**

- Нужно ограничивать tool budget и stop conditions.
- Tool descriptions становятся критичны.
- Возможны лишние или неверные tool calls.

### Вариант C: Planner-executor

Planner формирует план и артефакты; executor выполняет код/поиск; verifier проверяет.

**Плюсы**

- Хорошо совпадает с 7 шагами ТЗ.
- Можно показать пользователю план до выполнения.
- Удобно вставлять human-in-the-loop.

**Минусы**

- Больше latency.
- Если planner ошибся, executor может честно выполнить плохой план.

### Вариант D: Graph workflow

Узлы: classify -> clarify -> design -> retrieve -> rerank -> inspect -> execute -> validate -> repair -> final. Ветки и loops явно описаны.

**Инструменты**

- LangGraph: durable execution, streaming, human-in-the-loop, checkpointing.
- LlamaIndex Workflows: event-driven steps, loops, concurrency, HITL examples.
- Haystack Pipelines: directed multigraphs, branches, loops, async pipelines.
- Prefect/Dagster/Temporal для более data-engineering style workflows.

**Плюсы**

- Хорошо для нелинейного user journey.
- Состояние и trace проще сохранять.
- Удобно делать resume/replay.

**Минусы**

- Для хакатона может быть overhead.
- Требует проектирования state schema.

### Вариант E: Multi-agent

Специалисты: query analyst, source scout, data engineer, methodology critic, answer writer, verifier.

**Плюсы**

- Демонстрационно красиво.
- Разделяет роли и prompts.
- Можно параллелить source search.

**Минусы**

- Большой overhead.
- Больше недетерминизма.
- Труднее debug/eval.
- Может быть "архитектура ради архитектуры".

### Вариант F: MCP-first architecture

Каждый источник/инструмент - MCP server: Rosstat, World Bank, CKAN, DuckDB, script runner, Excel exporter.

**Плюсы**

- Хорошо для расширяемости.
- Yandex MCP Hub поддерживает подключение внешних MCP servers и создание своих servers/tools.
- Четкая граница инструментов.

**Минусы**

- MCP - транспорт/контракт, а не качество поиска.
- На MVP может быть лишний слой.
- Нужно деплоить/поддерживать servers или adapters.

**Вывод по слою**

Agentic workflow нужен не потому, что "так современно", а если есть реальная нелинейность: уточнения, source fallback, repair loops, user edits, replay. Для первого MVP жизнеспособны как deterministic pipeline, так и light tool-calling agent. Full multi-agent - optional/research path.

---

## 11. UX/UI Options

### Вариант A: CLI

Командная строка: запрос -> trace -> artifacts.

**Плюсы**

- Самый быстрый.
- ТЗ говорит, что CLI лучше мессенджер-бота.
- Удобно для reproducibility.

**Минусы**

- Не лучший UX для непрограммиста.
- Сложнее показать нелинейные правки.

### Вариант B: Streamlit

Chat + status panels + dataframes + downloads.

**Плюсы**

- Streamlit имеет chat elements, status for long-running tasks, stream output.
- Очень быстрый UI для Python data apps.
- Хорошо показывает таблицы/графики/файлы.

**Минусы**

- Layout и сложные state flows ограничены.
- Может выглядеть как прототип, если не аккуратно собрать UX.

### Вариант C: Gradio

ChatInterface/Blocks, examples, file outputs, feedback.

**Плюсы**

- Очень быстрый chatbot/demo.
- Поддерживает additional inputs/outputs, downloadable artifacts, examples.
- Хорош для ML demo.

**Минусы**

- Для сложного workflow trace может быть тесно.
- Чуть менее "data workbench", чем Streamlit/FastAPI.

### Вариант D: Chainlit

Chat-first Python UI for conversational AI with first-class concepts for messages, steps, streaming, user session, actions and feedback.

**Плюсы**

- Хорош для визуализации multi-step agent/tool trace.
- Быстрее custom frontend, если фокус именно на "следе" ассистента.
- Поддерживает streaming для messages и steps.

**Минусы**

- Меньше подходит для полноценного data workbench с богатыми таблицами, редакторами и сложным layout.
- Может подтолкнуть продукт в сторону "чат-агент", хотя центральным должен быть artifact workflow.

### Вариант E: FastAPI + custom frontend

Backend API + React/Vue/Svelte UI.

**Плюсы**

- Лучший контроль UX.
- Можно сделать artifact workspace: source cards, steps, diff, approvals, downloads.
- Готовит путь к production.

**Минусы**

- Самый дорогой для хакатона.
- Нужны frontend effort и state management.

### Вариант F: NiceGUI / Panel / Dash

Python-first richer UI.

**Плюсы**

- Больше контроля, чем Streamlit.
- Быстрее custom React.

**Минусы**

- Меньше familiarity.
- Риск потратить время на UI framework.

### Вариант G: Notebook/report-first

Система генерирует notebook/HTML report с шагами.

**Плюсы**

- Отлично для "researcher" audience.
- Код и результат рядом.

**Минусы**

- Не совсем интерфейс для непрограммиста.
- Интерактивные уточнения сложнее.

### UX patterns, которые нужны независимо от UI

- Stepper: Запрос -> Определение -> Дизайн -> Структура датасета -> Источники -> Скрипт -> Результат.
- Candidate source cards: источник, покрытие, период, единицы, почему выбран, почему отклонен.
- Clarification panel: "инфляция может означать CPI/year-over-year/monthly; выбрать?"
- Artifact workspace: каждый промежуточный результат можно принять, исправить или скачать.
- Trace timeline: tool calls, search queries, rejected sources, validation checks.
- Confidence/honesty: не "уверенность LLM", а проверенные статусы: source found, coverage matched, extraction succeeded, citation coverage passed.
- Data preview: первые строки, schema, units, missing values.
- Download buttons: dataset, script, metadata/provenance, report.
- Replay: повторить сборку из сохраненного скрипта и manifest.

**Вывод по слою**

UI лучше думать не как "чат", а как "agentic data workbench". Чат - только вход и объяснения. Центральный UX - артефакты, источники, правки, trace.

---

## 12. Evaluation and Observability

### Retrieval eval

Метрики:

- Recall@k: попал ли правильный source/indicator в top-k.
- MRR: насколько высоко правильный источник.
- nDCG: качество ранжирования, если есть graded relevance.
- Source coverage accuracy: период/география/единицы совпали?

Инструменты:

- pytest golden tests.
- custom eval CSV.
- Ragas/DeepEval для RAG/agent metrics, если нужен LLM-eval.

### Data extraction eval

Метрики:

- Numeric exact/within tolerance match.
- Row count match.
- Schema match.
- Unit match.
- Missingness behavior.
- Script rerun success.

### Answer eval

Метрики:

- Citation coverage: каждая цифра имеет source_id/link.
- No unsupported numeric claims.
- Correct "data not found" behavior.
- Clarity for non-programmer.

### Agent/workflow eval

Метрики:

- Tool call accuracy.
- Step efficiency.
- Plan adherence.
- Clarification appropriateness.
- Trace completeness.

Инструменты:

- Yandex/own logs.
- OpenTelemetry-style spans.
- LangGraph/LlamaIndex/Haystack tracing if using those frameworks.
- OpenAI docs emphasize traces first, then repeatable eval datasets for agent workflows; conceptually это применимо и к Yandex-compatible loop.
- Ragas lists context precision/recall/faithfulness and tool-use metrics.
- DeepEval documents RAG metrics, agentic metrics and LLM-as-judge workflows.
- promptfoo can be used for prompt/regression tests.

**Вывод по слою**

Без eval нельзя выбрать search strategy. Нужно измерять хотя бы 5-8 запросов сразу, даже если руками размеченных.

---

## 13. Viable End-to-End Architecture Families

Это не рекомендации, а разные жизнеспособные пути.

### Family A: Deterministic SQL-first pipeline

**Shape**

Normalized catalog in DuckDB/SQLite -> rule/LLM structured parsing -> SQL source search -> DuckDB extraction -> template/LLM answer.

**Плюсы**

- Очень честно и воспроизводимо.
- Отлично для чисел и ссылок.
- Меньше недетерминизма.

**Минусы**

- Меньше семантической гибкости.
- Нужно больше ручных mappings.
- Может хуже отвечать на исследовательские запросы без strong design step.

**Best fit**

- Если тест-кейсы в основном простые/сравнительные/derived metrics.

### Family B: Hybrid retrieval + deterministic extraction

**Shape**

Source cards -> lexical + dense search -> rerank -> inspect actual data -> DuckDB/pandas extraction -> citation guard -> answer.

**Плюсы**

- Сильный баланс precision/recall.
- Хорошо покрывает разные формулировки.
- Позволяет сравнить lexical/dense/hybrid экспериментально.

**Минусы**

- Больше компонентов.
- Нужно tuning и eval.

**Best fit**

- Если запросы разнообразные, но нужен controlled MVP.

### Family C: Yandex AI Studio native agent/search

**Shape**

Yandex agent + function calling + AI Studio Vector Store/File Search + MCP/API tools + deterministic extraction service.

**Плюсы**

- Нативно для кейса НЦСЭД + Yandex Cloud.
- AI Studio docs поддерживают agents, function calling, File Search, Web Search, Vector Store, MCP Hub.
- Быстро показать agent/tool story.

**Минусы**

- Vendor surface и cloud setup.
- Managed chunking/search может быть неидеален для табличных metadata.
- Нужно локально держать deterministic extraction и provenance guard.

**Best fit**

- Если оценщики ожидают использование Yandex Cloud capabilities.

### Family D: Workflow graph / human-in-the-loop workbench

**Shape**

Graph nodes for research definition, clarification, retrieval, validation, execution, repair. UI shows each node and artifact.

**Плюсы**

- Лучшее соответствие нелинейному пути ТЗ.
- Хорошо для "принять/исправить/остановиться на любом шаге".
- Удобно для replay.

**Минусы**

- Overhead для короткого hackathon.
- Требуется state model.

**Best fit**

- Если команда хочет выиграть продуктовым качеством и trace.

### Family E: Source broker / adapters first

**Shape**

Много source adapters: local Rosstat, World Bank, CKAN, SDMX, web. Search/routing выбирает adapters. Каждый adapter умеет search, inspect, fetch, cite.

**Плюсы**

- Отличная расширяемость.
- Четкое разделение ответственности.
- Подходит под MCP later.

**Минусы**

- Много integration work.
- Качество зависит от каждого adapter.

**Best fit**

- Если нужен "более одного реального источника/инструмента" как главный demo.

### Family F: Case-library assisted research designer

**Shape**

Seed examples -> case retrieval -> research definition/design/dataset schema -> source search -> extraction.

**Плюсы**

- Усиливает полные семь шагов ТЗ.
- Хорошо для неоднозначных/исследовательских запросов.
- Быстро дает качественные intermediate artifacts.

**Минусы**

- Не заменяет data retrieval.
- Требует хороших seed examples.

**Best fit**

- Если тесты включают "исследовательские" запросы и качество промежуточных артефактов важно.

### Family G: Local/offline-first

**Shape**

Local LLM or local embeddings + FAISS/SQLite/DuckDB + no cloud dependency except optional.

**Плюсы**

- Воспроизводимо.
- Нет cloud latency/cost.
- Может быть сильным "privacy/offline" модификатором.

**Минусы**

- Настройка моделей может съесть время.
- Yandex Cloud emphasis в кейсе может быть недоиспользован.

**Best fit**

- Если cloud/API ключи недоступны или unreliable.

---

## 14. Что Вероятнее Всего Обязательно, Опционально, Рискованно

### Обязательно

- Source/provenance schema.
- Deterministic data extraction.
- Citation guard.
- Honest no-data protocol.
- Trace of steps and rejected/accepted sources.
- At least minimal eval set.
- Reproducible script/artifacts.

### Вероятно полезно, но требует проверки

- Normalized metadata catalog.
- Hybrid lexical + semantic search.
- Reranking top candidates.
- Schema/profile index for Parquet.
- LLM structured query understanding.
- Few-shot/case-conditioned query parsing.
- Schema-first code generation.
- Bounded self-healing repair loop for generated SQL/Python.
- Clarification workflow for ambiguous queries.
- Streamlit/Gradio/Chainlit data-workbench or trace-workbench prototype.

### Опционально

- Full MCP architecture.
- Full graph workflow.
- Multi-agent roles.
- Cloud Vector Store.
- Local vector DB.
- Fine-tuned embeddings.
- Rich dashboards/visualizations.
- User-uploaded files.
- OpenAI-compatible SDK wrapper over Yandex endpoints, if compatibility is confirmed.

### Рискованно для MVP

- Pure dense vector search as only retrieval method.
- LLM reads tables/PDFs and extracts numbers directly.
- Open web search without verified-source whitelist.
- Multi-agent without strong tracing/eval.
- Full normalization of all 10-200K indicators before knowing test cases.
- Custom frontend before core data path works.
- Generated arbitrary code without sandbox/validation.

---

## 15. Spike Plan to Choose Instead of Guess

### Spike 0: Provider and SDK compatibility

Before choosing orchestration, verify the actual Yandex AI Studio surface:

- Does the chosen API support the required function calling shape?
- Is the OpenAI Python SDK usable with Yandex `base_url` for the exact endpoints we need, including streaming and tool calls?
- Which features require Yandex SDK or AI Studio UI rather than OpenAI-compatible calls?
- What are the auth, folder/project, quota and logging requirements?

Output: a short compatibility matrix: `feature -> works / partial / blocked / unknown`.

### Spike 1: Data map

Take 5 representative Rosstat/World Bank Parquet files and build:

- schema.
- row count.
- min/max period.
- geo coverage.
- unit fields.
- source URL/provenance.

Compare DuckDB, pandas/pyarrow, Polars for this.

### Spike 2: Retrieval bakeoff

On 10-15 manually labeled queries, compare:

- simple keyword/fuzzy.
- DuckDB/SQLite FTS.
- embeddings + FAISS/Chroma/Yandex.
- hybrid lexical+dense.
- hybrid + rerank.

Measure Recall@5, MRR, and "can prove coverage".

### Spike 3: Query understanding

Compare:

- rule parser.
- LLM JSON extraction.
- classifier + slot extraction.

Measure slot accuracy for geography, period, metric, ambiguity, output type.

### Spike 4: Deterministic extraction script

For 2 simple and 2 comparative queries, generate:

- SQL or Python script.
- output CSV.
- provenance table.

Check rerun from clean environment.

### Spike 5: Answer guard

Generate answers from structured facts. Then run numeric/citation checker:

- extract numbers from answer.
- verify each appears in fact table.
- verify each has source link.

### Spike 6: UX trace prototype

Build a paper/UI mock or minimal Streamlit/Gradio flow:

- steps.
- source candidates.
- accepted/rejected reasons.
- artifact downloads.

Evaluate with one non-programmer reading the screen.

---

## 16. Recommended Documentation Corrections

These are documentation hygiene changes, not architecture decisions:

- Replace "RAG-index" in requirements with "search/retrieval layer over source metadata".
- Replace "RAG fully eliminates hallucinations" with "retrieval + deterministic extraction + citation validation reduce unsupported numeric claims; RAG alone does not guarantee correctness".
- Split requirements into capability vs candidate implementation:
  - Capability: find relevant source metadata.
  - Candidate tools: FTS/BM25, vector search, hybrid, AI Studio File Search.
- Keep "MCP" as an optional integration style, not a requirement.
- Keep "agent" as UX/workflow possibility, not necessarily autonomous multi-step loop.
- Add a "Decision matrix" phase artifact before any implementation plan.

---

## 17. Source Notes

Primary/docs sources checked:

- Technical task PDF in repo: `НЦСЭД ТЗ.pdf`.
- Project docs: `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`, `INFO.md`.
- Parallel exploration draft reviewed and partially integrated: `.planning/EXPLORATION.md`.
- Yandex AI Studio agents overview: https://aistudio.yandex.ru/docs/en/ai-studio/concepts/agents/
- Yandex AI Studio function calling: https://aistudio.yandex.ru/docs/en/ai-studio/concepts/generation/function-call
- Yandex AI Studio AI Search overview: https://aistudio.yandex.ru/docs/en/ai-studio/concepts/search/
- Yandex AI Studio Vector Store: https://aistudio.yandex.ru/docs/en/ai-studio/concepts/search/vectorstore.html
- Yandex AI Studio embeddings: https://aistudio.yandex.ru/docs/ru/ai-studio/concepts/embeddings
- Yandex AI Studio MCP Hub: https://aistudio.yandex.ru/docs/en/ai-studio/concepts/mcp-hub/
- DuckDB Parquet docs: https://duckdb.org/docs/current/data/parquet/overview
- DuckDB FTS extension: https://duckdb.org/docs/current/core_extensions/full_text_search
- pandas `read_parquet`: https://pandas.pydata.org/docs/reference/api/pandas.read_parquet.html
- PyArrow Parquet: https://arrow.apache.org/docs/python/parquet.html
- Polars lazy query optimization: https://docs.pola.rs/user-guide/lazy/query-plan/
- FAISS docs: https://faiss.ai/
- Qdrant hybrid queries: https://qdrant.tech/documentation/search/hybrid-queries/
- CKAN API: https://docs.ckan.org/en/latest/api/
- World Bank Indicators API: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation
- SDMX standards: https://sdmx.org/standards-2/
- Streamlit chat elements: https://docs.streamlit.io/develop/api-reference/chat
- Gradio ChatInterface: https://www.gradio.app/docs/gradio/chatinterface
- Chainlit overview: https://docs.chainlit.io/get-started/overview
- Chainlit steps/trace concepts: https://docs.chainlit.io/concepts/step
- Chainlit streaming: https://docs.chainlit.io/advanced-features/streaming
- FastAPI WebSockets: https://fastapi.tiangolo.com/advanced/websockets/
- LangGraph docs: https://docs.langchain.com/oss/python/langgraph
- LlamaIndex Workflows: https://developers.llamaindex.ai/python/llamaagents/workflows/
- Haystack Pipelines: https://docs.haystack.deepset.ai/docs/pipelines
- Ragas metrics: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/
- DeepEval metrics: https://deepeval.com/docs/metrics-introduction
- Promptfoo: https://www.promptfoo.dev/docs/intro/
- Benchmark note: "From BM25 to Corrective RAG: Benchmarking Retrieval Strategies for Text-and-Table Documents", arXiv 2604.01733, submitted 2026-04-02: https://arxiv.org/abs/2604.01733

---

## 18. Bottom Line

The decision space should stay open until we run at least small bakeoffs. The project should be described as:

> A fact-grounded data assistant with deterministic numeric extraction, source provenance, artifact workflow, and explainable search over heterogeneous statistical sources.

Not as:

> A RAG chatbot with embeddings.

That distinction matters. The first statement preserves many viable implementations; the second prematurely chooses one family of tools and hides the harder parts: source coverage, methodology, deterministic extraction, validation, and UX trace.
