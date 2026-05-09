# Data / Retrieval Owner Onboarding

Документ для человека, который берет на себя слой данных, поиска источников и детерминированного извлечения в проекте DataAgent.

Цель: быстро ввести в контекст проекта, объяснить архитектурные решения простым языком, зафиксировать границы ответственности и дать понятный список первых задач.

## 1. Зачем существует DataAgent

DataAgent - это ИИ-ассистент для экономистов и аналитиков. Пользователь пишет обычный исследовательский запрос:

- "Покажи динамику ВВП стран БРИКС за 2015-2024"
- "Как связаны урбанизация и рождаемость по странам?"
- "Дай инфляцию по России за последние 10 лет"
- "Изучи торговлю между Россией и Казахстаном"
- "Собери датасет по реальным доходам населения"

Система должна не просто красиво ответить текстом. Она должна пройти почти весь цикл data-специалиста:

1. Понять исследовательский смысл запроса.
2. Формализовать географию, период, показатели, единицы, нужную гранулярность.
3. Найти подходящие источники данных.
4. Проверить, что в источниках реально есть нужные годы, страны, регионы, показатели и значения.
5. Детерминированным кодом извлечь числа.
6. Собрать датасет, manifest, скрипт сборки и ссылки на источники.
7. Объяснить результат человеку и показать trace: что искали, что выбрали, что отвергли и почему.

Главный принцип проекта:

```text
LLM помогает понять задачу, выбрать путь и объяснить результат.
Числа извлекает только deterministic code из проверенных источников.
```

Если модель "помнит", что ВВП России был таким-то, нам это не подходит. Число считается валидным только если оно пришло из нашего extractor-а, DatasetArtifact-а или trusted source adapter-а.

## 2. Почему роль Data / Retrieval Owner критична

В этом проекте data/retrieval слой - не вспомогательная часть. Это фундамент доверия.

LLM может ошибаться:

- выбрать похожий, но не тот показатель;
- перепутать страну и агрегат;
- смешать годовые и квартальные данные;
- выдумать значение, если extractor ничего не вернул;
- принять metadata coverage за фактическое наличие значений;
- не заметить, что единицы измерения разные.

Поэтому Data / Retrieval Owner отвечает за слой, который не дает агенту "улететь":

- каталог источников;
- поиск по метаданным;
- source candidate cards;
- coverage preview;
- deterministic extractors;
- нормализацию FedStat;
- адаптер World Bank;
- клиент CKAN/НЦСЭД;
- source links and provenance;
- rejection reasons;
- dataset artifacts;
- data-side тесты.

Если этот слой надежный, агентная часть становится управляемой. Если этот слой слабый, даже самая умная модель будет давать красивые, но ненадежные ответы.

## 3. Что уже известно о данных

Основные материалы лежат в planning-документах:

- `.planning/PROJECT.md` - требования и ограничения проекта.
- `.planning/DATA_REPORT.md` - подробный отчет по FedStat, World Bank и CKAN.
- `.planning/ARCHITECTURE_STACK.md` - целевая архитектура.
- `.planning/STATE.md` - текущее состояние проекта.

Локальные дампы не коммитятся в git. Они лежат вне репозитория:

```text
/Users/a/Downloads/dumps/fedstatru/fedstatru.zip
/Users/a/Downloads/dumps/wb/data.zip
/Users/a/Downloads/dumps.zip
```

В репозитории сейчас есть только минимальная заготовка:

```text
app/
  __init__.py
  llm/
    __init__.py
    yandex_ai_studio.py
requirements.txt
docs/
  PROJECT_WORKFLOW.md
```

То есть data/retrieval слой еще практически не реализован. Это хорошо: можно сразу построить его правильно.

## 4. Источники данных и их роли

### 4.1. FedStat / Росстат / ЕМИСС

Источник: локальный дамп `fedstatru.zip` и CKAN-пакеты `emiss_*`.

Роль:

- российская официальная статистика;
- региональные и ведомственные показатели;
- ВВП РФ по Росстату;
- ИПЦ, доходы, зарплаты, рождаемость, демография;
- показатели с русскоязычными методологическими описаниями.

