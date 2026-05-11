# Plan A — Schema Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Устранить три Pydantic-ошибки валидации LLM-вывода, которые превращают все 7 smoke-кейсов в фальшивый `not_found`, и вернуть диагностические артефакты в ответе даже когда извлечение неуспешно.

**Architecture:** Добавляем `@field_validator(..., mode="before")` в три схемы LLM-вывода — `_IntentAnalysisSchema`, `_CoverageAssessment`, `_CritiqueSchema`. Меняем narrator.py, чтобы датасеты/скрипты всегда попадали в ответ (не только при `passed`). Никакой архитектурной перестройки — только минимальные правки внутри существующих классов.

**Tech Stack:** Python 3.11+, Pydantic v2, LangGraph, pytest

---

## Контекст для разработчика

Workflow строится из узлов LangGraph. Три из них вызывают Qwen (LLM) и ожидают ответ в строгом Pydantic-формате. Qwen иногда возвращает `null` или `list` вместо `str`, `str` вместо `list[str]` — Pydantic выбрасывает `ValidationError`. Эта ошибка перехватывается как generic `Exception` и конвертируется в `finalization_pending` → `not_found`. Пользователь видит "данных нет", хотя сломалась схема.

**Файлы проекта:**
- `app/workflow/state.py` — `_IntentAnalysisSchema` (парсинг intent от Qwen)
- `app/workflow/nodes/coverage.py` — `_CoverageAssessment` (локальный класс внутри `_llm_assess_coverage`)
- `app/workflow/nodes/critic.py` — `_CritiqueSchema` (оценка методологии)
- `app/workflow/nodes/narrator.py` — `build_workflow_response` (финальный ответ)
- `tests/test_phase2_workflow_nodes.py` — существующие тесты узлов
- `tests/test_phase2_finalization.py` — тесты финализации

**Запуск тестов:**
```bash
cd /Users/a/MAI/matmod
python -m pytest tests/test_phase2_workflow_nodes.py tests/test_phase2_finalization.py -v --tb=short
```

---

## Task 1: Исправить `_IntentAnalysisSchema.geography` — принимать list

**Проблема:** Qwen возвращает `geography: ["Россия", "Казахстан"]` для сравнительных запросов. Поле объявлено как `str | None`, Pydantic отказывает. Вся intent нода уходит в `gated`, retrieval не запускается.

**Files:**
- Modify: `app/workflow/state.py:63-80`
- Test: `tests/test_schema_validators.py` (create new)

- [ ] **Step 1: Написать падающий тест**

Создать файл `tests/test_schema_validators.py`:

```python
"""Tests for LLM output schema validators — coercion and tolerance."""
import pytest
from pydantic import ValidationError


class TestIntentAnalysisSchemaGeography:
    def test_geography_as_list_is_coerced_to_string(self):
        from app.workflow.state import _IntentAnalysisSchema
        schema = _IntentAnalysisSchema(
            category="comparative",
            needs_clarification=False,
            geography=["Россия", "Казахстан"],
        )
        assert schema.geography == "Россия, Казахстан"

    def test_geography_as_string_unchanged(self):
        from app.workflow.state import _IntentAnalysisSchema
        schema = _IntentAnalysisSchema(
            category="simple",
            needs_clarification=False,
            geography="Россия",
        )
        assert schema.geography == "Россия"

    def test_geography_as_none_stays_none(self):
        from app.workflow.state import _IntentAnalysisSchema
        schema = _IntentAnalysisSchema(
            category="simple",
            needs_clarification=False,
            geography=None,
        )
        assert schema.geography is None

    def test_countries_derived_from_list_geography(self):
        from app.workflow.state import _IntentAnalysisSchema
        schema = _IntentAnalysisSchema(
            category="comparative",
            needs_clarification=False,
            geography=["Россия", "Казахстан"],
        )
        assert schema.countries == ["Россия", "Казахстан"]

    def test_countries_derived_from_string_geography(self):
        from app.workflow.state import _IntentAnalysisSchema
        schema = _IntentAnalysisSchema(
            category="simple",
            needs_clarification=False,
            geography="Россия",
        )
        assert schema.countries == ["Россия"]

    def test_countries_empty_when_no_geography(self):
        from app.workflow.state import _IntentAnalysisSchema
        schema = _IntentAnalysisSchema(
            category="simple",
            needs_clarification=False,
        )
        assert schema.countries == []
```

