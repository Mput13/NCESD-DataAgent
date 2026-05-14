"""Variant B: code-gen extraction agent.

LLM sees the real Parquet schema and writes a DuckDB SELECT query.
DuckDB executes it deterministically — numbers come from the file, not LLM output.
Retries up to max_retries times with error feedback on empty/failed results.

Entry point:
    codegen_extract_dataset(source_card, intent, filters, output_dir, artifact_id)

Returns DatasetArtifact on success, NoDataExplanationArtifact on permanent failure.
"""
from __future__ import annotations

import re
from numbers import Number
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb

from app.artifacts.workflow_artifacts import (
    DatasetArtifact,
    NoDataExplanationArtifact,
    utc_now_iso,
)

_MAX_RETRIES = 3
_SAMPLE_ROWS = 5
_MAX_SCHEMA_COLS = 60
_SAFE_SQL_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_UNSAFE_KEYWORDS_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|COPY|ATTACH|INSTALL|LOAD)\b",
    re.IGNORECASE,
)
_SOURCE_RELATION_RE = re.compile(r"\bFROM\s+source\b", re.IGNORECASE)
_VALUE_ALIASES = ("value", "obs_value", "amount", "gdp", "metric_value")
_NUMERIC_VALUE_EXCLUDE = {
    "period",
    "year",
    "date",
    "geo_id",
    "country_id",
    "indicator_id",
    "id",
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def codegen_extract_dataset(
    source_card: dict[str, Any],
    intent: Any,
    filters: dict[str, Any],
    *,
    output_dir: Path,
    artifact_id: str,
    max_retries: int = _MAX_RETRIES,
) -> DatasetArtifact | NoDataExplanationArtifact:
    """Generate and execute a DuckDB query via Qwen, retry on empty/error.

    Never returns LLM-generated text as numeric values — all values come from
    DuckDB executing against the real Parquet file.
    """
    source_family = _detect_family(source_card)
    try:
        parquet_path = _resolve_parquet_path(source_card, source_family)
    except FileNotFoundError as exc:
        return _no_data(artifact_id, source_card, [f"parquet_not_found: {exc}"])

    try:
        schema_info = _describe_schema(parquet_path)
    except Exception as exc:
        return _no_data(artifact_id, source_card, [f"schema_read_error: {exc}"])

    from app.llm.yandex_ai_studio import qwen_credential_gate
    gate = qwen_credential_gate()
    if gate["status"] == "gated_skip":
        return _no_data(artifact_id, source_card, ["llm_gated: Qwen credentials missing"])

    intent_text = _intent_summary(intent, filters)
    error_feedback: str | None = None
    attempts: list[str] = []

    for attempt in range(1, max_retries + 1):
        sql = _generate_query(
            schema_info=schema_info,
            intent_text=intent_text,
            parquet_path=parquet_path,
            error_feedback=error_feedback,
            attempt=attempt,
        )
        if sql is None:
            error_feedback = "LLM did not return a SQL query."
            continue

        validation_error = _validate_sql(sql)
        if validation_error:
            error_feedback = f"SQL validation failed: {validation_error}"
            attempts.append(f"attempt {attempt}: invalid SQL — {validation_error}")
            continue

        try:
            rows = _execute(sql, parquet_path)
        except Exception as exc:
            error_feedback = f"DuckDB execution error on attempt {attempt}: {exc}"
            attempts.append(f"attempt {attempt}: execution error — {exc}")
            continue

        try:
            normalized_rows = _normalize_result_rows(rows)
        except ValueError as exc:
            error_feedback = f"Result normalization failed: {exc}"
            attempts.append(f"attempt {attempt}: normalization error — {exc}")
            continue

        non_null_rows = [r for r in normalized_rows if r.get("value") is not None]
        if not non_null_rows:
            error_feedback = (
                f"Query returned {len(rows)} rows but all values are NULL. "
                "Try broader filters or different column names."
            )
            attempts.append(f"attempt {attempt}: {len(rows)} rows, all null values")
            continue

        return _build_artifact(
            artifact_id=artifact_id,
            source_card=source_card,
            source_family=source_family,
            rows=non_null_rows,
            sql=sql,
            output_dir=output_dir,
            parquet_path=parquet_path,
            attempts=attempts,
        )

    return _no_data(
        artifact_id,
        source_card,
        [f"codegen_failed_after_{max_retries}_attempts"] + attempts,
    )


# ---------------------------------------------------------------------------
# Schema introspection
# ---------------------------------------------------------------------------


def _describe_schema(parquet_path: Path) -> dict[str, Any]:
    """Return column names/types and a few sample rows from the Parquet file."""
    conn = duckdb.connect(database=":memory:")
    safe_path = str(parquet_path).replace("'", "''")

    desc = conn.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{safe_path}') LIMIT 0"
    ).fetchdf()

    cols = list(desc["column_name"].astype(str))
    types = list(desc["column_type"].astype(str))

    # Truncate very wide files for the prompt
    if len(cols) > _MAX_SCHEMA_COLS:
        cols = cols[:_MAX_SCHEMA_COLS]
        types = types[:_MAX_SCHEMA_COLS]

    try:
        sample_df = conn.execute(
            f"SELECT * FROM read_parquet('{safe_path}') LIMIT {_SAMPLE_ROWS}"
        ).fetchdf()
        sample = sample_df.to_dict(orient="records")
    except Exception:
        sample = []

    return {
        "columns": [{"name": c, "type": t} for c, t in zip(cols, types)],
        "sample_rows": sample,
        "parquet_path": str(parquet_path),
    }