Что важно:

- это самый ценный, но самый сложный источник;
- много Parquet-файлов в широком формате;
- первая строка часто является фактическим заголовком;
- колонки могут называться `column00`, `column01`, `column0`, `column1`;
- годовые значения часто лежат в отдельных колонках;
- нужно делать wide-to-long normalizer;
- `metadata.jsonl` нельзя считать полным каталогом;
- clean JSONL есть только для небольшой части показателей.

В `.planning/DATA_REPORT.md` зафиксировано:

- Parquet-файлов: 7 328.
- JSON metadata-файлов: 7 330.
- clean JSONL gzip-файлов: 84.
- `metadata.jsonl` фактически неполный.
- `metdata.csv` полезен как основной табличный слой метаданных.
- `indicators.csv` содержит больше кодов, чем реально есть в metadata/parquet.

Пример сложного, но важного показателя:

```text
57319 - Валовой внутренний продукт в рыночных ценах в соответствии с методологией СНС 2008
```

Для него Parquet примерно такой:

```text
row 0:
  column00 = "Вид цены"
  column01 = "Классификатор объектов административно-территориального деления (ОКАТО)"
  column02 = "Единица измерения"
  column03 = "Период"
  column04..column17 = 2011..2024

row 1:
  Вид цены = "8 Постоянные цены 2011 года"
  ОКАТО = "643 Российская Федерация"
  Единица измерения = "385 миллион рублей"
  Период = "54 I квартал"
  2011 = 13386065.5
```

То есть нельзя просто ожидать колонки `year` и `value`. Их надо получить нормализацией.

### 4.2. World Bank

Источник: локальный дамп `wb/data.zip`.

Роль:

- международные сравнения;
- страны и агрегаты;
- GDP, CPI, population, fertility, urbanization, unemployment;
- быстрые demo-запросы;
- источник, с которого лучше начинать end-to-end MVP.

Что важно:

- около 29 470 индикаторов;
- 296 стран, территорий и агрегатов;
- Parquet-формат намного регулярнее, чем FedStat;
- типичная схема: `indicator_id`, `country_id`, `date`, `value`;
- удобно строить coverage preview по индикатору, стране и периоду;
- нужно отличать реальные страны от агрегатов: World, Europe & Central Asia, income groups.

World Bank хорош для запросов:

- "ВВП стран БРИКС"
- "Инфляция по странам Европы"
- "Связь урбанизации и рождаемости"
- "Динамика населения и ВВП по странам"

World Bank хуже для:

- российских регионов;
- ведомственной статистики РФ;
- детальной торговли Россия-Казахстан;
- показателей, которые существуют только в российских источниках.

### 4.3. НЦСЭД CKAN API

API:

```text
https://repository.nsedc.ru/api/3/action/package_search
https://repository.nsedc.ru/api/3/action/package_show
```

Роль:

- live discovery;
- полный каталог НЦСЭД;
- свежие ресурсы;
- прямые ссылки на `parquet`, `csv.gz`, `xls.zip`, `HTML`;
- источник provenance для UI и manifest.

Важное правило:

```text
CKAN - это trusted catalog API, но не general web search.
```

Мы используем его ограниченно:

- ищем пакеты;
- получаем ресурсы;
- берем metadata;
- кешируем только продвинутые/выбранные карточки;
- не грузим огромные ответы прямо в LLM context.

Пример:

```text
GET https://repository.nsedc.ru/api/3/action/package_search?q=57319&rows=1
```

Возвращает пакет:

```text
name: emiss_57319
title: Валовой внутренний продукт ... (ЕМИСС)
resources:
  57319.csv.gz
  57319.parquet
  57319.xls.zip
  HTML source page
```

CKAN search шумный. По широкому запросу вроде `ВВП` может быть тысячи результатов. Поэтому поверх CKAN нужен собственный rerank/compression layer.

## 5. Как агентная часть связана с data layer

Если человек не работал с агентами, проще думать так:

```text
Агент - это не магия.
Агент - это оркестратор, который вызывает обычные функции и собирает их результаты.
```

