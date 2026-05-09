from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests
from dotenv import find_dotenv, load_dotenv


DEFAULT_BASE_URL = "https://ai.api.cloud.yandex.net/v1"


@dataclass(frozen=True)
class YandexAIStudioConfig:
    api_key: str
    model: str
    base_url: str = DEFAULT_BASE_URL

    @classmethod
    def from_env(cls) -> "YandexAIStudioConfig":
        load_dotenv(find_dotenv(usecwd=True))
        api_key = os.getenv("YANDEX_AI_STUDIO_API_KEY")
        model = os.getenv("YANDEX_AI_STUDIO_MODEL")
        base_url = os.getenv("YANDEX_AI_STUDIO_BASE_URL", DEFAULT_BASE_URL)

        missing = [
            name
            for name, value in {
                "YANDEX_AI_STUDIO_API_KEY": api_key,
                "YANDEX_AI_STUDIO_MODEL": model,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Missing required environment variables: " + ", ".join(missing)
            )

        return cls(api_key=api_key, model=model, base_url=base_url.rstrip("/"))


class YandexAIStudioClient:
    """Small OpenAI-compatible client for Yandex AI Studio chat completions."""

    def __init__(self, config: YandexAIStudioConfig | None = None) -> None:
        self.config = config or YandexAIStudioConfig.from_env()

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 512,
        timeout: int = 60,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        response = requests.post(
            f"{self.config.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"].get("content")
        if not content:
            raise RuntimeError("Yandex AI Studio response did not contain final content")
        return content.strip()


def smoke_prompt() -> str:
    client = YandexAIStudioClient()
    return client.chat(
        [
            {
                "role": "system",
                "content": "You are a concise assistant. Answer in Russian.",
            },
            {
                "role": "user",
                "content": "Ответь одним предложением: подключение к модели работает?",
            },
        ],
        max_tokens=512,
    )