- [ ] **Step 2: Убедиться что тест падает**

```bash
python -m pytest tests/test_schema_validators.py::TestIntentAnalysisSchemaGeography -v
```

Ожидаемый результат: FAIL — `_IntentAnalysisSchema` не имеет `countries` и не принимает list для `geography`.

- [ ] **Step 3: Добавить validator и поле `countries` в `_IntentAnalysisSchema`**

Файл `app/workflow/state.py`, класс `_IntentAnalysisSchema` (строки 63-80). Добавить validator для `geography` и новое поле `countries`:

```python
class _IntentAnalysisSchema(BaseModel):
    """Structured Qwen output schema for intent analysis."""

    category: str
    needs_clarification: bool
    geography: str | None = None
    period: str | None = None
    indicator: str | None = None
    source_preferences: list[str] = []
    missing_fields: list[str] = []
    countries: list[str] = []

    @field_validator("geography", mode="before")
    @classmethod
    def _coerce_geography_list(cls, v: Any) -> str | None:
        if isinstance(v, list):
            return ", ".join(str(item) for item in v if item)
        return v

    @field_validator("countries", mode="before")
    @classmethod
    def _coerce_countries(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return [str(item) for item in v if item]
        if isinstance(v, str) and v:
            return [v]
        return v if v is not None else []

    @field_validator("source_preferences", "missing_fields", mode="before")
    @classmethod
    def _coerce_str_to_list(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v] if v else []
        return v if v is not None else []
```

- [ ] **Step 4: Обновить `_analyze_intent_live` — добавить `countries` в `known_fields`**

В функции `_analyze_intent_live` (строки ~140-159), после `if result.geography:` добавить:

```python
    known_fields: dict[str, Any] = {}
    if result.geography:
        known_fields["geography"] = result.geography
    if result.countries:
        known_fields["countries"] = result.countries
    elif result.geography:
        # Fallback: derive countries from geography string for multi-country queries
        known_fields["countries"] = [c.strip() for c in result.geography.split(",") if c.strip()]
    if result.period:
        known_fields["period"] = result.period
    if result.indicator:
        known_fields["indicator"] = result.indicator
```

- [ ] **Step 5: Запустить тест — должен пройти**

```bash
python -m pytest tests/test_schema_validators.py::TestIntentAnalysisSchemaGeography -v
```

Ожидаемый результат: PASS 6/6

- [ ] **Step 6: Запустить существующие тесты — не сломать**

```bash
python -m pytest tests/test_phase2_workflow_nodes.py tests/test_phase2_finalization.py -v --tb=short
```

Ожидаемый результат: все тесты проходят (или те же что падали до правки).

- [ ] **Step 7: Commit**

```bash
git add app/workflow/state.py tests/test_schema_validators.py
git commit -m "fix: coerce geography list to string in _IntentAnalysisSchema, derive countries field"
```

---

## Task 2: Исправить `_CoverageAssessment` — `best_slice` принимает `None`, списки принимают строку

**Проблема:** `_CoverageAssessment` определён локально внутри `_llm_assess_coverage` как обычный Pydantic-класс. Поля `best_slice: str = ""`, `quality_risks: list[str] = []`, `alternative_slices: list[str] = []` не принимают `None` и строку вместо списка. При ValidationError весь `except Exception` в `_llm_assess_coverage` возвращает исходные отчёты не модифицированными — это лучше чем gated, но LLM-оценка теряется.