Для Data / Retrieval Owner важны не внутренние промпты, а стабильные функции:

```text
search_catalog(query, filters) -> SourceCandidateCard[]
preview_coverage(source_id, filters) -> CoverageReport
extract_dataset(extraction_plan) -> DatasetArtifact
```

Agent/Core слой будет делать примерно следующее:

1. Получает пользовательский запрос.
2. LLM превращает его в IntentArtifact.
3. Вызывает data/retrieval функции.
4. Получает кандидаты источников.
5. Просит coverage preview.
6. Строит extraction plan.
7. Вызывает deterministic extractor.
8. Получает DatasetArtifact.
9. Отдает Narrator-у только подтвержденные факты, ссылки и warnings.

Именно поэтому Data / Retrieval Owner должен возвращать строго типизированные артефакты, а не произвольные словари "как удобно сейчас".

## 6. Главные контракты между командами

Ниже не финальный код, а целевая форма контрактов. Их должен утвердить Core / Integration Owner, но Data / Retrieval Owner должен проектировать свои функции вокруг них.

### 6.1. SourceCandidateCard

Карточка найденного источника. Это не данные, а кандидат на использование.

```python
class SourceCandidateCard(BaseModel):
    candidate_id: str
    source: Literal["fedstat", "world_bank", "nsed_ckan"]
    dataset_id: str
    indicator_id: str | None = None
    title: str
    description: str | None = None
    unit: str | None = None
    periodicity: str | None = None
    time_coverage_hint: str | None = None
    geo_coverage_hint: str | None = None
    dimensions: list[str] = []
    organization: str | None = None
    source_url: str | None = None
    local_path: str | None = None
    api_url: str | None = None
    license: str | None = None
    match_mode: Literal[
        "exact",
        "code",
        "lexical",
        "semantic",
        "proxy",
        "ckan_discovery",
        "methodology_match",
    ]
    why_matched: str
    risk_flags: list[str] = []
    availability_flags: list[str] = []
    score: float | None = None
```

Принципы:

- `why_matched` обязателен.
- `source_url` желателен всегда, если есть.
- `risk_flags` лучше заполнить честно, чем скрыть проблему.
- `match_mode=proxy` должен быть виден пользователю.

Пример:

```json
{
  "candidate_id": "fedstat:57319",
  "source": "fedstat",
  "dataset_id": "57319",
  "indicator_id": "57319",
  "title": "Валовой внутренний продукт в рыночных ценах ...",
  "unit": "миллион рублей",
  "periodicity": "квартальная/годовая",
  "source_url": "https://www.fedstat.ru/indicator/57319",
  "match_mode": "code",
  "why_matched": "Код 57319 найден в CKAN/FedStat metadata; название соответствует ВВП",
  "risk_flags": ["нужно выбрать вид цены", "покрытие зависит от периода"],
  "availability_flags": ["has_local_parquet", "has_ckan_resource"]
}
```

### 6.2. CoverageReport

CoverageReport отвечает на вопрос: можно ли из этого источника реально получить нужные данные?

```python
class CoverageReport(BaseModel):
    source: str
    dataset_id: str
    verdict: Literal["enough", "partial", "not_enough", "unknown"]
    requested_filters: dict[str, Any]
    available_periods: list[str] = []
    available_geographies: list[str] = []
    available_dimensions: dict[str, list[str]] = {}
    non_null_observations: int | None = None
    missing_requested_items: list[str] = []
    suggested_filters: dict[str, Any] = {}
    warnings: list[str] = []
    can_continue_without_user: bool
    needs_user_clarification: bool
    clarification_question: str | None = None
```

Важно:

- metadata coverage не равно data coverage;
- по возможности проверять non-null values;
- для FedStat обязательно показывать измерения;
- для World Bank обязательно различать страны и агрегаты;
- если можно продолжить с разумным допущением, вернуть `can_continue_without_user=True`, но добавить warning.

### 6.3. ExtractionPlan

ExtractionPlan - это не произвольный Python-код от LLM, а структурированный план безопасных операций.