# ---------------------------------------------------------------------------
# LLM query generation
# ---------------------------------------------------------------------------


def _generate_query(
    *,
    schema_info: dict[str, Any],
    intent_text: str,
    parquet_path: Path,
    error_feedback: str | None,
    attempt: int,
) -> str | None:
    """Ask Qwen for a DuckDB SELECT query. Returns the SQL string or None."""
    from pydantic import BaseModel
    from app.llm.yandex_ai_studio import YandexAIStudioClient

    class _QueryResult(BaseModel):
        sql: str
        reasoning: str = ""

    schema_text = "\n".join(
        f"  {col['name']} ({col['type']})"
        for col in schema_info["columns"]
    )
    sample_text = ""
    if schema_info["sample_rows"]:
        import json
        sample_text = "\nПервые строки:\n" + json.dumps(
            schema_info["sample_rows"][:3], ensure_ascii=False, default=str
        )

    safe_path = str(parquet_path).replace("\\", "/")

    feedback_section = ""
    if error_feedback:
        feedback_section = f"\n\nПредыдущая попытка завершилась ошибкой:\n{error_feedback}\nПожалуйста, исправь запрос."

    system_prompt = (
        "Ты — аналитик данных, специализирующийся на DuckDB и статистических базах данных. "
        "Твоя задача — написать DuckDB SQL-запрос для извлечения данных из Parquet-файла.\n\n"
        "СТРОГИЕ ПРАВИЛА:\n"
        "1. Используй ТОЛЬКО SELECT. Запрещены INSERT, UPDATE, DELETE, DROP, CREATE и т.д.\n"
        "2. Таблица уже подключена как source. Используй FROM source, не вызывай read_parquet самостоятельно.\n"
        "3. Выбирай реальные значения из колонок — не вычисляй числа самостоятельно.\n"
        "4. Результат должен содержать колонки: geo_name (или аналог), period (год), value (числовое значение), unit (единица измерения).\n"
        "   Используй AS для переименования: ... AS geo_name, ... AS period, ... AS value, ... AS unit.\n"
        "5. Фильтруй строки по нужной географии и периоду если возможно.\n"
        "6. Исключи строки с NULL в value.\n"
        "7. Отвечай строго в формате JSON."
    )

    user_prompt = (
        f"Запрос пользователя: {intent_text}\n\n"
        f"Таблица для запроса: source\n"
        f"Локальный файл уже подключен системой: {safe_path}\n\n"
        f"Схема таблицы source:\n{schema_text}{sample_text}"
        f"{feedback_section}"
    )

    try:
        client = YandexAIStudioClient()
        result = client.structured_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            schema=_QueryResult,
            temperature=0.0,
            max_tokens=1024,
        )
        sql = result.sql.strip()
        return sql if sql else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# SQL validation + execution
# ---------------------------------------------------------------------------


def _validate_sql(sql: str) -> str | None:
    """Return error message if SQL is unsafe, None if ok."""
    if not _SAFE_SQL_RE.match(sql):
        return "must start with SELECT"
    if _UNSAFE_KEYWORDS_RE.search(sql):
        return "contains forbidden keyword"
    return None


def _execute(sql: str, parquet_path: Path) -> list[dict[str, Any]]:
    """Execute SQL against the Parquet file and return rows as dicts."""
    safe_path = str(parquet_path).replace("'", "''")
    stripped_sql = sql.strip().rstrip(";")
    if "read_parquet" in stripped_sql.lower():
        resolved_sql = stripped_sql.replace(
            "read_parquet('PATH')", f"read_parquet('{safe_path}')"
        ).replace(
            "read_parquet('ПУТЬ')", f"read_parquet('{safe_path}')"
        ).replace(
            f"read_parquet('{str(parquet_path)}')", f"read_parquet('{safe_path}')"
        )
    elif _SOURCE_RELATION_RE.search(stripped_sql):
        resolved_sql = (
            f"WITH source AS (SELECT * FROM read_parquet('{safe_path}'))\n"
            f"{stripped_sql}"
        )
    else:
        raise ValueError("generated query must read from source using FROM source")

    conn = duckdb.connect(database=":memory:")
    df = conn.execute(resolved_sql).fetchdf()
    return df.to_dict(orient="records")


