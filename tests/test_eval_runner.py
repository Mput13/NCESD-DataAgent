from __future__ import annotations

import json
from pathlib import Path


def test_eval_runner_records_gated_components_without_silent_success(tmp_path: Path) -> None:
    from app.evals.run_eval import run_evaluation

    result = run_evaluation(
        goldens_path=Path(".planning/phases/01-data-architecture-research/golden-cases.yaml"),
        retrieval_eval_path=Path(".planning/phases/01-data-architecture-research/retrieval-eval.csv"),
        extraction_probes_path=Path(".planning/phases/01-data-architecture-research/extraction-probes.json"),
        index_manifest_path=Path(".planning/phases/01-data-architecture-research/embedding-index-manifest.json"),
        json_output=tmp_path / "data-relevance-eval.json",
        markdown_output=tmp_path / "data-relevance-eval.md",
    )

    assert result["total_cases"] > 0
    assert result["qdrant_status"] in {"ready", "gated_skip"}
    assert "passed" in result and "failed" in result and "gated" in result
    assert result["gated"] > 0
    assert all("case_id" in item and "status" in item for item in result["cases"])
    assert not any(
        item["status"] == "passed" and item["gated_reasons"]
        for item in result["cases"]
    )
    written = json.loads((tmp_path / "data-relevance-eval.json").read_text(encoding="utf-8"))
    assert written["total_cases"] == result["total_cases"]
    assert "Data Relevance Evaluation" in (tmp_path / "data-relevance-eval.md").read_text(encoding="utf-8")