```python
class ExtractionPlan(BaseModel):
    plan_id: str
    source: Literal["fedstat", "world_bank", "nsed_ckan"]
    dataset_id: str
    operation: Literal[
        "read_series",
        "filter_dimensions",
        "join_indicators",
        "compute_derived_metric",
        "normalize_wide_table",
        "rebase_index",
        "aggregate",
    ]
    filters: dict[str, Any]
    output_columns: list[str]
    expected_unit: str | None = None
    source_url: str | None = None
    safety_notes: list[str] = []
```

Главная идея:

```text
LLM выбирает операцию и параметры.
Код исполняет только известные безопасные операции.
```

### 6.4. DatasetArtifact

DatasetArtifact - главный результат data layer. Только из него можно брать числа для ответа.

```python
class DatasetArtifact(BaseModel):
    artifact_id: str
    source: str
    dataset_id: str
    title: str
    rows: int
    columns: list[str]
    data_preview: list[dict[str, Any]]
    file_paths: dict[str, str] = {}
    source_urls: list[str]
    manifest_path: str | None = None
    generated_script_path: str | None = None
    units: dict[str, str] = {}
    filters_applied: dict[str, Any] = {}
    quality_flags: list[str] = []
    warnings: list[str] = []
```

Нужно стремиться, чтобы у каждого artifact были:

- CSV/Parquet output path;
- manifest JSON;
- source URLs;
- filters applied;
- units;
- warnings;
- row count;
- preview.

### 6.5. SourceRejection

Пользователь должен видеть не только выбранные источники, но и отвергнутые.

```python
class SourceRejection(BaseModel):
    candidate_id: str
    title: str
    rejection_reason: str
    severity: Literal["low", "medium", "high"]
    alternative_used: str | None = None
```

Примеры причин:

- "Показатель похож по названию, но имеет другую единицу измерения."
- "В metadata заявлен период 2010-2024, но для выбранного региона значения отсутствуют."
- "Источник является агрегатом World, а пользователь запросил конкретную страну."
- "CKAN package содержит ресурс, но формат не поддержан MVP extractor-ом."

## 7. Что именно должна реализовать зона Data / Retrieval

Рекомендуемая структура модулей:

```text
app/
  contracts/
    data.py
  retrieval/
    catalog_builder.py
    catalog_store.py
    lexical_search.py
    ranker.py
    ckan_client.py
    synonyms.py
  data/
    paths.py
    schemas.py
    fedstat_catalog.py
    fedstat_normalizer.py
    fedstat_extractor.py
    wb_catalog.py
    wb_adapter.py
    coverage.py
    duckdb_runner.py
  artifacts/
    manifest.py
    exporters.py
```

Если Core owner уже создал `app/contracts`, не дублировать модели в `app/data`. Импортировать общие Pydantic-модели.

### 7.1. Catalog builders

Задача catalog builder-а - превратить сырые metadata в компактные карточки, пригодные для поиска.

FedStat catalog builder:

- читает `metdata.csv`;
- читает `metadata/{code}.json`, если нужно;
- проверяет наличие `parquet/{code}.parquet`;
- проверяет наличие `clean_jsonl/{code}.jsonl.gz`;
- добавляет `source_url`;
- добавляет availability flags;
- добавляет quality flags;
- сохраняет normalized catalog.

World Bank catalog builder:

- читает `indicators.json`;
- читает `countries.json`;
- читает metadata/source notes;
- проверяет наличие Parquet по indicator id;
- строит indicator cards;
- отдельно хранит country/aggregate lookup.

CKAN catalog sample/cache:

- делает bounded `package_search`;
- преобразует package results в SourceCandidateCard;
- вызывает `package_show` только для top-N;
- кеширует выбранные package metadata и resource URLs.

### 7.2. Search / retrieval

MVP-подход:

1. Нормализовать запрос.
2. Добавить синонимы.
3. Выполнить lexical search по catalog cards.
4. Отфильтровать по source/geography/period, если возможно.
5. Переранжировать эвристиками.
6. Вернуть top-N SourceCandidateCard.

Не начинать с embeddings как единственного поиска. На экономических данных точные коды, аббревиатуры, русские названия и единицы измерения очень важны.