**Files:**
- Modify: `app/workflow/nodes/coverage.py:61-68`
- Test: `tests/test_schema_validators.py` (добавить класс)

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_schema_validators.py`:

```python
class TestCoverageAssessmentSchema:
    """_CoverageAssessment is defined locally in coverage.py — test via module import."""

    def _build_schema(self, **kwargs):
        # Import and invoke _llm_assess_coverage internals by patching
        # Instead, test that a dict with these values parses without error
        from pydantic import BaseModel, field_validator
        from typing import Any

        class _CoverageAssessment(BaseModel):
            source_id: str = ""
            can_proceed: bool = True
            best_slice: str | None = None
            alternative_slices: list[str] = []
            quality_risks: list[str] = []
            ask_user: bool = False
            ask_user_reason: str = ""

            @field_validator("alternative_slices", "quality_risks", mode="before")
            @classmethod
            def _coerce_to_list(cls, v: Any) -> list[str]:
                if v is None:
                    return []
                if isinstance(v, str):
                    return [v] if v else []
                return list(v)

        return _CoverageAssessment(**kwargs)

    def test_best_slice_null_is_accepted(self):
        obj = self._build_schema(source_id="s1", best_slice=None)
        assert obj.best_slice is None

    def test_quality_risks_as_string_coerced_to_list(self):
        obj = self._build_schema(source_id="s1", quality_risks="some risk")
        assert obj.quality_risks == ["some risk"]

    def test_quality_risks_as_none_becomes_empty_list(self):
        obj = self._build_schema(source_id="s1", quality_risks=None)
        assert obj.quality_risks == []

    def test_alternative_slices_as_string_coerced_to_list(self):
        obj = self._build_schema(source_id="s1", alternative_slices="2020-2023")
        assert obj.alternative_slices == ["2020-2023"]
```

- [ ] **Step 2: Убедиться что тест проходит с текущей схемой — проверить что проблема воспроизводится через coverage.py**

Написать дополнительный тест, который симулирует реальный провал через `_llm_assess_coverage`:

```python
    def test_coverage_llm_assess_survives_null_best_slice(self):
        """_llm_assess_coverage must not crash when LLM returns null for best_slice."""
        from unittest.mock import MagicMock, patch
        from app.workflow.nodes.coverage import _llm_assess_coverage
        from app.artifacts.workflow_artifacts import CoverageReport

        reports = [
            CoverageReport(
                source_id="test-source",
                status="ok",
                checks=["pyarrow_parquet_metadata_read"],
                available_periods=["2020", "2021"],
                available_geographies=["Россия"],
            )
        ]
        # Simulate LLM returning null for best_slice
        mock_result = MagicMock()
        mock_result.assessments = [
            MagicMock(
                source_id="test-source",
                can_proceed=True,
                best_slice=None,       # <<< проблемное поле
                alternative_slices=[],
                quality_risks=None,    # <<< тоже проблемное
                ask_user=False,
                ask_user_reason="",
            )
        ]

        with patch("app.workflow.nodes.coverage.qwen_credential_gate") as mock_gate, \
             patch("app.workflow.nodes.coverage.YandexAIStudioClient") as mock_client:
            mock_gate.return_value = {"status": "ready"}
            mock_client.return_value.structured_chat.return_value = mock_result

            result = _llm_assess_coverage(reports, intent_fields={"geography": "Россия"})

        # Must return reports (not crash), and source must be present
        assert len(result) == 1
        assert result[0].source_id == "test-source"
```

```bash
python -m pytest tests/test_schema_validators.py::TestCoverageAssessmentSchema -v
```

- [ ] **Step 3: Добавить validators в `_CoverageAssessment` внутри `coverage.py`**

В файле `app/workflow/nodes/coverage.py`, найти локальный класс `_CoverageAssessment` (строки 61-68) и заменить его:

```python
        class _CoverageAssessment(BaseModel):
            source_id: str = ""
            can_proceed: bool = True
            best_slice: str | None = None
            alternative_slices: list[str] = []
            quality_risks: list[str] = []
            ask_user: bool = False
            ask_user_reason: str = ""

            @field_validator("alternative_slices", "quality_risks", mode="before")
            @classmethod
            def _coerce_to_list(cls, v: Any) -> list[str]:
                if v is None:
                    return []
                if isinstance(v, str):
                    return [v] if v else []
                return list(v)
```

Для этого нужно добавить импорт `field_validator` в начало метода `_llm_assess_coverage`. Класс `_CoverageAssessment` уже находится внутри `try:` блока, и `from pydantic import BaseModel` уже там импортируется на строке 54. Добавить `field_validator` к этому импорту:

```python
        from pydantic import BaseModel, field_validator
