from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings
from app.contracts import SourceFamily, WorkflowOutcome
from app.sources.world_bank import WorldBankAdapter
from app.workflow import run_query


def test_empty_query_needs_clarification(tmp_path: Path) -> None:
    settings = Settings(artifact_root=tmp_path)
    response = run_query("", settings=settings)

    assert response.outcome == WorkflowOutcome.NEEDS_CLARIFICATION
    assert response.trace_events
    assert (tmp_path / response.run_id / "workflow-response.json").exists()


def test_no_configured_sources_returns_not_found(tmp_path: Path) -> None:
    settings = Settings(artifact_root=tmp_path)
    response = run_query("GDP Russia 2024", settings=settings)

    assert response.outcome == WorkflowOutcome.NOT_FOUND
    assert "No real source adapters" in response.message
    assert response.selected_sources == []


def test_world_bank_adapter_uses_metadata_fixture(tmp_path: Path) -> None:
    wb_root = tmp_path / "wb"
    wb_root.mkdir()
    (wb_root / "indicators.json").write_text(
        json.dumps(
            [
                {
                    "id": "NY.GDP.MKTP.CD",
                    "name": "GDP current US dollars",
                    "unit": "current US$",
                    "sourceNote": "Gross domestic product by country.",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    adapter = WorldBankAdapter(root=wb_root)
    candidates = adapter.search("GDP country", limit=3)

    assert len(candidates) == 1
    assert candidates[0].source_family == SourceFamily.WORLD_BANK
    assert candidates[0].indicator_id == "NY.GDP.MKTP.CD"
    assert candidates[0].match_mode.value == "lexical"


def test_app_contains_no_mock_or_old_demo_markers() -> None:
    forbidden = ("MOCK DATA", "Eurostat COMEXT", "DS_059341", "/api/stream", "fake backend")
    app_root = Path("app")
    scanned = []
    for path in app_root.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".js", ".html"}:
            text = path.read_text(encoding="utf-8")
            scanned.append(path)
            for marker in forbidden:
                assert marker not in text, f"{marker!r} found in {path}"
    assert scanned