Синонимы, которые стоит завести рано:

```text
ВВП -> GDP, gross domestic product, валовой внутренний продукт
инфляция -> CPI, consumer price index, индекс потребительских цен
рождаемость -> fertility, birth rate
население -> population
безработица -> unemployment
урбанизация -> urban population
доходы -> income, disposable income
Россия -> Russian Federation, RUS, РФ
Казахстан -> Kazakhstan, KAZ
БРИКС -> BRA, RUS, IND, CHN, ZAF plus current BRICS policy if needed
```

Для MVP можно сделать простую эвристику score:

```text
+ exact code match
+ exact phrase in title
+ synonym match in title
+ source preferred for query type
+ has local parquet
+ has clean_jsonl
+ period coverage likely includes requested range
+ geography likely includes requested country/region
- metadata only
- unknown unit
- requires unsupported format
- aggregate used when country requested
```

### 7.3. Coverage preview

Coverage preview - обязательный слой между search и extraction.

Он должен отвечать:

- какие периоды доступны;
- какие географии доступны;
- какие dimension values есть;
- есть ли non-null values;
- какой лучший срез выбрать;
- можно ли продолжить без уточнения;
- какие warnings показать.

Для World Bank:

- проверить indicator parquet;
- отфильтровать countries;
- проверить годы;
- посчитать non-null values;
- вернуть missing countries/years.

Для FedStat:

- определить, есть ли clean_jsonl;
- если есть, быстро inspect;
- если только wide parquet, прочитать schema/header row;
- определить dimension columns и year columns;
- показать доступные dimension values;
- не читать огромный файл полностью без необходимости.

Для CKAN:

- package metadata не считается coverage;
- package resources - это только availability;
- coverage появляется после скачивания/открытия конкретного resource или сопоставления с локальным FedStat/WB.

### 7.4. Extractors

World Bank extractor:

```text
input:
  indicator_id
  country_ids
  years

output:
  canonical long dataframe:
    source
    dataset_id
    indicator_id
    indicator_name
    geo_id
    geo_name
    geo_type
    period
    period_type
    value
    unit
    dimensions
    source_url
    retrieved_at
    quality_flags
```

FedStat clean_jsonl extractor:

- использовать как самый быстрый путь для тех 84 показателей, где clean jsonl есть;
- привести к тому же canonical long format;
- сохранить исходные dimension names;
- выделить unit, period, year, value.

FedStat wide parquet normalizer:

- прочитать первую строку как header;
- найти year columns;
- остальные колонки считать dimensions;
- выполнить melt wide-to-long;
- привести value к numeric;
- сохранить исходные dimension values;
- не терять коды в строках вроде `643 Российская Федерация`;
- добавить source_url и indicator metadata.

Важно: нормализатор FedStat должен быть source-specific, а не "универсальный магический parser". Лучше покрыть 5 важных показателей надежно, чем 7 328 плохо.

### 7.5. Artifacts and manifest

Каждое извлечение должно оставлять след:

```text
artifacts/
  runs/
    <run_id>/
      dataset.csv
      dataset.parquet
      manifest.json
      extraction_plan.json
      source_candidates.json
      rejected_sources.json
      coverage_report.json
```

Manifest должен отвечать:

- откуда взяли данные;
- какие filters применили;
- какие единицы измерения;
- когда извлекли;
- какой код/операция использовалась;
- сколько строк получили;
- какие warnings есть;
- какие источники отвергли.

## 8. Канонический long format

Очень желательно, чтобы все источники приводились к одному формату:

```text
source
dataset_id
indicator_id
indicator_name
geo_id
geo_name
geo_type
period
period_type
value
unit
dimensions
source_url
retrieved_at
quality_flags
```

Почему это важно:

- UI сможет показывать таблицу одинаково для FedStat и World Bank;
- Methodology Critic сможет проверять единицы и периоды одинаково;
- Visualization layer сможет строить график по DatasetArtifact;
- evals смогут сравнивать поведение на разных источниках;
- Agent/Core layer не будет знать внутренности каждого формата.

Не обязательно все поля идеально заполнены на первом MVP. Но структура должна быть такой с самого начала.