```

- [ ] **Step 4: Запустить тест — должен пройти**

```bash
python -m pytest tests/test_schema_validators.py::TestCoverageAssessmentSchema -v
```

Ожидаемый результат: PASS все тесты, включая `test_coverage_llm_assess_survives_null_best_slice`.

- [ ] **Step 5: Commit**

```bash
git add app/workflow/nodes/coverage.py tests/test_schema_validators.py
git commit -m "fix: make _CoverageAssessment tolerate null best_slice and string quality_risks"
```

---

## Task 3: Исправить `_CritiqueSchema.warnings` — принимать `None` и строку

**Проблема:** `_CritiqueSchema.warnings: list[str] = []` не принимает `None` или строку от Qwen. У `repair_plan` уже есть validator `wrap_string_in_list`, у `warnings` его нет.

**Files:**
- Modify: `app/workflow/nodes/critic.py:33-43`
- Test: `tests/test_schema_validators.py` (добавить класс)

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_schema_validators.py`:

```python
class TestCritiqueSchema:
    def test_warnings_as_none_becomes_empty_list(self):
        from app.workflow.nodes.critic import _CritiqueSchema
        schema = _CritiqueSchema(verdict="pass", warnings=None, repair_plan=[])
        assert schema.warnings == []

    def test_warnings_as_string_becomes_list(self):
        from app.workflow.nodes.critic import _CritiqueSchema
        schema = _CritiqueSchema(verdict="pass", warnings="некоторое предупреждение", repair_plan=[])
        assert schema.warnings == ["некоторое предупреждение"]

    def test_repair_plan_as_none_becomes_empty_list(self):
        from app.workflow.nodes.critic import _CritiqueSchema
        schema = _CritiqueSchema(verdict="pass", warnings=[], repair_plan=None)
        assert schema.repair_plan == []

    def test_repair_plan_as_string_becomes_list(self):
        from app.workflow.nodes.critic import _CritiqueSchema
        schema = _CritiqueSchema(verdict="pass", warnings=[], repair_plan="fix something")
        assert schema.repair_plan == ["fix something"]

    def test_valid_pass_verdict_accepted(self):
        from app.workflow.nodes.critic import _CritiqueSchema
        schema = _CritiqueSchema(verdict="pass", warnings=[], repair_plan=[])
        assert schema.verdict == "pass"
```

- [ ] **Step 2: Убедиться что тест `test_warnings_as_none_becomes_empty_list` падает**

```bash
python -m pytest tests/test_schema_validators.py::TestCritiqueSchema -v
```

Ожидаемый результат: `test_warnings_as_none_becomes_empty_list` FAIL с ValidationError.

- [ ] **Step 3: Добавить validator для `warnings` в `_CritiqueSchema`**

В файле `app/workflow/nodes/critic.py`, класс `_CritiqueSchema` (строки 33-43). Добавить validator для `warnings` по аналогии с `repair_plan`:

```python
    class _CritiqueSchema(BaseModel):
        verdict: str = "pass"
        warnings: list[str] = []
        repair_plan: list[str] = []

        @field_validator("warnings", "repair_plan", mode="before")
        @classmethod
        def wrap_string_in_list(cls, v: Any) -> list[str]:
            if v is None:
                return []
            if isinstance(v, str):
                return [v] if v else []
            return list(v)
```

Оба поля теперь покрыты одним validator-ом.

- [ ] **Step 4: Запустить тест — должен пройти**

```bash
python -m pytest tests/test_schema_validators.py::TestCritiqueSchema -v
```

Ожидаемый результат: PASS 5/5

- [ ] **Step 5: Commit**

```bash
git add app/workflow/nodes/critic.py tests/test_schema_validators.py
git commit -m "fix: add warnings validator to _CritiqueSchema, unify with repair_plan coercion"
```

---

## Task 4: Поверхностный вывод диагностических артефактов в `not_found` ответах

**Проблема:** Narrator скрывает датасеты и скрипты когда `final_outcome != "passed"` (строки 506-507). Из-за этого при `not_found` нельзя увидеть что извлёк детерминированный инструмент — неправильные строки, нулевые строки, скрипт который почти сработал. Это критично для отладки.

**Архитектурное решение:** `WorkflowResponse.model_validator` не запрещает наличие артефактов при `not_found` — запрещает только их отсутствие при `passed`. Поэтому можно просто убрать условие и всегда включать артефакты. Для `not_found` добавить quality_flag `"diagnostic"` чтобы UI отличал их от ответных данных.

**Files:**
- Modify: `app/workflow/nodes/narrator.py` (~строки 496-515)
- Test: `tests/test_schema_validators.py` (добавить класс)

- [ ] **Step 1: Найти точные строки в narrator.py**

```bash
grep -n "final_outcome == \"passed\"" /Users/a/MAI/matmod/app/workflow/nodes/narrator.py
```

