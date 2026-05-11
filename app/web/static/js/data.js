// ============ MOCK DATA & ARTIFACT BUILDERS ============

const AGENTS = [
  {
    id: "query",
    name: "Query Understanding",
    desc: "Извлечение параметров: страна = DE, период = 5 лет, тема = ИТ-импорт.",
    meta: { confidence: "0.97", entities: "[Germany, IT equipment]", period: "Q1'21 — Q4'25" },
    badges: [{ text: "Qwen-2.5-72B", cls: "" }],
    duration: 420
  },
  {
    id: "research",
    name: "Research Design",
    desc: "Гипотеза: рост импорта на фоне локализации. Группировка по кварталам и HS-коду.",
    meta: { schema: "EconomicAnalysis", indicators: "4", source: "Eurostat COMEXT" },
    badges: [{ text: "Pydantic", cls: "cloud" }, { text: "Принято", cls: "lime" }],
    duration: 980,
    hasArtifact: "pydantic"
  },
  {
    id: "search",
    name: "Dataset Search",
    desc: "Параллельный поиск в Qdrant + reranker. Выбран Eurostat Parquet (DS_059341).",
    meta: { candidates: "12", reranked: "3", chosen: "DS_059341.parquet" },
    badges: [{ text: "Qdrant", cls: "" }, { text: "BGE-rerank", cls: "" }],
    duration: 1100
  },
  {
    id: "schema",
    name: "Schema Inspector",
    desc: "Детерминированно: чтение метаданных Parquet. Колонки и типы валидированы.",
    meta: { columns: "11", rows: "4.2M", size: "182 MB" },
    badges: [{ text: "Deterministic", cls: "" }],
    duration: 240
  },
  {
    id: "script",
    name: "Script Generation",
    desc: "Генерация SQL для DuckDB. AST-проверка, dry run.",
    meta: { lang: "DuckDB SQL", lines: "23", dryRun: "ok" },
    badges: [{ text: "Dry run", cls: "lime" }, { text: "AST ✓", cls: "" }],
    duration: 1340,
    hasArtifact: "code"
  },
  {
    id: "exec",
    name: "Execution",
    desc: "DuckDB исполняет запрос. Retry-loop при ошибке.",
    meta: { runtime: "0.41 s", rows: "20", retries: "0" },
    badges: [{ text: "DuckDB 0.10", cls: "" }],
    duration: 410
  },
  {
    id: "analysis",
    name: "Analysis & Synthesis",
    desc: "Интерпретация датасета, цитирование источников.",
    meta: { insights: "3", citations: "2" },
    badges: [{ text: "Citing", cls: "cloud" }],
    duration: 760,
    hasArtifact: "chart"
  }
];

// quarterly time series
const SERIES_QUARTERS = [
  "Q1'21","Q2'21","Q3'21","Q4'21",
  "Q1'22","Q2'22","Q3'22","Q4'22",
  "Q1'23","Q2'23","Q3'23","Q4'23",
  "Q1'24","Q2'24","Q3'24","Q4'24",
  "Q1'25","Q2'25","Q3'25","Q4'25"
];
const SERIES_VALUES = [
  4820, 5130, 5440, 6010,
  6230, 6610, 6920, 7480,
  7050, 7320, 7790, 8240,
  8520, 8910, 9340, 9780,
  9650, 10120, 10580, 11240
];

const TABLE_ROWS = [
  ["Q4'24", "9 780", "+4.7%",  "Servers, GPU"],
  ["Q1'25", "9 650", "−1.3%",  "Networking"],
  ["Q2'25", "10 120","+4.9%",  "Servers, Storage"],
  ["Q3'25", "10 580","+4.5%",  "GPU, AI accel."],
  ["Q4'25", "11 240","+6.2%",  "GPU, Servers"]
];

