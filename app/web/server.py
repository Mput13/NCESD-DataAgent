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


def _serialize_trace(event: Any) -> dict[str, Any]:
    """Serialize a TraceEvent to a plain dict for JSON/SSE."""
    if hasattr(event, "model_dump"):
        return event.model_dump(mode="json")
    if isinstance(event, dict):
        return event
    return {"raw": str(event)}


class DataAgentWebHandler(SimpleHTTPRequestHandler):
    server_version = "DataAgentWeb/0.1"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._write_json({"status": "ok"})
            return
        if parsed.path == "/api/download":
            self._handle_download(parsed)
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def _handle_download(self, parsed: Any) -> None:
        from urllib.parse import parse_qs
        qs = parse_qs(parsed.query)
        file_path = qs.get("path", [None])[0]
        if not file_path:
            self._write_json({"error": "missing path"}, status=HTTPStatus.BAD_REQUEST)
            return
        p = Path(file_path)
        # Safety: only allow files inside project directory
        try:
            p.resolve().relative_to(Path(".").resolve())
        except ValueError:
            self._write_json({"error": "forbidden"}, status=HTTPStatus.FORBIDDEN)
            return
        if not p.exists():
            self._write_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return
        data = p.read_bytes()
        filename = p.name
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/csv; charset=utf-8" if filename.endswith(".csv") else "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        # /api/stream handles its own headers and exceptions — must not go through
        # the generic try/except below which would try to write a JSON error body
        # on top of an already-opened SSE stream.
        if parsed.path == "/api/stream":
            try:
                payload = self._read_json()
            except Exception as exc:
                self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._handle_stream(payload)
            return
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
        local_mode = bool(payload.get("local_mode", False))
        default = WorkflowRunConfig.default()
        return default.model_copy(
            update={
                "live_llm_required": not local_mode,
                "live_embeddings_required": not local_mode,
            }
        )

    def _handle_stream(self, payload: dict[str, Any]) -> None:
        query = str(payload.get("query") or "").strip()
        if not query:
            self._write_json({"error": "query is required"}, status=HTTPStatus.BAD_REQUEST)
            return

        self.send_response(200)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-cache")
        self.send_header("x-accel-buffering", "no")
        self.end_headers()

        def _sse(event: str, data: dict[str, Any]) -> None:
            line = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
            try:
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass

        # --- Agent descriptions shown to the user while thinking ---
        _AGENT_DESCRIPTIONS: dict[str, str] = {
            "supervisor": "Супервизор анализирует запрос и выбирает маршрут исследования...",
            "intent_analyst": "Анализатор намерений разбирает запрос: показатель, период, география...",
            "research_designer": "Дизайнер исследования строит гипотезы и выбирает измерения...",
            "source_scouts": "Разведчики источников ищут данные в FedStat, World Bank, CKAN...",
            "coverage_schema": "Проверка покрытия: есть ли нужные периоды, единицы, схема...",
            "extraction_planner": "Планировщик извлечения строит план запросов к данным...",
            "deterministic_tools": "Детерминированные инструменты извлекают реальные данные...",
            "finalization_pending": "Завершение: критик и нарратор формируют итоговый ответ...",
        }

        try:
            config = self._run_config(payload)

            from app.workflow.service import _finalize_state
            from app.workflow.state import new_run_id
            from app.workflow.graph import build_phase2_graph

            run_id = new_run_id()
            initial_state = {
                "run_id": run_id,
                "query": query,
                "intent": None,
                "research_design": None,
                "evidence": None,
                "coverage_reports": [],
                "extraction_plan": None,
                "dataset_artifacts": [],
                "script_artifacts": [],
                "final_outcome": None,
                "finalization_pending": False,
                "pending_reason": None,
                "trace_events": [],
                "component_statuses": {},
                "_live_llm_required": config.live_llm_required,
                "_live_embeddings_required": config.live_embeddings_required,
                "_artifact_dir": str(config.artifact_dir),
                "_index_manifest_path": str(config.phase1_index_manifest),
            }

            graph = build_phase2_graph()
            # Accumulate full state across chunks (stream returns deltas per node)
            accumulated_state: dict[str, Any] = dict(initial_state)
            seen_trace_count = 0

            for chunk in graph.stream(initial_state):
                for node_name, node_delta in chunk.items():
                    # Merge delta into accumulated state
                    if isinstance(node_delta, dict):
                        accumulated_state = {**accumulated_state, **node_delta}

                    trace_events = list(accumulated_state.get("trace_events") or [])
                    new_events = trace_events[seen_trace_count:]
                    seen_trace_count = len(trace_events)

                    description = _AGENT_DESCRIPTIONS.get(node_name, f"{node_name}...")
                    _sse("step", {
                        "node": node_name,
                        "description": description,
                        "run_id": run_id,
                        "new_trace_events": [
                            _serialize_trace(e) for e in new_events
                        ],
                    })

            # Finalization: critic + visualization + narrator
            _sse("step", {
                "node": "finalization",
                "description": "Критик проверяет качество данных, нарратор пишет ответ...",
                "run_id": run_id,
                "new_trace_events": [],
            })

            response = _finalize_state(accumulated_state, config=config)

            _sse("done", response.model_dump(mode="json"))

        except Exception as exc:
            _sse("error", {"message": str(exc)})

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