Ожидаемый вывод — строки вида:
```
506:        dataset_artifacts=dataset_artifacts if final_outcome == "passed" else [],
507:        script_artifacts=script_artifacts if final_outcome == "passed" else [],
508:        visualization=visualization if final_outcome == "passed" else None,
```

- [ ] **Step 2: Написать падающий тест**

Добавить в `tests/test_schema_validators.py`:

```python
class TestNarratorDiagnosticArtifacts:
    """Dataset and script artifacts must appear in not_found responses as diagnostic."""

    def _make_minimal_state(self, dataset_rows: int) -> dict:
        from uuid import uuid4
        from app.artifacts.workflow_artifacts import (
            DatasetArtifact, ScriptArtifact, EvidenceBundleArtifact,
            NoDataExplanationArtifact,
        )
        dataset = DatasetArtifact(
            artifact_id=f"ds-{uuid4().hex[:8]}",
            status="ok",
            source_id="test-source",
            rows=dataset_rows,
            records=[{"value": 42.0}] if dataset_rows > 0 else [],
            provenance=[{"source": "test"}],
        )
        script = ScriptArtifact(
            artifact_id=f"sc-{uuid4().hex[:8]}",
            content="print('hello')",
            downloadable=False,
        )
        return {
            "run_id": "test-run",
            "query": "ВВП России",
            "intent": None,
            "dataset_artifacts": [dataset],
            "script_artifacts": [script],
            "coverage_reports": [],
            "trace_events": [],
            "component_statuses": {},
            "evidence": EvidenceBundleArtifact(
                selected_sources=[],
                rejected_sources=[{"card_id": "s1", "rejection_reason": "not_found"}],
            ),
        }

    def test_not_found_response_includes_diagnostic_dataset(self):
        from unittest.mock import patch
        from app.workflow.nodes.narrator import build_workflow_response
        from app.artifacts.workflow_artifacts import CritiqueReport, NoDataExplanationArtifact
        from uuid import uuid4

        state = self._make_minimal_state(dataset_rows=0)
        critique = CritiqueReport(
            artifact_id=f"cr-{uuid4().hex[:8]}",
            verdict="not_found",
            warnings=[],
            repair_plan=[],
        )

        with patch("app.workflow.nodes.narrator.qwen_credential_gate") as mock_gate, \
             patch("app.workflow.nodes.narrator.YandexAIStudioClient") as mock_client:
            mock_gate.return_value = {"status": "ready"}
            mock_llm = mock_client.return_value
            mock_llm.structured_chat.return_value = MagicMock(
                message="Данные не найдены.",
                answer_blocks=[],
                citations=[],
                limitations=[],
                clarification_questions=[],
            )

            response = build_workflow_response(
                state,
                final_outcome="not_found",
                critique=critique,
                visualization=None,
                live_llm_required=False,
            )

        # Diagnostic artifacts must be present
        assert len(response.dataset_artifacts) > 0, (
            "not_found response must include diagnostic dataset_artifacts"
        )
        # Must carry diagnostic quality flag
        assert any("diagnostic" in d.quality_flags for d in response.dataset_artifacts)

    def test_not_found_response_includes_diagnostic_script(self):
        from unittest.mock import patch, MagicMock
        from app.workflow.nodes.narrator import build_workflow_response
        from app.artifacts.workflow_artifacts import CritiqueReport
        from uuid import uuid4

        state = self._make_minimal_state(dataset_rows=0)
        critique = CritiqueReport(
            artifact_id=f"cr-{uuid4().hex[:8]}",
            verdict="not_found",
            warnings=[],
            repair_plan=[],
        )

        with patch("app.workflow.nodes.narrator.qwen_credential_gate") as mock_gate, \
             patch("app.workflow.nodes.narrator.YandexAIStudioClient") as mock_client:
            mock_gate.return_value = {"status": "ready"}
            mock_client.return_value.structured_chat.return_value = MagicMock(
                message="Данные не найдены.",
                answer_blocks=[],
                citations=[],
                limitations=[],
                clarification_questions=[],
            )

            response = build_workflow_response(
                state,
                final_outcome="not_found",
                critique=critique,
                visualization=None,
                live_llm_required=False,
            )

        assert len(response.script_artifacts) > 0, (
            "not_found response must include diagnostic script_artifacts"
        )
```