## 9. Как думать о "source-bound" поведении

В проекте запрещены ответы вида:

```text
По данным Всемирного банка, ВВП России в 2024 году составил ...
```

если внутри нет DatasetArtifact или manifest, где видно:

- indicator id;
- country id;
- year;
- value;
- source URL;
- timestamp;
- filters;
- extraction code path.

Правильная модель:

```text
Не найдено в DatasetArtifact -> не существует для финального ответа.
```

Если данные не найдены, хороший ответ не "примерно...", а:

```text
Я проверил World Bank indicator X, FedStat candidates Y/Z и CKAN query Q.
Для запрошенного периода 2025 нет non-null значений.
Могу показать ряд до 2024 или поискать альтернативный источник.
```

## 10. Что Data / Retrieval Owner не должен делать

Не нужно:

- строить весь агентный граф;
- писать промпты для Narrator-а;
- делать Streamlit UI;
- решать всю продуктовую UX-логику;
- нормализовать весь FedStat сразу;
- коммитить dumps;
- отдавать LLM сырые Parquet/CSV;
- делать embeddings по числовым таблицам;
- писать произвольный код extraction, который потом будет сложно воспроизвести;
- скрывать warnings, потому что "портят демо".

Нужно:

- дать надежные функции;
- вернуть компактные typed artifacts;
- хранить provenance;
- честно маркировать риски;
- сделать маленький, но работающий end-to-end на выбранных источниках.

## 11. Первые задачи на 1-2 дня

### Task A: Paths and data availability

Сделать модуль, который знает, где искать локальные dumps.

Пример:

```text
app/data/paths.py
```

Функции:

```python
get_data_root() -> Path
get_fedstat_zip_path() -> Path
get_wb_zip_path() -> Path
validate_local_dumps() -> DataAvailabilityReport
```

Важно:

- пути должны задаваться через `.env`;
- дефолт можно брать из `/Users/a/Downloads/dumps`;
- если данных нет, ошибка должна быть понятной.

### Task B: World Bank MVP adapter

Начать с World Bank, потому что он регулярнее.

Минимум:

- прочитать metadata;
- найти индикатор по тексту/коду;
- найти страны по имени/ISO;
- извлечь ряд по indicator/country/year;
- вернуть canonical long dataframe;
- сохранить DatasetArtifact.

Тестовый запрос:

```text
GDP BRICS 2015-2023
```

или:

```text
Inflation Russia Kazakhstan 2015-2023
```

### Task C: FedStat catalog builder

Не нормализовать все данные. Сначала собрать catalog.

Минимум:

- прочитать `metdata.csv`;
- взять `code`, `name`, `url`, units, periodicity, time range, methodology, rows;
- проверить наличие local parquet/clean_jsonl;
- создать searchable cards.

Первые коды для ручной проверки:

```text
57319 - ВВП в рыночных ценах
40578 - ВВП России по ППС
40579 - ВВП на душу по ППС
33568 - базовый индекс потребительских цен
61028 - индексы потребительских цен на отдельные товары и услуги
30973 - возрастные коэффициенты рождаемости
```

### Task D: CKAN bounded client

Минимум:

```python
search_packages(query: str, rows: int = 10) -> list[dict]
show_package(name_or_id: str) -> dict
```

Важно:

- timeout;
- rows limit;
- не передавать сырой полный ответ в LLM;
- преобразовывать в SourceCandidateCard;
- сохранять resource URLs.

### Task E: First `find_data`

Одна публичная функция:

```python
find_data(query: str, filters: SearchFilters | None = None, limit: int = 10) -> list[SourceCandidateCard]
```

Она может сначала быть простой:

- локальный WB catalog;
- локальный FedStat catalog;
- CKAN только как fallback или explicit source;
- lexical search;
- эвристический score.

Главное - стабильный контракт.

## 12. Тестовые запросы для data/retrieval слоя

Нужны не только happy path, но и ошибки.

Простой:

```text
Какой ВВП России в 2024 году?
```

Ожидаем:

- FedStat 57319 или WB GDP;
- clarification/warning по методологии: рубли Росстата vs current US$ World Bank.