def _normalize_result_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return rows with canonical lower-case keys and a resolved numeric value."""
    if not rows:
        return []

    normalized: list[dict[str, Any]] = []
    for row in rows:
        canonical = {str(key).lower(): value for key, value in row.items()}
        value_key = _resolve_value_key(canonical)
        canonical["value"] = canonical.get(value_key)
        normalized.append(canonical)
    return normalized


def _resolve_value_key(row: dict[str, Any]) -> str:
    for alias in _VALUE_ALIASES:
        if alias in row:
            return alias

    numeric_candidates = [
        key
        for key, value in row.items()
        if key not in _NUMERIC_VALUE_EXCLUDE
        and isinstance(value, Number)
        and not isinstance(value, bool)
    ]
    if len(numeric_candidates) == 1:
        return numeric_candidates[0]
    if not numeric_candidates:
        raise ValueError("result has no value column or numeric value candidate")
    raise ValueError(f"result has ambiguous numeric value columns: {numeric_candidates}")


# ---------------------------------------------------------------------------
# Artifact builders
# ---------------------------------------------------------------------------


def _build_artifact(
    *,
    artifact_id: str,
    source_card: dict[str, Any],
    source_family: str,
    rows: list[dict[str, Any]],
    sql: str,
    output_dir: Path,
    parquet_path: Path,
    attempts: list[str],
) -> DatasetArtifact:
    """Map raw DuckDB rows to canonical DatasetArtifact format."""
    canonical_rows: list[dict[str, Any]] = []
    for row in rows:
        geo_name = str(
            row.get("geo_name") or row.get("geo_id") or row.get("country") or ""
        )
        period = str(row.get("period") or row.get("year") or "")
        value = row.get("value")
        unit = str(row.get("unit") or "")
        canonical_rows.append({
            "source": source_family,
            "dataset_id": str(source_card.get("dataset_id") or source_card.get("resource_id") or ""),
            "indicator_id": str(row.get("indicator_id") or ""),
            "indicator_name": str(row.get("indicator_name") or ""),
            "geo_id": str(row.get("geo_id") or geo_name),
            "geo_name": geo_name,
            "period": period,
            "period_type": "annual" if re.fullmatch(r"\d{4}", period) else "other",
            "value": float(value) if value is not None else None,
            "unit": unit,
            "dimensions": {},
            "source_url": str(source_card.get("provenance_url") or source_card.get("resource_url") or ""),
            "retrieved_at": utc_now_iso(),
        })

    from app.data.deterministic_tools import export_csv_parquet_manifest

    dataset = DatasetArtifact(
        artifact_id=artifact_id,
        source_id=str(source_card.get("dataset_id") or source_card.get("resource_id") or source_family),
        rows=len(canonical_rows),
        columns=list(canonical_rows[0].keys()) if canonical_rows else [],
        records=canonical_rows,
        status="ok",
        quality_flags=["codegen_extraction"] + (["retry"] if attempts else []),
        provenance=[{
            "source_family": source_family,
            "parquet_path": str(parquet_path),
            "sql": sql,
            "attempts": attempts,
            "generated_at": utc_now_iso(),
        }],
    )

    export_csv_parquet_manifest(dataset, output_dir=output_dir)
    return dataset


def _no_data(
    artifact_id: str,
    source_card: dict[str, Any],
    reasons: list[str],
) -> NoDataExplanationArtifact:
    source_id = str(source_card.get("dataset_id") or source_card.get("resource_id") or "unknown")
    return NoDataExplanationArtifact(
        artifact_id=artifact_id,
        checked_sources=[source_card],
        rejected_sources=[{"source_id": source_id, "reasons": reasons}],
        rejection_reasons=reasons,
        search_strategy="codegen_duckdb",
        alternatives=[],
        limitations=reasons,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_family(source_card: dict[str, Any]) -> str:
    from app.data.source_family import detect_source_family_from_card

    return detect_source_family_from_card(source_card)


def _resolve_parquet_path(source_card: dict[str, Any], source_family: str) -> Path:
    """Reuse adapter path resolution logic."""
    if source_family == "fedstat":
        from app.data.fedstat_adapter import resolve_fedstat_parquet_path
        return resolve_fedstat_parquet_path(source_card)
    elif source_family == "world_bank":
        from app.data.world_bank_adapter import resolve_world_bank_parquet_path
        return resolve_world_bank_parquet_path(source_card)
    # Fallback: try direct candidates
    for key in ("local_path", "parquet_path", "resource_id"):
        val = source_card.get(key)
        if val:
            p = Path(str(val))
            if p.exists():
                return p
    raise FileNotFoundError(f"Cannot resolve parquet path for source_card: {source_card!r}")


def _intent_summary(intent: Any, filters: dict[str, Any]) -> str:
    parts: list[str] = []
    if intent and hasattr(intent, "query"):
        parts.append(f"Запрос: {intent.query}")
    if intent and hasattr(intent, "known_fields") and intent.known_fields:
        parts.append(f"Параметры: {intent.known_fields}")
    if filters:
        parts.append(f"Фильтры: {filters}")
    return "\n".join(parts) if parts else "неизвестный запрос"
