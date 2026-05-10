from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.workflow.service import (
    WorkflowRunConfig,
    apply_feedback,
    continue_user_query,
    run_user_query,
)


STATIC_DIR = Path(__file__).resolve().parent / "static"


class DataAgentWebHandler(SimpleHTTPRequestHandler):
    server_version = "DataAgentWeb/0.1"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._write_json({"status": "ok"})
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path == "/api/query":
                self._handle_query(payload)
                return
            if parsed.path == "/api/continue":
                self._handle_continue(payload)
                return
            if parsed.path == "/api/feedback":
                self._handle_feedback(payload)
                return
            self._write_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._write_json(
                {"error": "server_error", "detail": str(exc)},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _run_config(self, payload: dict[str, Any]) -> WorkflowRunConfig:
        default = WorkflowRunConfig.default()
        local_mode = bool(payload.get("local_mode", True))
        return default.model_copy(
            update={
                "live_llm_required": not local_mode,
                "live_embeddings_required": not local_mode,
            }
        )

    def _handle_query(self, payload: dict[str, Any]) -> None:
        query = str(payload.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        response = run_user_query(query, run_config=self._run_config(payload))
        self._write_json(response.model_dump(mode="json"))

    def _handle_continue(self, payload: dict[str, Any]) -> None:
        run_id = str(payload.get("run_id") or "").strip()
        answer = str(payload.get("answer") or "").strip()
        if not run_id:
            raise ValueError("run_id is required")
        if not answer:
            raise ValueError("answer is required")
        response = continue_user_query(run_id, answer, run_config=self._run_config(payload))
        self._write_json(response.model_dump(mode="json"))

    def _handle_feedback(self, payload: dict[str, Any]) -> None:
        run_id = str(payload.get("run_id") or "").strip()
        comment = str(payload.get("user_comment") or "").strip()
        if not run_id:
            raise ValueError("run_id is required")
        if not comment:
            raise ValueError("user_comment is required")
        result = apply_feedback(
            run_id,
            rating=payload.get("rating"),
            user_comment=comment,
            requested_action=payload.get("requested_action"),
            target_state=payload.get("target_state"),
            run_config=self._run_config(payload),
        )
        self._write_json(result.model_dump(mode="json"))

    def _write_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def run_server(host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), DataAgentWebHandler)
    print(f"DataAgent web UI: http://{host}:{port}", flush=True)
    server.serve_forever()
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the minimal DataAgent web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8787, type=int)
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
