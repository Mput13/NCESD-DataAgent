from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel


class _IntentSchema(BaseModel):
    metric: str
    geography: str
    needs_clarification: bool


def test_qwen_client_uses_verified_base_url_and_api_key_header(monkeypatch) -> None:
    from app.llm.yandex_ai_studio import (
        DEFAULT_BASE_URL,
        YandexAIStudioClient,
        YandexAIStudioConfig,
    )

    captured: dict[str, Any] = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(url: str, **kwargs: Any) -> _Response:
        captured["url"] = url
        captured.update(kwargs)
        return _Response()

    monkeypatch.setattr("requests.post", fake_post)

    client = YandexAIStudioClient(
        YandexAIStudioConfig(
            api_key="secret",
            model="gpt://folder/qwen3/latest",
        )
    )

    assert DEFAULT_BASE_URL == "https://llm.api.cloud.yandex.net/v1"
    assert client.chat([{"role": "user", "content": "ping"}]) == "ok"
    assert captured["url"] == "https://llm.api.cloud.yandex.net/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Api-Key secret"


def test_structured_output_helper_sends_json_schema(monkeypatch) -> None:
    from app.llm.yandex_ai_studio import YandexAIStudioClient, YandexAIStudioConfig

    captured: dict[str, Any] = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"metric":"GDP","geography":"Russia",'
                                '"needs_clarification":false}'
                            )
                        }
                    }
                ]
            }

    def fake_post(url: str, **kwargs: Any) -> _Response:
        captured["url"] = url
        captured.update(kwargs)
        return _Response()

    monkeypatch.setattr("requests.post", fake_post)

    client = YandexAIStudioClient(
        YandexAIStudioConfig(
            api_key="secret",
            model="gpt://folder/qwen3/latest",
        )
    )
    intent = client.structured_chat(
        [{"role": "user", "content": "ВВП России"}],
        schema=_IntentSchema,
    )

    assert intent.metric == "GDP"
    assert captured["json"]["response_format"]["type"] == "json_schema"
    assert captured["json"]["response_format"]["json_schema"]["name"] == "IntentSchema"
    assert "needs_clarification" in str(captured["json"]["response_format"])


def test_spike_report_records_credential_gate_and_deepseek_fallback_note() -> None:
    report = Path(
        ".planning/phases/01-data-architecture-research/yandex-qwen-spike.md"
    ).read_text(encoding="utf-8")

    assert "YANDEX_AI_STUDIO_QWEN_API_KEY" in report
    assert "gated_skip" in report
    assert "structured-output" in report
    assert "DeepSeek historical fallback only" in report