Сравнительный:

```text
ВВП стран БРИКС за 2015-2023
```

Ожидаем:

- World Bank GDP indicator;
- countries list;
- non-null coverage.

Производная метрика:

```text
Как изменилась реальная покупательная способность доходов в России с 2015 года?
```

Ожидаем:

- не делать сразу, если нет надежного набора;
- вернуть candidates и сказать, какие показатели нужны.

Исследовательский:

```text
Связь урбанизации и рождаемости по странам
```

Ожидаем:

- World Bank urban population + fertility;
- join by country/year.

Неоднозначный:

```text
Дай инфляцию
```

Ожидаем:

- needs clarification: страна, период, annual/monthly, CPI/inflation rate.

No data:

```text
Инфляция в Северной Корее за 2020-2024
```

Ожидаем:

- попытки WB/CKAN;
- честный not_found/partial coverage.

CKAN discovery:

```text
Найди источник ЕМИСС по коду 57319
```

Ожидаем:

- CKAN package `emiss_57319`;
- resources list;
- source URL.

## 13. Минимальные проверки качества

Для каждого adapter-а нужны тесты.

World Bank:

- indicator lookup by exact code;
- indicator lookup by title synonym;
- country lookup by ISO and Russian/English name;
- extraction returns non-empty for known indicator/country/year;
- missing year returns warning, not fake value;
- aggregate/country distinction is preserved.

FedStat:

- catalog contains known code `57319`;
- `metadata.jsonl` is not used as full catalog;
- availability flags are correct;
- wide parquet header detection works on `57319`;
- clean_jsonl extractor works on at least one available clean file;
- huge file is not loaded accidentally in full during simple inspect.

CKAN:

- `package_search` works with timeout;
- rows limit enforced;
- `emiss_57319` maps to SourceCandidateCard;
- resources are compressed;
- bad network response returns controlled error.

Artifacts:

- DatasetArtifact always has source_urls;
- manifest exists for extracted dataset;
- row count matches saved file;
- warnings survive into artifact.

## 14. How this connects to Streamlit and trace

UI owner will need from Data / Retrieval:

- list of candidates;
- chosen source;
- rejected sources;
- coverage report;
- dataset preview;
- downloadable files;
- manifest;
- warnings.

Trace events will be created by Core/UI, but data functions should return enough structured information to render them.

Example human-readable trace:

```text
1. Searched World Bank catalog for "GDP BRICS"
2. Found NY.GDP.MKTP.CD with exact GDP match
3. Resolved countries: BRA, RUS, IND, CHN, ZAF
4. Coverage preview: 2015-2023 enough, 2024 partial
5. Extracted 45 observations
6. Saved dataset.csv and manifest.json
```

This is what judges/users should see. Not a hidden black box.

## 15. GSD workflow for this owner

The repository uses GSD.

For non-trivial work:

```text
$gsd-discuss-phase <N>
$gsd-plan-phase <N>
$gsd-execute-phase <N>
$gsd-verify-work <N>
```

For this owner, each GSD plan should explicitly say:

- owned files;
- source covered;
- contract returned;
- verification command;
- known limitations;
- integration point with Core/UI.

Good GSD task:

```text
Implement WorldBankAdapter that returns DatasetArtifact for indicator/country/year filters.
Owned files: app/data/wb_adapter.py, tests/test_wb_adapter.py.
Does not modify: app/workflow, app/ui.
Verification: pytest tests/test_wb_adapter.py.
```

Bad GSD task:

```text
Make data work.
```

## 16. Coordination rules with the other two owners

### With Core / Integration Owner

Agree on:

- Pydantic contracts;
- public function signatures;
- error model;
- artifact directory layout;
- how run_id is passed;
- where trace events are created.

Do not silently change:

- field names in contracts;
- meanings of verdicts;
- path layout;
- expected return types.

### With UI / Evaluation Owner

Provide:

- stable mock examples;
- sample DatasetArtifact JSON;
- sample CoverageReport JSON;
- sample rejected sources;
- example prompts.

UI can build against mocks first. Data layer later swaps in real outputs.

