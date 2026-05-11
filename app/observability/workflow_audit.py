from __future__ import annotations

import json
import time
from contextlib import ExitStack
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

from app.artifacts.workflow_artifacts import utc_now_iso


class WorkflowAuditSession:
    """Runtime observer for one headless workflow run.

    The session patches boundary functions while active and writes inputs,
    outputs, errors, and durations to JSONL files. It does not change prompts,
    graph routing, state payloads, or return values.
    """

    def __init__(self, audit_dir: Path, *, item_id: str, query: str) -> None:
        self.audit_dir = audit_dir
        self.item_id = item_id
        self.query = query
        self._stack = ExitStack()

    def __enter__(self) -> WorkflowAuditSession:
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.record("node-events.jsonl", "audit_start", {"item_id": self.item_id, "query": self.query})
        self._install_patches()
        return self

    def __exit__(self, exc_type: object, exc: BaseException | None, tb: object) -> None:
        self.record(
            "node-events.jsonl",
            "audit_end",
            {
                "item_id": self.item_id,
                "error_type": type(exc).__name__ if exc else None,
                "error": str(exc) if exc else None,
            },
        )
        self._stack.close()

    def record(self, filename: str, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "ts": utc_now_iso(),
            "item_id": self.item_id,
            "event_type": event_type,
            "payload": _safe(payload),
        }
        with (self.audit_dir / filename).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def _install_patches(self) -> None:
        import app.llm.yandex_ai_studio as yandex
        import app.retrieval.hybrid_retrieval as retrieval
        import app.workflow.graph as graph
        import app.workflow.service as service
        import app.workflow.nodes.deterministic_tools as deterministic_tools

        self._patch_method(yandex.YandexAIStudioClient, "chat", self._wrap_llm_chat)
        self._patch_method(yandex.YandexAIStudioClient, "structured_chat", self._wrap_structured_chat)

        self._patch_method(retrieval.LexicalBM25Retriever, "search", self._wrap_named_call("retrieval-lexical"))
        self._patch_method(retrieval.DenseQdrantRetriever, "search", self._wrap_named_call("retrieval-dense"))
        self._patch_method(retrieval.DenseQdrantRetriever, "fetch_by_card_ids", self._wrap_named_call("retrieval-dense-fetch-by-card-id"))
        self._patch_method(retrieval.GraphExpander, "expand", self._wrap_named_call("retrieval-graph-expand"))
        self._patch_method(retrieval.HybridRetriever, "_graph_first", self._wrap_named_call("retrieval-graph-first"))
        self._patch_method(retrieval.HybridRetriever, "search", self._wrap_named_call("retrieval-hybrid-search"))
        self._patch_attr(retrieval, "_rrf_fuse", self._wrap_named_call("retrieval-rrf-fuse"))
        self._patch_attr(retrieval, "_split_rejections", self._wrap_named_call("retrieval-split-rejections"))

        for name in (
            "_node_supervisor",
            "_node_intent_analyst",
            "_node_research_designer",
            "_node_source_scouts",
            "_node_coverage_schema",
            "_node_extraction_planner",
            "_node_deterministic_tools",
            "_node_finalization_pending",
        ):
            self._patch_attr(graph, name, self._wrap_graph_node(name.removeprefix("_node_")))

        self._patch_attr(service, "_finalize_state", self._wrap_named_call("finalize-state"))
        self._patch_attr(deterministic_tools, "run_deterministic_tools", self._wrap_named_call("deterministic-tools"))
        self._patch_attr(deterministic_tools, "_dispatch_extraction", self._wrap_named_call("deterministic-dispatch-extraction"))
        self._patch_attr(deterministic_tools, "export_dataset_with_script", self._wrap_named_call("deterministic-export-script"))

    def _patch_method(self, cls: type, name: str, factory: Callable[[Callable[..., Any]], Callable[..., Any]]) -> None:
        original = getattr(cls, name)
        self._stack.enter_context(patch.object(cls, name, factory(original)))

    def _patch_attr(self, module: Any, name: str, factory: Callable[[Callable[..., Any]], Callable[..., Any]]) -> None:
        original = getattr(module, name)
        self._stack.enter_context(patch.object(module, name, factory(original)))

    def _wrap_graph_node(self, node_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def factory(fn: Callable[..., Any]) -> Callable[..., Any]:
            def wrapped(state: Any, *args: Any, **kwargs: Any) -> Any:
                started = time.perf_counter()
                self.record(
                    "node-events.jsonl",
                    "node_start",
                    {"node": node_name, "input_state": _state_snapshot(state)},
                )
                try:
                    result = fn(state, *args, **kwargs)
                except Exception as exc:
                    self.record(
                        "node-events.jsonl",
                        "node_error",
                        {
                            "node": node_name,
                            "duration_ms": _duration_ms(started),
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                    raise
                self.record(
                    "node-events.jsonl",
                    "node_end",
                    {
                        "node": node_name,
                        "duration_ms": _duration_ms(started),
                        "output_state": _state_snapshot(result),
                    },
                )
                return result

            return wrapped

        return factory

    def _wrap_named_call(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def factory(fn: Callable[..., Any]) -> Callable[..., Any]:
            def wrapped(*args: Any, **kwargs: Any) -> Any:
                started = time.perf_counter()
                self.record(
                    _event_file_for(name),
                    f"{name}_start",
                    {"args": _safe_args(args), "kwargs": kwargs},
                )
                try:
                    result = fn(*args, **kwargs)
                except Exception as exc:
                    self.record(
                        _event_file_for(name),
                        f"{name}_error",
                        {
                            "duration_ms": _duration_ms(started),
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                    raise
                self.record(
                    _event_file_for(name),
                    f"{name}_end",
                    {"duration_ms": _duration_ms(started), "result": result},
                )
                return result

            return wrapped

        return factory

    def _wrap_llm_chat(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(client: Any, messages: list[dict[str, str]], *args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            payload = {
                "model": getattr(client.config, "model", None),
                "base_url": getattr(client.config, "base_url", None),
                "messages": messages,
                "kwargs": kwargs,
            }
            self.record("llm-calls.jsonl", "llm_chat_start", payload)
            try:
                result = fn(client, messages, *args, **kwargs)
            except Exception as exc:
                self.record(
                    "llm-calls.jsonl",
                    "llm_chat_error",
                    {
                        **payload,
                        "duration_ms": _duration_ms(started),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
                raise
            self.record(
                "llm-calls.jsonl",
                "llm_chat_end",
                {**payload, "duration_ms": _duration_ms(started), "response_text": result},
            )
            return result

        return wrapped

    def _wrap_structured_chat(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(client: Any, messages: list[dict[str, str]], *args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            schema = kwargs.get("schema")
            payload = {
                "model": getattr(client.config, "model", None),
                "base_url": getattr(client.config, "base_url", None),
                "schema": getattr(schema, "__name__", str(schema)),
                "schema_fields": list(getattr(schema, "model_fields", {}).keys()) if schema else [],
                "messages": messages,
                "kwargs": {k: v for k, v in kwargs.items() if k != "schema"},
            }
            self.record("llm-calls.jsonl", "llm_structured_start", payload)
            try:
                result = fn(client, messages, *args, **kwargs)
            except Exception as exc:
                self.record(
                    "llm-calls.jsonl",
                    "llm_structured_error",
                    {
                        **payload,
                        "duration_ms": _duration_ms(started),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
                raise
            self.record(
                "llm-calls.jsonl",
                "llm_structured_end",
                {**payload, "duration_ms": _duration_ms(started), "parsed": result},
            )
            return result

        return wrapped


def _event_file_for(name: str) -> str:
    if name.startswith("retrieval"):
        return "retrieval.jsonl"
    if name.startswith("deterministic"):
        return "tool-calls.jsonl"
    return "node-events.jsonl"


def _duration_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _safe_args(args: tuple[Any, ...]) -> list[Any]:
    if not args:
        return []
    first, *rest = args
    first_repr = _compact_self(first)
    return [first_repr, *rest]


def _compact_self(value: Any) -> Any:
    cls = value.__class__
    if cls.__module__.startswith("app."):
        return {"class": f"{cls.__module__}.{cls.__name__}"}
    return value


def _state_snapshot(state: Any) -> Any:
    if not isinstance(state, dict):
        return state
    keys = [
        "run_id",
        "query",
        "pending_reason",
        "finalization_pending",
        "component_statuses",
        "intent",
        "research_design",
        "evidence",
        "coverage_reports",
        "extraction_plan",
        "dataset_artifacts",
        "script_artifacts",
        "final_outcome",
    ]
    return {key: state.get(key) for key in keys if key in state}


def _safe(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return "<max_depth>"
    if hasattr(value, "model_dump"):
        return _safe(value.model_dump(mode="json"), depth=depth + 1)
    if is_dataclass(value):
        return _safe(asdict(value), depth=depth + 1)
    if isinstance(value, dict):
        return {str(k): _safe(v, depth=depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe(item, depth=depth + 1) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        if len(value) > 120_000:
            return value[:120_000] + f"...<truncated {len(value) - 120_000} chars>"
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    cls = value.__class__
    if cls.__module__.startswith("app."):
        return {"class": f"{cls.__module__}.{cls.__name__}", "repr": repr(value)}
    return repr(value)
