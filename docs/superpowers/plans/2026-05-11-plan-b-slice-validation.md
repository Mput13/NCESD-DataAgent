# Plan B — Slice Validation + Parquet Path Resolution

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **PREREQUISITE:** Plan A (schema hardening) MUST be completed first. Plan B assumes intent/coverage/critic schemas are already tolerant of LLM output shape mismatches.

**Goal:** Устранить два корневых источника `not_found` на уровне данных: (1) адаптеры не могут найти parquet-файлы если каталог хранит старые пути, (2) coverage помечает источники как `ok` не проверяя реально ли запрошенный срез (страна, период, индикатор) существует в данных.

**Architecture:** Два независимых изменения. Первое: `_parquet_path()` в обоих адаптерах получает новый шаг поиска через env vars `FEDSTAT_DUMPS_DIR` / `WORLD_BANK_DUMPS_DIR` перед выбросом `FileNotFoundError`. Второе: `CoverageReport` получает новые поля (`matched_geographies`, `matched_periods`, `requested_slice_rows`, `extraction_ready`), которые заполняются детерминированно в адаптерах и используются extraction planner-ом для ранжирования.

**Tech Stack:** Python 3.11+, Pydantic v2, DuckDB, pyarrow, pytest, python-dotenv

---

## Контекст для разработчика

**Как хранятся данные:**
- FedStat: parquet-файлы в виде wide-format таблиц (`dataset_id.parquet` или запакованы в `data.zip`). Путь берётся из `source_card["local_path"]` или `source_card["parquet_path"]`.
- World Bank: аналогично — `indicator_code.parquet` или в zip-архиве.
- Каталог (`source-catalog.sqlite`) содержит пути вида `/Users/a/Downloads/dumps/...` — эти пути могут не существовать на текущей машине.

**Почему падает:**
`_parquet_path(source_card)` перебирает кандидатов из карточки, не находит ни одного, вызывает `_extract_archived_parquet` (тоже не находит zip), выбрасывает `FileNotFoundError`. Coverage нода перехватывает, возвращает `CoverageReport(status="gated")`. Extraction planner видит только gated-отчёты → extraction skipped → not_found.

**Решение:** Перед `_extract_archived_parquet` пробовать env-переменную как базовую директорию.

**Файлы:**
- `app/data/fedstat_adapter.py` — `_parquet_path` (строка ~222)
- `app/data/world_bank_adapter.py` — `_parquet_path` (строка ~302)
- `app/artifacts/workflow_artifacts.py` — `CoverageReport` (строка 84)
- `app/workflow/nodes/deterministic_tools.py` — обработка нулевых строк (строка ~108)
- `tests/test_parquet_path_resolution.py` — новый тестовый файл
- `tests/test_slice_validation.py` — новый тестовый файл

**Запуск тестов:**
```bash
cd /Users/a/MAI/matmod
python -m pytest tests/test_parquet_path_resolution.py tests/test_slice_validation.py -v --tb=short
```

---

## Task 1: Env-var fallback для путей к parquet в FedStat адаптере

**Files:**
- Modify: `app/data/fedstat_adapter.py` — функция `_parquet_path` (~строка 222)
- Test: `tests/test_parquet_path_resolution.py` (create new)

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_parquet_path_resolution.py`:

```python
"""Tests for parquet path resolution with env var fallback."""
import os
import shutil
import tempfile
from pathlib import Path

import pytest


