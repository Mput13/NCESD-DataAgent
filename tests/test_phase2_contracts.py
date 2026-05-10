from __future__ import annotations


def test_phase2_runtime_imports_declared_dependencies() -> None:
    import duckdb
    import langgraph
    import pyarrow
    import pydantic
    import qdrant_client
    import streamlit

    assert duckdb
    assert langgraph
    assert pyarrow
    assert pydantic
    assert qdrant_client
    assert streamlit