### With everyone

Any number shown to user must be traceable:

```text
number -> DatasetArtifact -> manifest -> source URL + extraction filters
```

If that chain breaks, the answer should not be shipped.

## 17. Practical implementation order

Recommended order:

1. Define or adopt contracts.
2. Implement paths/data availability checks.
3. Build WB catalog.
4. Implement WB search and extraction.
5. Build FedStat catalog.
6. Implement FedStat inspect/coverage for selected codes.
7. Implement CKAN bounded client.
8. Implement unified `find_data`.
9. Implement artifact/manifest export.
10. Add tests for known cases.
11. Integrate with Core run API.
12. Add performance guardrails for large FedStat files.

Do not start with:

- all-source universal abstraction;
- full FedStat normalization;
- vector search;
- LangGraph internals;
- fancy ranking;
- charts.

Small reliable pipeline beats broad unreliable coverage.

## 18. Suggested MVP acceptance criteria

Data / Retrieval MVP is acceptable when:

- `find_data("GDP BRICS")` returns World Bank GDP candidates.
- `find_data("ВВП России")` returns FedStat and/or WB candidates with clear source distinction.
- `preview_coverage` can say enough/partial/not_enough for WB indicator/countries/years.
- WB extractor produces DatasetArtifact with source URLs.
- FedStat catalog includes known indicators and availability flags.
- CKAN client finds `emiss_57319` and resource links.
- No final numeric answer can be produced without DatasetArtifact.
- At least 5 golden prompts have data-side expected behavior.

## 19. Common mistakes to avoid

### Mistake: treating metadata as data

Bad:

```text
Metadata says "2011-2025", therefore we answer for 2025.
```

Good:

```text
Metadata says "2011-2025"; coverage preview checks non-null values for requested slice.
```

### Mistake: hiding ambiguity

Bad:

```text
"ВВП России" -> silently choose World Bank current US$.
```

Good:

```text
Return candidates:
- FedStat GDP in million rubles
- WB GDP current US$
Then Core can ask clarification or choose with warning.
```

### Mistake: overusing LLM

Bad:

```text
Ask LLM to inspect CSV and tell us the value.
```

Good:

```text
Code reads CSV/Parquet, filters rows, returns value with source.
```

### Mistake: returning raw CKAN response

Bad:

```text
Put 100 package_search results into model context.
```

Good:

```text
Convert top results into compact SourceCandidateCard with reason and resource links.
```

### Mistake: building all FedStat first

Bad:

```text
Normalize 7,328 Parquet files before any demo works.
```

Good:

```text
Catalog all, normalize selected important indicators, expand later.
```

## 20. Glossary

**Agent** - orchestrator that decides which function/tool to call next. It should not invent data.

**Artifact** - structured output of a step: candidate card, coverage report, dataset, manifest, critique, final answer.

**Coverage preview** - deterministic check that requested data exists before extraction/final answer.

**DatasetArtifact** - extracted dataset plus metadata, files, source links and warnings. The only allowed source of final numeric facts.

**FedStat / ЕМИСС** - Russian official statistics source. Rich but structurally messy.

**World Bank** - international statistics source. Cleaner and better for MVP comparisons.

**CKAN** - catalog API used by НЦСЭД repository. Good for discovery and resource links.

**SourceCandidateCard** - compact representation of a possible source returned by search.

**Provenance** - traceable origin of data: source, URL, filters, extraction time, method.

**Rejection log** - structured record of sources considered but not used.

**Source-bound** - system only answers from known, traceable sources.

## 21. The mental model to keep

The product is not:

```text
chatbot + documents
```

It is:

```text
research planner + source catalog + deterministic data engine + traceable artifacts
```

Data / Retrieval Owner owns the part that makes the whole thing trustworthy.

The best possible contribution is not a clever model prompt. It is a boringly reliable chain:

```text
query
-> source candidates
-> coverage report
-> extraction plan
-> dataset artifact
-> manifest
-> final answer with sources
```

If that chain is solid, the agent can be imperfect and the product will still be credible. If that chain is weak, the agent can sound brilliant and still fail the core requirement.