// human-readable reasoning trace for the research design step
const REASONING_STEPS = [
  {
    name: "Понимание запроса",
    tag: "Query",
    text: "Пользователь спрашивает про <strong>импорт ИТ-оборудования в Германию</strong> за последние 5 лет. Извлекаю ключевые параметры: страна — <code>Германия</code>, период — <code>2021–2025</code>, разрез — <code>квартально</code>."
  },
  {
    name: "Уточнение контекста",
    tag: "Clarify",
    cls: "is-question",
    text: "<em>Под «ИТ-оборудованием» обычно понимаются HS-коды 8471 (вычислительная техника) и 8517 (сетевое оборудование). Беру оба, т.к. вопрос — про общую динамику.</em>"
  },
  {
    name: "Гипотеза",
    tag: "Hypothesis",
    text: "Ожидаю устойчивый рост: пост-пандемийная цифровизация + спрос на AI-инфраструктуру в 2024–2025. Возможен спад в Q1'25 из-за высокой базы Q4'24."
  },
  {
    name: "План индикаторов",
    tag: "Indicators",
    text: "Беру три индикатора: <code>import_value_eur</code> (объём в евро), <code>hs_code</code> (категория), <code>partner_iso</code> (страна-поставщик). Группирую по кварталу."
  },
  {
    name: "Источники данных",
    tag: "Sources",
    text: "Основной источник — <strong>Eurostat COMEXT</strong> (внешняя торговля ЕС, квартальная разбивка). Кросс-валидация — <strong>BMWK Monitor</strong> (отчёты Минэкономики ФРГ)."
  },
  {
    name: "Готов к запуску",
    tag: "Ready",
    cls: "is-final",
    text: "Если параметры устраивают — запускаю поиск датасетов в Qdrant и сборку SQL-скрипта в DuckDB."
  }
];

const SOURCES = [
  { num: 1, title: "Eurostat COMEXT — quarterly trade",  host: "ec.europa.eu/eurostat" },
  { num: 2, title: "BMWK Monitor 2025 Q4",                host: "bmwk.de/monitor" },
  { num: 3, title: "WTO Statistical Review 2025",         host: "wto.org/stats" },
  { num: 4, title: "OECD Trade in Goods",                 host: "stats.oecd.org" }
];

const PYDANTIC_CODE = [
  ['com', '# Research Design Artifact (auto-generated)'],
  ['nl'],
  ['kw',  'class '], ['fn', 'ITImportAnalysis'], ['pun','('], ['id','BaseModel'], ['pun',')'], ['pun',':'],
  ['nl'],
  ['id','    target_country'], ['pun',': '], ['id','str'], ['pun',' = '], ['str','"DE"'],
  ['nl'],
  ['id','    timeframe'],      ['pun',': '], ['id','str'], ['pun',' = '], ['str','"2021Q1-2025Q4"'],
  ['nl'],
  ['id','    indicators'],     ['pun',': '], ['id','List'],['pun','[str] = ['], ['str','"import_value_eur"'], ['pun',', '],
                                                                                 ['str','"hs_code"'], ['pun',', '],
                                                                                 ['str','"partner_iso"'], ['pun',']'],
  ['nl'],
  ['id','    granularity'],    ['pun',': '], ['id','str'], ['pun',' = '], ['str','"quarter"'],
  ['nl'],
  ['id','    sources'],        ['pun',': '], ['id','List'],['pun','[str] = ['], ['str','"Eurostat COMEXT"'], ['pun',', '],
                                                                                 ['str','"BMWK Monitor"'], ['pun',']'],
  ['nl'],
  ['id','    expected_output'],['pun',': '], ['id','str'], ['pun',' = '], ['str','"Quarterly trend chart + table"']
];

const SQL_CODE = [
  ['com','-- Quarterly IT imports — Germany'],
  ['kw','WITH '], ['fn','q '], ['kw','AS '], ['pun','('],
  ['nl'],
  ['kw','  SELECT '],
    ['fn','date_trunc'], ['pun','('], ['str',"'quarter'"], ['pun',', '], ['id','flow_date'], ['pun',') '], ['kw','AS '], ['id','quarter'], ['pun',','],
  ['nl'],
  ['kw','         SUM'], ['pun','('], ['id','value_eur'], ['pun',') '], ['kw','AS '], ['id','total_eur'],
  ['nl'],
  ['kw','  FROM '], ['id','read_parquet'], ['pun','('], ['str',"'s3://eurostat/comext_2021_2025.parquet'"], ['pun',')'],
  ['nl'],
  ['kw','  WHERE '], ['id','reporter_iso'], ['pun',' = '], ['str',"'DE'"],
  ['nl'],
  ['kw','    AND '], ['id','hs_code'], ['kw',' LIKE '], ['str',"'8471%'"], ['com','  -- ADP machines'],
  ['nl'],
  ['kw','  GROUP BY '], ['num','1'],
  ['nl'],
  ['pun',')'],
  ['nl'],
  ['kw','SELECT '], ['pun','*'], ['kw',' FROM '], ['id','q'], ['kw',' ORDER BY '], ['id','quarter'], ['pun',';']
];