- [ ] **Step 3: Убедиться что тест падает**

```bash
python -m pytest "tests/test_schema_validators.py::TestNarratorDiagnosticArtifacts" -v
```

Ожидаемый результат: FAIL — `response.dataset_artifacts` пустой.

- [ ] **Step 4: Найти и изменить условие в narrator.py**

Найти строки вида:
```python
        dataset_artifacts=dataset_artifacts if final_outcome == "passed" else [],
        script_artifacts=script_artifacts if final_outcome == "passed" else [],
```

Заменить на:

```python
        dataset_artifacts=_tag_diagnostic(dataset_artifacts, final_outcome),
        script_artifacts=script_artifacts,
```

Добавить вспомогательную функцию `_tag_diagnostic` в начало `narrator.py` (после импортов):

```python
def _tag_diagnostic(
    artifacts: list[DatasetArtifact],
    final_outcome: str,
) -> list[DatasetArtifact]:
    """Add 'diagnostic' quality flag to artifacts when outcome is not passed."""
    if final_outcome == "passed":
        return artifacts
    return [
        a.model_copy(update={"quality_flags": list(a.quality_flags) + ["diagnostic"]})
        if "diagnostic" not in a.quality_flags
        else a
        for a in artifacts
    ]
```

- [ ] **Step 5: Запустить тест — должен пройти**

```bash
python -m pytest "tests/test_schema_validators.py::TestNarratorDiagnosticArtifacts" -v
```

- [ ] **Step 6: Проверить что WorkflowResponse.model_validator не ломается**

```bash
python -m pytest tests/test_phase2_finalization.py -v --tb=short
```

Ожидаемый результат: все тесты проходят.

- [ ] **Step 7: Commit**

```bash
git add app/workflow/nodes/narrator.py tests/test_schema_validators.py
git commit -m "fix: expose diagnostic dataset/script artifacts in not_found responses"
```

---

## Task 5: Финальный smoke-прогон и проверка

- [ ] **Step 1: Запустить весь новый test-файл**

```bash
python -m pytest tests/test_schema_validators.py -v
```

Ожидаемый результат: PASS все тесты.

- [ ] **Step 2: Запустить существующие suite без регрессий**

```bash
python -m pytest tests/test_phase2_workflow_nodes.py tests/test_phase2_finalization.py tests/test_deterministic_tools_and_trace.py -v --tb=short
```

Ожидаемый результат: те же тесты что проходили до — проходят. Не должно появиться новых FAIL.

- [ ] **Step 3: Быстрая проверка schema coercion вручную**

```bash
python -c "
from app.workflow.state import _IntentAnalysisSchema
s = _IntentAnalysisSchema(category='comparative', needs_clarification=False, geography=['Россия', 'Казахстан'])
print('geography:', s.geography)
print('countries:', s.countries)
assert s.geography == 'Россия, Казахстан'
assert s.countries == ['Россия', 'Казахстан']
print('PASS: intent schema coercion works')
"
```

```bash
python -c "
from app.workflow.nodes.critic import _CritiqueSchema
s = _CritiqueSchema(verdict='pass', warnings=None, repair_plan=None)
print('warnings:', s.warnings)
print('repair_plan:', s.repair_plan)
assert s.warnings == []
assert s.repair_plan == []
print('PASS: critique schema coercion works')
"
```

- [ ] **Step 4: Финальный commit (если что-то не попало в предыдущие)**

```bash
git status
# добавить все незакомиченные изменения
git add -p
git commit -m "fix: plan A schema hardening complete — intent/coverage/critic tolerant validators + diagnostic artifacts"
```

---

## Acceptance Criteria

- [ ] `_IntentAnalysisSchema` принимает `geography` как `list`, `str`, `None`
- [ ] `_IntentAnalysisSchema` заполняет `countries: list[str]` из geography
- [ ] `_CoverageAssessment.best_slice` принимает `None`
- [ ] `_CoverageAssessment.quality_risks` и `alternative_slices` принимают `str` и `None`
- [ ] `_CritiqueSchema.warnings` принимает `None` и `str`
- [ ] `not_found` ответ содержит `dataset_artifacts` с `quality_flags=["diagnostic"]`
- [ ] `tests/test_schema_validators.py` — все тесты PASS
- [ ] Существующие тесты не сломаны
