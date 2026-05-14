"""Tests for Variant B: codegen extraction agent."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.data.codegen_extractor import (
    _describe_schema,
    _validate_sql,
    _execute,
    _intent_summary,
    _detect_family,
    codegen_extract_dataset,
)
from app.artifacts.workflow_artifacts import DatasetArtifact, NoDataExplanationArtifact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_parquet(tmp_path: Path, df: pd.DataFrame) -> Path:
    p = tmp_path / "test.parquet"
    df.to_parquet(p, index=False)
    return p


# ---------------------------------------------------------------------------
# _describe_schema
# ---------------------------------------------------------------------------


def test_describe_schema_columns(tmp_path):
    df = pd.DataFrame({"region": ["Russia", "China"], "year": [2020, 2021], "gdp": [1.5, 2.0]})
    p = _write_parquet(tmp_path, df)
    info = _describe_schema(p)
    col_names = [c["name"] for c in info["columns"]]
    assert "region" in col_names
    assert "year" in col_names
    assert "gdp" in col_names
    assert len(info["sample_rows"]) == 2


def test_describe_schema_sample_truncated(tmp_path):
    df = pd.DataFrame({"x": list(range(20)), "v": list(range(20))})
    p = _write_parquet(tmp_path, df)
    info = _describe_schema(p)
    assert len(info["sample_rows"]) <= 5


# ---------------------------------------------------------------------------
# _validate_sql
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sql", [
    "SELECT * FROM read_parquet('x.parquet')",
    "select geo, value from read_parquet('x.parquet') where year=2020",
    "  SELECT geo AS geo_name, year AS period FROM source",
])
def test_validate_sql_ok(sql):
    assert _validate_sql(sql) is None


@pytest.mark.parametrize("sql,expected_fragment", [
    ("DROP TABLE foo", "must start with SELECT"),
    ("INSERT INTO t VALUES (1)", "must start with SELECT"),
    ("SELECT * FROM t; DELETE FROM t", "forbidden keyword"),
    ("SELECT * FROM t WHERE 1=1; DROP TABLE t", "forbidden keyword"),
])
def test_validate_sql_rejects(sql, expected_fragment):
    err = _validate_sql(sql)
    assert err is not None
    assert expected_fragment in err


# ---------------------------------------------------------------------------
# _execute
# ---------------------------------------------------------------------------


def test_execute_returns_rows(tmp_path):
    df = pd.DataFrame({
        "region": ["Russia", "China"],
        "year": ["2020", "2021"],
        "value": [1500.0, 2000.0],
        "unit": ["млрд руб", "млрд руб"],
    })
    p = _write_parquet(tmp_path, df)
    safe = str(p).replace("'", "''")
    sql = f"SELECT region AS geo_name, year AS period, value, unit FROM read_parquet('{safe}')"
    rows = _execute(sql, p)
    assert len(rows) == 2
    assert rows[0]["geo_name"] == "Russia"
    assert rows[0]["value"] == 1500.0


def test_execute_supports_source_relation(tmp_path):
    df = pd.DataFrame({
        "region": ["Russia"],
        "year": ["2022"],
        "amount": [2240.0],
        "unit": ["USD"],
    })
    p = _write_parquet(tmp_path, df)
    rows = _execute("SELECT region AS geo_name, year AS period, amount, unit FROM source", p)
    assert rows == [{"geo_name": "Russia", "period": "2022", "amount": 2240.0, "unit": "USD"}]


def test_execute_rejects_unknown_table_alias(tmp_path):
    df = pd.DataFrame({"region": ["Russia"], "value": [1.0]})
    p = _write_parquet(tmp_path, df)
    with pytest.raises(ValueError, match="FROM source"):
        _execute("SELECT region, value FROM df", p)


def test_execute_raises_on_bad_sql(tmp_path):
    df = pd.DataFrame({"x": [1]})
    p = _write_parquet(tmp_path, df)
    with pytest.raises(Exception):
        _execute("SELECT nonexistent_column FROM read_parquet('nowhere.parquet')", p)


# ---------------------------------------------------------------------------
# _detect_family
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("card,expected", [
    ({"source_family": "fedstat"}, "fedstat"),
    ({"source_family": "world_bank"}, "world_bank"),
    ({"dataset_id": "40578"}, "fedstat"),
    ({"dataset_id": "NY.GDP.MKTP.CD"}, "world_bank"),
    ({"dataset_id": "SH_UHC_FH40_LARGE"}, "world_bank"),
    ({"dataset_id": "fin30.2"}, "unknown"),
    ({"dataset_id": "fin30.2", "card_id": "world_bank:fin30.2:wb/parquet/fin30.2.parquet"}, "world_bank"),
    ({}, "unknown"),
])
def test_detect_family(card, expected):
    assert _detect_family(card) == expected


@pytest.mark.parametrize("source_id,expected", [
    ("40578", "fedstat"),
    ("NY.GDP.MKTP.CD", "world_bank"),
    ("SH_UHC_FH40_LARGE", "world_bank"),
    ("fin30.2", "unknown"),
])
def test_workflow_family_detection_matches_codegen_for_ids(source_id, expected):
    from app.artifacts.workflow_artifacts import ExtractionPlan
    from app.workflow.nodes.deterministic_tools import _resolve_source_family

    plan = ExtractionPlan(artifact_id="plan-test", source_id=source_id, operations=[])
    card = {"dataset_id": source_id}
    assert _resolve_source_family(plan) == expected
    assert _detect_family(card) == expected


# ---------------------------------------------------------------------------
# _intent_summary
# ---------------------------------------------------------------------------


def test_intent_summary_with_intent():
    intent = MagicMock()
    intent.query = "ВВП России 2020"
    intent.known_fields = {"geography": "Russia", "periods": ["2020"]}
    summary = _intent_summary(intent, {"geography": "Russia"})
    assert "ВВП России 2020" in summary
    assert "Russia" in summary


def test_intent_summary_no_intent():
    summary = _intent_summary(None, {"periods": ["2020"]})
    assert "2020" in summary


# ---------------------------------------------------------------------------
# codegen_extract_dataset — integration (mocked LLM)
# ---------------------------------------------------------------------------


def test_codegen_success_on_first_attempt(tmp_path):
    df = pd.DataFrame({
        "region": ["Russia"],
        "year": ["2020"],
        "value": [1500.5],
        "unit": ["млрд руб"],
    })
    p = _write_parquet(tmp_path, df)
    sql = "SELECT region AS geo_name, year AS period, value, unit FROM source"

    source_card = {"source_family": "fedstat", "dataset_id": "40578", "local_path": str(p)}

    with patch("app.llm.yandex_ai_studio.qwen_credential_gate", return_value={"status": "ok"}), \
         patch("app.data.codegen_extractor._generate_query", return_value=sql):
        result = codegen_extract_dataset(
            source_card, None, {}, output_dir=tmp_path, artifact_id="test-art"
        )

    assert isinstance(result, DatasetArtifact)
    assert result.rows == 1
    assert result.records[0]["value"] == 1500.5
    assert "codegen_extraction" in result.quality_flags


def test_codegen_normalizes_amount_column_to_value(tmp_path):
    df = pd.DataFrame({
        "region": ["Russia"],
        "year": ["2022"],
        "amount": [2240.0],
        "unit": ["USD"],
    })
    p = _write_parquet(tmp_path, df)
    source_card = {"source_family": "fedstat", "dataset_id": "40578", "local_path": str(p)}
    sql = "SELECT region AS geo_name, year AS period, amount, unit FROM source"

    with patch("app.llm.yandex_ai_studio.qwen_credential_gate", return_value={"status": "ok"}), \
         patch("app.data.codegen_extractor._generate_query", return_value=sql):
        result = codegen_extract_dataset(
            source_card, None, {}, output_dir=tmp_path, artifact_id="test-amount"
        )

    assert isinstance(result, DatasetArtifact)
    assert result.records[0]["value"] == 2240.0


def test_codegen_retries_on_unresolvable_value_column(tmp_path):
    df = pd.DataFrame({"region": ["Russia"], "year": ["2022"], "label": ["n/a"]})
    p = _write_parquet(tmp_path, df)
    source_card = {"source_family": "fedstat", "dataset_id": "40578", "local_path": str(p)}

    with patch("app.llm.yandex_ai_studio.qwen_credential_gate", return_value={"status": "ok"}), \
         patch("app.data.codegen_extractor._generate_query", return_value="SELECT * FROM source"):
        result = codegen_extract_dataset(
            source_card, None, {}, output_dir=tmp_path, artifact_id="test-no-value", max_retries=1
        )

    assert isinstance(result, NoDataExplanationArtifact)
    assert any("normalization error" in reason for reason in result.rejection_reasons)


def test_codegen_retries_on_null_values(tmp_path):
    df = pd.DataFrame({
        "region": ["Russia"],
        "year": ["2020"],
        "value": [None],
        "unit": [""],
    })
    p = _write_parquet(tmp_path, df)
    safe = str(p).replace("'", "''")
    null_sql = f"SELECT region AS geo_name, year AS period, value, unit FROM read_parquet('{safe}')"

    df_good = pd.DataFrame({"region": ["Russia"], "year": ["2020"], "value": [999.0], "unit": ["руб"]})
    p_good = tmp_path / "good.parquet"
    df_good.to_parquet(p_good, index=False)
    safe_good = str(p_good).replace("'", "''")
    good_sql = f"SELECT region AS geo_name, year AS period, value, unit FROM read_parquet('{safe_good}')"

    source_card = {"source_family": "fedstat", "dataset_id": "40578", "local_path": str(p)}
    call_count = 0

    def _gen(*, schema_info, intent_text, parquet_path, error_feedback, attempt):
        nonlocal call_count
        call_count += 1
        if attempt == 1:
            return null_sql
        # On retry, return query against the good file to simulate fix
        return good_sql

    with patch("app.llm.yandex_ai_studio.qwen_credential_gate", return_value={"status": "ok"}), \
         patch("app.data.codegen_extractor._generate_query", side_effect=_gen):
        result = codegen_extract_dataset(
            source_card, None, {}, output_dir=tmp_path, artifact_id="test-art-2"
        )

    assert isinstance(result, DatasetArtifact)
    assert result.rows == 1
    assert call_count == 2


def test_codegen_returns_no_data_when_gated(tmp_path):
    df = pd.DataFrame({"x": [1]})
    p = _write_parquet(tmp_path, df)
    source_card = {"source_family": "fedstat", "dataset_id": "40578", "local_path": str(p)}
    with patch("app.llm.yandex_ai_studio.qwen_credential_gate", return_value={"status": "gated_skip"}):
        result = codegen_extract_dataset(
            source_card, None, {}, output_dir=tmp_path, artifact_id="test-gated"
        )
    assert isinstance(result, NoDataExplanationArtifact)
    assert any("gated" in r for r in result.rejection_reasons)


def test_codegen_returns_no_data_after_all_retries_fail(tmp_path):
    df = pd.DataFrame({"a": [1]})
    p = _write_parquet(tmp_path, df)
    source_card = {"source_family": "fedstat", "dataset_id": "40578", "local_path": str(p)}

    with patch("app.llm.yandex_ai_studio.qwen_credential_gate", return_value={"status": "ok"}), \
         patch("app.data.codegen_extractor._generate_query", return_value=None):
        result = codegen_extract_dataset(
            source_card, None, {}, output_dir=tmp_path, artifact_id="test-fail", max_retries=2
        )

    assert isinstance(result, NoDataExplanationArtifact)
    assert any("codegen_failed" in r for r in result.rejection_reasons)
