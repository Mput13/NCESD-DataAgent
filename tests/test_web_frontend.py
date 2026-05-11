from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from app.artifacts.workflow_artifacts import NoDataExplanationArtifact, WorkflowResponse
from app.web.server import DataAgentWebHandler


class _FakeRequestHandler(DataAgentWebHandler):
    def __init__(self) -> None:
        self.status_code = 0
        self.headers: list[tuple[str, str]] = []
        self.body = b""

    def send_response(self, code: int, message: str | None = None) -> None:
        self.status_code = code

    def send_header(self, keyword: str, value: str) -> None:
        self.headers.append((keyword, value))

    def end_headers(self) -> None:
        pass

    @property
    def wfile(self):  # type: ignore[no-untyped-def]
        class Writer:
            def __init__(self, owner: _FakeRequestHandler) -> None:
                self.owner = owner

            def write(self, data: bytes) -> None:
                self.owner.body += data

        return Writer(self)


def test_static_frontend_files_exist_and_call_api() -> None:
    static_dir = Path("app/web/static")
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    js = (static_dir / "js" / "app.js").read_text(encoding="utf-8")
    css = (static_dir / "css" / "styles.css").read_text(encoding="utf-8")

    assert '<link rel="stylesheet" href="/css/styles.css"' in html
    assert '<script src="/js/app.js">' in html
    assert "/api/query" in js
    assert "/api/continue" in js
    assert ".workspace" in css


def test_web_handler_query_returns_workflow_response() -> None:
    handler = _FakeRequestHandler()
    payload = {"query": "test", "local_mode": True}

    fake = WorkflowResponse(
        run_id="phase2-web-test",
        final_outcome="not_found",
        message="No data.",
        not_found_evidence=NoDataExplanationArtifact(
            artifact_id="not-found-web",
            checked_sources=[],
            rejected_sources=[],
            rejection_reasons=["test"],
            search_strategy="test",
        ),
    )
    with patch("app.web.server.run_user_query", return_value=fake) as mocked:
        handler._handle_query(payload)

    assert handler.status_code == 200
    data = json.loads(handler.body.decode("utf-8"))
    assert data["run_id"] == "phase2-web-test"
    assert data["final_outcome"] == "not_found"
    assert mocked.call_args.kwargs["run_config"].live_llm_required is True


def test_web_handler_continue_requires_run_id() -> None:
    handler = _FakeRequestHandler()
    try:
        handler._handle_continue({"answer": "Russia"})
    except ValueError as exc:
        assert "run_id is required" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError")