class TestFedstatParquetPathEnvFallback:
    def test_finds_parquet_via_fedstat_dumps_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_parquet_path must find file using FEDSTAT_DUMPS_DIR when catalog path is wrong."""
        # Create a real parquet file in a temp dumps dir
        dumps_dir = tmp_path / "fedstatru" / "data" / "parquet"
        dumps_dir.mkdir(parents=True)
        parquet_file = dumps_dir / "12345.parquet"
        parquet_file.write_bytes(b"fake parquet content")  # content doesn't matter for path test

        monkeypatch.setenv("FEDSTAT_DUMPS_DIR", str(dumps_dir))

        from app.data import fedstat_adapter
        # Reload to pick up env var (or call directly)
        import importlib
        importlib.reload(fedstat_adapter)

        source_card = {
            "dataset_id": "12345",
            "local_path": "/nonexistent/old/path/12345.parquet",  # wrong catalog path
        }

        from app.data.fedstat_adapter import _parquet_path
        path = _parquet_path(source_card)
        assert path == parquet_file

    def test_finds_parquet_by_dataset_id_in_dumps_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_parquet_path finds file by dataset_id.parquet filename in FEDSTAT_DUMPS_DIR."""
        dumps_dir = tmp_path / "dumps"
        dumps_dir.mkdir()
        parquet_file = dumps_dir / "99999.parquet"
        parquet_file.write_bytes(b"fake")

        monkeypatch.setenv("FEDSTAT_DUMPS_DIR", str(dumps_dir))

        from app.data.fedstat_adapter import _parquet_path
        source_card = {"dataset_id": "99999"}
        path = _parquet_path(source_card)
        assert path == parquet_file

    def test_raises_when_dumps_dir_also_has_no_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_parquet_path raises FileNotFoundError when env dir exists but file not there."""
        dumps_dir = tmp_path / "empty_dumps"
        dumps_dir.mkdir()

        monkeypatch.setenv("FEDSTAT_DUMPS_DIR", str(dumps_dir))

        from app.data.fedstat_adapter import _parquet_path
        source_card = {"dataset_id": "99999", "local_path": "/nonexistent/path.parquet"}

        with pytest.raises(FileNotFoundError):
            _parquet_path(source_card)

    def test_works_without_env_var_set(self, monkeypatch: pytest.MonkeyPatch):
        """_parquet_path does not crash when FEDSTAT_DUMPS_DIR is not set."""
        monkeypatch.delenv("FEDSTAT_DUMPS_DIR", raising=False)

        from app.data.fedstat_adapter import _parquet_path
        source_card = {"dataset_id": "12345", "local_path": "/nonexistent/path.parquet"}

        with pytest.raises(FileNotFoundError):
            _parquet_path(source_card)  # should raise, not crash differently
```

- [ ] **Step 2: Убедиться что первые два теста падают**

```bash
python -m pytest tests/test_parquet_path_resolution.py::TestFedstatParquetPathEnvFallback -v
```

Ожидаемый результат: `test_finds_parquet_via_fedstat_dumps_dir` и `test_finds_parquet_by_dataset_id_in_dumps_dir` — FAIL.

- [ ] **Step 3: Добавить env-var fallback в `_parquet_path` в fedstat_adapter.py**

В `app/data/fedstat_adapter.py`, найти функцию `_parquet_path` (~строка 222). Добавить новый блок перед вызовом `_extract_archived_parquet`:

```python
def _parquet_path(source_card: dict[str, Any]) -> Path:
    candidates = [
        source_card.get("local_path"),
        source_card.get("parquet_path"),
        source_card.get("resource_id"),
    ]
    metadata = source_card.get("metadata")
    if isinstance(metadata, dict):
        candidates.extend([metadata.get("local_path"), metadata.get("parquet_path")])
    for candidate in candidates:
        if candidate:
            path = Path(str(candidate))
            if path.exists():
                return path

    # Env-var fallback: look in FEDSTAT_DUMPS_DIR by dataset_id or resource_id
    import os
    dumps_dir_str = os.environ.get("FEDSTAT_DUMPS_DIR")
    if dumps_dir_str:
        dumps_dir = Path(dumps_dir_str)
        if dumps_dir.is_dir():
            for id_key in ("dataset_id", "resource_id", "card_id"):
                raw_id = source_card.get(id_key)
                if not raw_id:
                    continue
                # Try exact name and name + .parquet
                for name in [str(raw_id), f"{raw_id}.parquet"]:
                    candidate = dumps_dir / name
                    if candidate.exists():
                        return candidate

    archived = _extract_archived_parquet(source_card)
    if archived is not None:
        return archived
    raise FileNotFoundError(f"No readable FedStat parquet path in source card: {source_card!r}")
```

- [ ] **Step 4: Запустить тест — должен пройти**

```bash
python -m pytest tests/test_parquet_path_resolution.py::TestFedstatParquetPathEnvFallback -v
```

Ожидаемый результат: PASS 4/4

- [ ] **Step 5: Commit**

```bash
git add app/data/fedstat_adapter.py tests/test_parquet_path_resolution.py
git commit -m "fix: add FEDSTAT_DUMPS_DIR env-var fallback to fedstat _parquet_path"
```

---

## Task 2: Env-var fallback для путей к parquet в World Bank адаптере

**Files:**
- Modify: `app/data/world_bank_adapter.py` — функция `_parquet_path` (~строка 302)
- Test: `tests/test_parquet_path_resolution.py` (добавить класс)

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_parquet_path_resolution.py`:

```python
class TestWorldBankParquetPathEnvFallback:
    def test_finds_parquet_via_world_bank_dumps_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_parquet_path must find WB file using WORLD_BANK_DUMPS_DIR when catalog path is wrong."""
        dumps_dir = tmp_path / "wb_dumps"
        dumps_dir.mkdir()
        parquet_file = dumps_dir / "NY.GDP.MKTP.CD.parquet"
        parquet_file.write_bytes(b"fake parquet")

        monkeypatch.setenv("WORLD_BANK_DUMPS_DIR", str(dumps_dir))

        from app.data.world_bank_adapter import _parquet_path
        source_card = {
            "dataset_id": "NY.GDP.MKTP.CD",
            "local_path": "/nonexistent/old/path/NY.GDP.MKTP.CD.parquet",
        }
        path = _parquet_path(source_card)
        assert path == parquet_file

    def test_finds_by_card_id_filename(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_parquet_path finds by card_id component ending in .parquet."""
        dumps_dir = tmp_path / "wb"
        dumps_dir.mkdir()
        parquet_file = dumps_dir / "SP.POP.TOTL.parquet"
        parquet_file.write_bytes(b"fake")

        monkeypatch.setenv("WORLD_BANK_DUMPS_DIR", str(dumps_dir))

        from app.data.world_bank_adapter import _parquet_path
        source_card = {
            "dataset_id": "SP.POP.TOTL",
            "card_id": "world_bank:SP.POP.TOTL:wb/parquet/SP.POP.TOTL.parquet",
        }
        path = _parquet_path(source_card)
        assert path == parquet_file

    def test_raises_when_not_found_anywhere(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.setenv("WORLD_BANK_DUMPS_DIR", str(empty_dir))

        from app.data.world_bank_adapter import _parquet_path
        source_card = {"dataset_id": "NY.GDP.MKTP.CD"}

        with pytest.raises(FileNotFoundError):
            _parquet_path(source_card)
```

- [ ] **Step 2: Убедиться что тест падает**

```bash
python -m pytest tests/test_parquet_path_resolution.py::TestWorldBankParquetPathEnvFallback -v
```

- [ ] **Step 3: Добавить env-var fallback в `_parquet_path` в world_bank_adapter.py**

В `app/data/world_bank_adapter.py`, найти `_parquet_path` (~строка 302). Добавить по аналогии с fedstat:

```python
def _parquet_path(source_card: dict[str, Any]) -> Path:
    candidates = [
        source_card.get("local_path"),
        source_card.get("parquet_path"),
        source_card.get("resource_id"),
    ]
    metadata = source_card.get("metadata")
    if isinstance(metadata, dict):
        candidates.extend([metadata.get("local_path"), metadata.get("parquet_path")])
    for candidate in candidates:
        if candidate:
            path = Path(str(candidate))
            if path.exists():
                return path

    # Env-var fallback: look in WORLD_BANK_DUMPS_DIR by dataset_id
    import os
    dumps_dir_str = os.environ.get("WORLD_BANK_DUMPS_DIR")
    if dumps_dir_str:
        dumps_dir = Path(dumps_dir_str)
        if dumps_dir.is_dir():
            for id_key in ("dataset_id", "resource_id"):
                raw_id = source_card.get(id_key)
                if not raw_id:
                    continue
                for name in [str(raw_id), f"{raw_id}.parquet"]:
                    candidate = dumps_dir / name
                    if candidate.exists():
                        return candidate
            # Also try card_id last component (e.g. "wb/parquet/NY.GDP.MKTP.CD.parquet")
            card_id = source_card.get("card_id") or ""
            if card_id:
                last_part = card_id.split("/")[-1]
                if last_part.endswith(".parquet"):
                    candidate = dumps_dir / last_part
                    if candidate.exists():
                        return candidate

    archived = _extract_archived_parquet(source_card)
    if archived is not None:
        return archived
    raise FileNotFoundError(f"No readable World Bank parquet path in source card: {source_card!r}")
```

- [ ] **Step 4: Запустить тест — должен пройти**

```bash
python -m pytest tests/test_parquet_path_resolution.py::TestWorldBankParquetPathEnvFallback -v
```

- [ ] **Step 5: Запустить оба класса тестов**

```bash
python -m pytest tests/test_parquet_path_resolution.py -v
```

Ожидаемый результат: PASS 7/7

- [ ] **Step 6: Commit**

```bash
git add app/data/world_bank_adapter.py tests/test_parquet_path_resolution.py
git commit -m "fix: add WORLD_BANK_DUMPS_DIR env-var fallback to world_bank _parquet_path"
```

---

## Task 3: Добавить поля slice-валидации в `CoverageReport`

**Проблема:** `CoverageReport` не содержит информации о том, сколько строк доступно для запрошенного среза (страна × период × индикатор). `extraction_ready` нет как поля — extraction planner смотрит на `status == "ok"` и считает что данные есть.

**Files:**
- Modify: `app/artifacts/workflow_artifacts.py` — класс `CoverageReport` (строка 84)
- Test: `tests/test_slice_validation.py` (create new)

- [ ] **Step 1: Написать тест на новые поля**

Создать `tests/test_slice_validation.py`:

```python
"""Tests for slice-level coverage validation fields."""
import pytest


class TestCoverageReportSliceFields:
    def test_coverage_report_has_slice_fields_with_defaults(self):
        from app.artifacts.workflow_artifacts import CoverageReport
        report = CoverageReport(
            source_id="test",
            status="ok",
        )
        assert hasattr(report, "matched_geographies")
        assert hasattr(report, "matched_periods")
        assert hasattr(report, "requested_slice_rows")
        assert hasattr(report, "extraction_ready")
        assert report.matched_geographies == []
        assert report.matched_periods == []
        assert report.requested_slice_rows == 0
        assert report.extraction_ready is False

    def test_coverage_report_slice_fields_settable(self):
        from app.artifacts.workflow_artifacts import CoverageReport
        report = CoverageReport(
            source_id="test",
            status="ok",
            matched_geographies=["Россия"],
            matched_periods=["2020", "2021", "2022"],
            requested_slice_rows=150,
            extraction_ready=True,
        )
        assert report.matched_geographies == ["Россия"]
        assert report.requested_slice_rows == 150
        assert report.extraction_ready is True

    def test_coverage_report_extra_fields_still_forbidden(self):
        from app.artifacts.workflow_artifacts import CoverageReport
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CoverageReport(source_id="test", status="ok", unknown_field="value")
```

- [ ] **Step 2: Убедиться что тест на наличие полей падает**

```bash
python -m pytest tests/test_slice_validation.py::TestCoverageReportSliceFields -v
```

Ожидаемый результат: `test_coverage_report_has_slice_fields_with_defaults` — FAIL (поля не существуют).

- [ ] **Step 3: Добавить новые поля в `CoverageReport`**

В `app/artifacts/workflow_artifacts.py`, класс `CoverageReport` (строка 84):

```python
class CoverageReport(BaseModel):
    source_id: str
    status: WorkflowStatus
    checks: list[str] = Field(default_factory=list)
    available_periods: list[str] = Field(default_factory=list)
    available_geographies: list[str] = Field(default_factory=list)
    unit: str | None = None
    frequency: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    gated_reason: str | None = None
    # Slice-level validation fields (Plan B)
    matched_geographies: list[str] = Field(default_factory=list)
    matched_periods: list[str] = Field(default_factory=list)
    requested_slice_rows: int = 0
    extraction_ready: bool = False

    model_config = ConfigDict(extra="forbid")
```

- [ ] **Step 4: Запустить тест — должен пройти**

```bash
python -m pytest tests/test_slice_validation.py::TestCoverageReportSliceFields -v
```

- [ ] **Step 5: Убедиться что существующие тесты не сломались**

```bash
python -m pytest tests/ -v --tb=short -q 2>&1 | tail -20
```

- [ ] **Step 6: Commit**

```bash
git add app/artifacts/workflow_artifacts.py tests/test_slice_validation.py
git commit -m "feat: add slice validation fields to CoverageReport (matched_geographies, matched_periods, requested_slice_rows, extraction_ready)"
```

---

## Task 4: Заполнять slice-поля в FedStat coverage preview

**Проблема:** `preview_fedstat_coverage` в fedstat_adapter.py возвращает `CoverageReport(status="ok")` не проверяя пересекается ли запрошенная страна/период с реальными данными. Extraction planner видит `ok` и пробует извлечение, получает нулевые строки.

**Files:**
- Modify: `app/data/fedstat_adapter.py` — функция `preview_fedstat_coverage` (строка 33)
- Test: `tests/test_slice_validation.py` (добавить класс)

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_slice_validation.py`:

```python
class TestFedstatSliceCoverage:
    """preview_fedstat_coverage must populate slice fields."""

    def _make_source_card(self, tmp_path) -> dict:
        """Create a minimal FedStat source card with a real parquet file."""
        import pyarrow as pa
        import pyarrow.parquet as pq

        # Create a FedStat-style wide parquet file
        # First row = indicator names, subsequent rows = data with geo/unit columns
        table = pa.table({
            "Территория": ["Наименование показателя", "Россия", "Казахстан"],
            "Единица измерения": ["", "руб.", "руб."],
            "2020": ["ВВП", "100000.0", "50000.0"],
            "2021": ["ВВП", "110000.0", "55000.0"],
            "2022": ["ВВП", "120000.0", ""],  # Kazakhstan has missing 2022
        })
        parquet_path = tmp_path / "12345.parquet"
        pq.write_table(table, parquet_path)

        return {
            "dataset_id": "12345",
            "local_path": str(parquet_path),
            "title": "ВВП по регионам",
        }

    def test_matched_geographies_populated_when_filter_matches(self, tmp_path):
        from app.data.fedstat_adapter import preview_fedstat_coverage

        card = self._make_source_card(tmp_path)
        filters = {"geography": "Россия"}
        report = preview_fedstat_coverage(card, filters=filters)

        assert "Россия" in report.matched_geographies, (
            f"Expected 'Россия' in matched_geographies, got {report.matched_geographies}"
        )
        assert report.requested_slice_rows > 0
        assert report.extraction_ready is True

    def test_matched_geographies_empty_when_filter_not_found(self, tmp_path):
        from app.data.fedstat_adapter import preview_fedstat_coverage

        card = self._make_source_card(tmp_path)
        filters = {"geography": "Германия"}  # not in the data
        report = preview_fedstat_coverage(card, filters=filters)

        assert report.matched_geographies == []
        assert report.requested_slice_rows == 0
        assert report.extraction_ready is False

    def test_extraction_ready_true_when_no_filter_specified(self, tmp_path):
        """Without geography filter, any data means extraction_ready=True."""
        from app.data.fedstat_adapter import preview_fedstat_coverage

        card = self._make_source_card(tmp_path)
        filters = {}  # no filter
        report = preview_fedstat_coverage(card, filters=filters)

        assert report.extraction_ready is True
        assert report.requested_slice_rows > 0
```

- [ ] **Step 2: Убедиться что тест на `matched_geographies` падает**

```bash
python -m pytest tests/test_slice_validation.py::TestFedstatSliceCoverage -v
```

- [ ] **Step 3: Обновить `preview_fedstat_coverage` для заполнения slice полей**

В `app/data/fedstat_adapter.py`, функция `preview_fedstat_coverage` (строка 33). Добавить после вычисления `geographies` и `units`:

```python
    # Compute slice-level coverage
    requested_geo = _optional_text(filters.get("geography") or filters.get("geo_name")) or ""
    if requested_geo:
        matched_geos = [g for g in geographies if requested_geo.lower() in g.lower()]
    else:
        matched_geos = list(geographies)

    requested_periods_filter = {
        str(p) for p in (filters.get("periods") or [])
    }
    if requested_periods_filter:
        matched_periods = [p for p in period_columns if p in requested_periods_filter]
    else:
        matched_periods = list(period_columns)

    # Count rows for the requested slice
    if requested_geo:
        slice_rows = sum(
            1 for row in filtered
            if requested_geo.lower() in (_geo_name(row, metadata) or "").lower()
        )
    else:
        slice_rows = len(filtered)

    extraction_ready = slice_rows > 0
```

Добавить в возвращаемый `CoverageReport` новые поля:

```python
    return CoverageReport(
        source_id=str(source_card.get("dataset_id") or source_card.get("resource_id") or "fedstat"),
        status="ok",
        checks=[...],  # без изменений
        available_periods=period_columns,
        available_geographies=geographies,
        unit=...,  # без изменений
        frequency=...,  # без изменений
        evidence={
            "missing_values": missing_values,
            "row_count": len(filtered),
            "source_path": str(_parquet_path(source_card)),
            "physical_columns": metadata["physical_columns"],
            "logical_columns": metadata["logical_columns"],
        },
        matched_geographies=matched_geos,
        matched_periods=matched_periods,
        requested_slice_rows=slice_rows,
        extraction_ready=extraction_ready,
    )
```

- [ ] **Step 4: Запустить тест — должен пройти**

```bash
python -m pytest tests/test_slice_validation.py::TestFedstatSliceCoverage -v
```

- [ ] **Step 5: Commit**

```bash
git add app/data/fedstat_adapter.py tests/test_slice_validation.py
git commit -m "feat: populate slice fields (matched_geographies, requested_slice_rows, extraction_ready) in FedStat coverage preview"
```

---

## Task 5: Заполнять slice-поля в World Bank coverage preview

**Files:**
- Modify: `app/data/world_bank_adapter.py` — функция `preview_world_bank_coverage`
- Test: `tests/test_slice_validation.py` (добавить класс)

- [ ] **Step 1: Найти функцию в адаптере**

```bash
grep -n "def preview_world_bank_coverage" /Users/a/MAI/matmod/app/data/world_bank_adapter.py
```

- [ ] **Step 2: Написать падающий тест**

Добавить в `tests/test_slice_validation.py`:

```python
class TestWorldBankSliceCoverage:
    """preview_world_bank_coverage must populate slice fields."""

    def _make_wb_source_card(self, tmp_path) -> dict:
        import pyarrow as pa
        import pyarrow.parquet as pq

        # World Bank parquet: long format with countryiso3code, date, value
        table = pa.table({
            "countryiso3code": ["RUS", "RUS", "KAZ", "KAZ"],
            "date": ["2020", "2021", "2020", "2021"],
            "value": [1.5, 2.3, 1.1, 1.8],
            "indicator": ["NY.GDP.MKTP.CD"] * 4,
        })
        parquet_path = tmp_path / "NY.GDP.MKTP.CD.parquet"
        pq.write_table(table, parquet_path)

        return {
            "dataset_id": "NY.GDP.MKTP.CD",
            "local_path": str(parquet_path),
            "title": "GDP (current US$)",
        }

    def test_matched_geographies_populated_for_russia(self, tmp_path):
        from app.data.world_bank_adapter import preview_world_bank_coverage

        card = self._make_wb_source_card(tmp_path)
        report = preview_world_bank_coverage(
            card, countries=["RUS"], periods=[], indicator_id="NY.GDP.MKTP.CD"
        )

        assert "RUS" in report.matched_geographies or any("RUS" in g for g in report.matched_geographies)
        assert report.requested_slice_rows > 0
        assert report.extraction_ready is True

    def test_matched_geographies_empty_for_unknown_country(self, tmp_path):
        from app.data.world_bank_adapter import preview_world_bank_coverage

        card = self._make_wb_source_card(tmp_path)
        report = preview_world_bank_coverage(
            card, countries=["DEU"], periods=[], indicator_id="NY.GDP.MKTP.CD"
        )

        assert report.matched_geographies == []
        assert report.requested_slice_rows == 0
        assert report.extraction_ready is False

    def test_extraction_ready_true_without_country_filter(self, tmp_path):
        from app.data.world_bank_adapter import preview_world_bank_coverage

        card = self._make_wb_source_card(tmp_path)
        report = preview_world_bank_coverage(
            card, countries=[], periods=[], indicator_id="NY.GDP.MKTP.CD"
        )

        assert report.extraction_ready is True
```

- [ ] **Step 3: Убедиться что тест падает**

```bash
python -m pytest tests/test_slice_validation.py::TestWorldBankSliceCoverage -v
```

- [ ] **Step 4: Обновить `preview_world_bank_coverage` для заполнения slice полей**

Прочитать функцию `preview_world_bank_coverage` в `app/data/world_bank_adapter.py`. Найти где она возвращает `CoverageReport`. После вычисления `available_geographies` добавить:

```python
    # Compute slice-level coverage
    if countries:
        # Match requested countries against available (case-insensitive, iso3 or name)
        countries_upper = {c.upper() for c in countries}
        matched_geos = [
            g for g in available_geographies
            if g.upper() in countries_upper
        ]
        # Count rows matching requested countries
        slice_rows = sum(
            1 for g in available_geographies
            if g.upper() in countries_upper
        ) * (len(matched_periods) if matched_periods else 1)
        # More accurate: use actual filtered row count if accessible
    else:
        matched_geos = list(available_geographies)
        slice_rows = total_row_count  # all rows

    extraction_ready = slice_rows > 0 if countries else total_row_count > 0
```

Добавить в `return CoverageReport(...)`:
```python
        matched_geographies=matched_geos,
        matched_periods=matched_periods,
        requested_slice_rows=slice_rows,
        extraction_ready=extraction_ready,
```

**Важно:** Переменные `available_geographies`, `total_row_count`, `matched_periods` должны быть уже вычислены в функции. Если их нет — добавить соответствующий DuckDB-запрос. Читать функцию внимательно перед редактированием.

- [ ] **Step 5: Запустить тест — должен пройти**

```bash
python -m pytest tests/test_slice_validation.py::TestWorldBankSliceCoverage -v
```

- [ ] **Step 6: Commit**

```bash
git add app/data/world_bank_adapter.py tests/test_slice_validation.py
git commit -m "feat: populate slice fields in World Bank coverage preview"
```

---

## Task 6: Маркировать нулевые датасеты явно в deterministic_tools

**Проблема:** `run_deterministic_tools` создаёт `DatasetArtifact(status="ok", rows=0)` — critic проверяет `rows > 0` и отказывает, но `component_statuses["deterministic_tools"] = "ok"` остаётся. Trace выглядит успешным, хотя данных нет. Это мешает диагностике.

**Files:**
- Modify: `app/workflow/nodes/deterministic_tools.py` (~строка 108)
- Test: `tests/test_slice_validation.py` (добавить класс)

- [ ] **Step 1: Написать тест**

Добавить в `tests/test_slice_validation.py`:

```python
class TestZeroRowDatasetHandling:
    """run_deterministic_tools must mark zero-row datasets with quality_flag and gated status."""

    def test_zero_row_dataset_gets_empty_slice_flag(self):
        """When extraction returns 0 rows, DatasetArtifact must have quality_flags=['empty_slice'] and status='gated'."""
        from unittest.mock import patch, MagicMock
        from pathlib import Path
        from app.artifacts.workflow_artifacts import (
            DatasetArtifact, ExtractionPlan, IntentFrame
        )
        from app.workflow.nodes.deterministic_tools import run_deterministic_tools
        from uuid import uuid4

        zero_row_dataset = DatasetArtifact(
            artifact_id=f"ds-{uuid4().hex[:8]}",
            status="ok",
            source_id="fedstat:12345",
            rows=0,
            records=[],
            provenance=[{"source": "fedstat", "dataset_id": "12345"}],
        )

        plan = ExtractionPlan(
            artifact_id="plan-001",
            source_id="fedstat:12345",
            status="ok",
            operations=["filter_rows", "export_dataset"],
            filters={"geography": "Казахстан"},
        )

        intent = IntentFrame(
            query="ВВП Казахстана",
            category="simple",
            known_fields={"geography": "Казахстан"},
        )

        state = {
            "run_id": "test-run",
            "extraction_plan": plan,
            "intent": intent,
            "dataset_artifacts": [],
            "script_artifacts": [],
            "trace_events": [],
            "component_statuses": {},
        }

        with patch("app.workflow.nodes.deterministic_tools._dispatch_extraction") as mock_dispatch:
            mock_dispatch.return_value = zero_row_dataset
            with patch("app.workflow.nodes.deterministic_tools.export_dataset_with_script") as mock_export:
                mock_export.return_value = None
                result = run_deterministic_tools(state, output_dir=Path("/tmp/test-artifacts"))

        datasets = result["dataset_artifacts"]
        assert len(datasets) == 1
        dataset = datasets[0]
        assert "empty_slice" in dataset.quality_flags, (
            f"Expected 'empty_slice' in quality_flags, got {dataset.quality_flags}"
        )
        assert dataset.status == "gated", (
            f"Expected status='gated' for zero-row dataset, got '{dataset.status}'"
        )
        assert result["component_statuses"]["deterministic_tools"] == "empty_slice"

    def test_nonzero_row_dataset_stays_ok(self):
        """When extraction returns rows > 0, DatasetArtifact keeps status='ok'."""
        from unittest.mock import patch
        from pathlib import Path
        from app.artifacts.workflow_artifacts import (
            DatasetArtifact, ExtractionPlan, IntentFrame
        )
        from app.workflow.nodes.deterministic_tools import run_deterministic_tools
        from uuid import uuid4

        ok_dataset = DatasetArtifact(
            artifact_id=f"ds-{uuid4().hex[:8]}",
            status="ok",
            source_id="fedstat:12345",
            rows=150,
            records=[{"value": 1.0}],
            provenance=[{"source": "fedstat"}],
        )

        plan = ExtractionPlan(
            artifact_id="plan-001",
            source_id="fedstat:12345",
            status="ok",
            operations=["filter_rows", "export_dataset"],
        )

        state = {
            "run_id": "test-run",
            "extraction_plan": plan,
            "intent": None,
            "dataset_artifacts": [],
            "script_artifacts": [],
            "trace_events": [],
            "component_statuses": {},
        }

        with patch("app.workflow.nodes.deterministic_tools._dispatch_extraction") as mock_dispatch, \
             patch("app.workflow.nodes.deterministic_tools.export_dataset_with_script") as mock_export:
            mock_dispatch.return_value = ok_dataset
            mock_export.return_value = None
            result = run_deterministic_tools(state, output_dir=Path("/tmp/test-artifacts"))

        dataset = result["dataset_artifacts"][0]
        assert dataset.status == "ok"
        assert "empty_slice" not in dataset.quality_flags
```

- [ ] **Step 2: Убедиться что `test_zero_row_dataset_gets_empty_slice_flag` падает**

```bash
python -m pytest "tests/test_slice_validation.py::TestZeroRowDatasetHandling::test_zero_row_dataset_gets_empty_slice_flag" -v
```

- [ ] **Step 3: Добавить проверку нулевых строк в `run_deterministic_tools`**

В `app/workflow/nodes/deterministic_tools.py`, найти блок `if isinstance(result, DatasetArtifact):` (~строка 108). Добавить после `row_count = result.rows`:

```python
    if isinstance(result, DatasetArtifact):
        row_count = result.rows

        # Mark zero-row datasets explicitly — they look successful but contain no data
        if (row_count or 0) == 0:
            result = result.model_copy(update={
                "status": "gated",
                "quality_flags": list(result.quality_flags) + ["empty_slice"],
            })
            status = "empty_slice"

        dataset_artifacts.append(result)
```

Также обновить `component_statuses["deterministic_tools"] = status` — убедиться что переменная `status` передаётся правильно. Это уже происходит на строке ~170.

- [ ] **Step 4: Запустить тест — должен пройти**

```bash
python -m pytest tests/test_slice_validation.py::TestZeroRowDatasetHandling -v
```

- [ ] **Step 5: Commit**

```bash
git add app/workflow/nodes/deterministic_tools.py tests/test_slice_validation.py
git commit -m "fix: mark zero-row DatasetArtifact as gated with empty_slice quality flag"
```

---

## Task 7: Финальная проверка — все тесты, нет регрессий

- [ ] **Step 1: Все новые тесты**

```bash
python -m pytest tests/test_parquet_path_resolution.py tests/test_slice_validation.py -v
```

Ожидаемый результат: PASS все тесты.

- [ ] **Step 2: Существующие suite**

```bash
python -m pytest tests/test_phase2_extraction_adapters.py tests/test_deterministic_tools_and_trace.py tests/test_phase2_finalization.py -v --tb=short
```

- [ ] **Step 3: Проверить что FEDSTAT_DUMPS_DIR используется при preview**

```bash
python -c "
import os, tempfile
from pathlib import Path
import pyarrow as pa, pyarrow.parquet as pq

# Setup: fake dump dir with a parquet file
with tempfile.TemporaryDirectory() as tmp:
    dumps_dir = Path(tmp)
    fake_parquet = dumps_dir / '12345.parquet'
    table = pa.table({'Территория': ['Наим.', 'Россия'], 'ед.': ['', 'руб.'], '2020': ['ВВП', '100.0']})
    pq.write_table(table, fake_parquet)
    
    os.environ['FEDSTAT_DUMPS_DIR'] = str(dumps_dir)
    
    from app.data.fedstat_adapter import _parquet_path
    path = _parquet_path({'dataset_id': '12345', 'local_path': '/nonexistent/path'})
    print(f'Found: {path}')
    assert path == fake_parquet
    print('PASS: FEDSTAT_DUMPS_DIR fallback works')
"
```

- [ ] **Step 4: Финальный commit если что-то осталось незакомиченным**

```bash
git status
git add -p  # добавить только изменённые файлы
git commit -m "fix: plan B complete — parquet env-var fallback + slice coverage validation + empty_slice marking"
```

---

## Acceptance Criteria

- [ ] `FEDSTAT_DUMPS_DIR` env var используется как fallback в `_parquet_path` fedstat_adapter
- [ ] `WORLD_BANK_DUMPS_DIR` env var используется как fallback в `_parquet_path` world_bank_adapter
- [ ] `CoverageReport` содержит `matched_geographies`, `matched_periods`, `requested_slice_rows`, `extraction_ready`
- [ ] `preview_fedstat_coverage` заполняет slice-поля и ставит `extraction_ready=False` если запрошенная страна не найдена
- [ ] `preview_world_bank_coverage` заполняет slice-поля аналогично
- [ ] Нулевые строки в `DatasetArtifact` → `status="gated"`, `quality_flags=["empty_slice"]`
- [ ] `component_statuses["deterministic_tools"] == "empty_slice"` для нулевых датасетов
- [ ] Все новые тесты PASS
- [ ] Нет регрессий в существующих тестах
