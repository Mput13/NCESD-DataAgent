from __future__ import annotations

import os
import json
from dataclasses import dataclass
from typing import Any, TypeVar

import requests
from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel


DEFAULT_BASE_URL = "https://llm.api.cloud.yandex.net/v1"
DEFAULT_QWEN_MODEL = "gpt://<folder_id>/qwen3/latest"

SchemaT = TypeVar("SchemaT", bound=BaseModel)


@dataclass(frozen=True)
class YandexAIStudioConfig:
    api_key: str
    model: str
    base_url: str = DEFAULT_BASE_URL

    @classmethod
    def from_env(cls, profile: str = "QWEN") -> "YandexAIStudioConfig":
        load_dotenv(find_dotenv(usecwd=True))
        profile = profile.upper()
        api_key = os.getenv(f"YANDEX_AI_STUDIO_{profile}_API_KEY")
        model = os.getenv(f"YANDEX_AI_STUDIO_{profile}_MODEL")
        if not api_key and profile == "QWEN":
            api_key = os.getenv("YANDEX_AI_STUDIO_API_KEY") or os.getenv("YANDEX_API_KEY")
        if not model and profile == "QWEN":
            model = os.getenv("YANDEX_AI_STUDIO_MODEL") or os.getenv("YANDEX_QWEN_MODEL")
        base_url = os.getenv("YANDEX_AI_STUDIO_BASE_URL", DEFAULT_BASE_URL)

        missing = [
            name
            for name, value in {
                f"YANDEX_AI_STUDIO_{profile}_API_KEY": api_key,
                f"YANDEX_AI_STUDIO_{profile}_MODEL": model,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Missing required environment variables: " + ", ".join(missing)
            )

        return cls(api_key=api_key, model=model, base_url=base_url.rstrip("/"))


class YandexAIStudioClient:
    """OpenAI-compatible Qwen client for Yandex AI Studio chat completions."""

    def __init__(
        self,
        config: YandexAIStudioConfig | None = None,
        *,
        profile: str = "QWEN",
    ) -> None:
        self.config = config or YandexAIStudioConfig.from_env(profile=profile)

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 512,
        timeout: int = 60,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format
        if tools:
            payload["tools"] = tools
        response = requests.post(
            f"{self.config.base_url}/chat/completions",
            headers={
                "Authorization": f"Api-Key {self.config.api_key}",
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

    def structured_chat(
        self,
        messages: list[dict[str, str]],
        *,
        schema: type[SchemaT],
        temperature: float = 0.0,
        max_tokens: int = 512,
        timeout: int = 60,
    ) -> SchemaT:
        """Request Qwen structured output and validate it as a Pydantic artifact."""

        schema_name = schema.__name__.lstrip("_")
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema.model_json_schema(),
                "strict": True,
            },
        }
        content = self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            response_format=response_format,
        )
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Structured Yandex AI Studio response was not valid JSON") from exc
        return schema.model_validate(payload)


def qwen_credential_gate(profile: str = "QWEN") -> dict[str, Any]:
    """Return explicit gated-skip evidence when Qwen credentials are unavailable."""

    load_dotenv(find_dotenv(usecwd=True))
    profile = profile.upper()
    api_key = (
        os.getenv(f"YANDEX_AI_STUDIO_{profile}_API_KEY")
        or os.getenv("YANDEX_AI_STUDIO_API_KEY")
        or os.getenv("YANDEX_API_KEY")
    )
    model = (
        os.getenv(f"YANDEX_AI_STUDIO_{profile}_MODEL")
        or os.getenv("YANDEX_AI_STUDIO_MODEL")
        or os.getenv("YANDEX_QWEN_MODEL")
    )
    missing = []
    if not api_key:
        missing.append(
            f"YANDEX_AI_STUDIO_{profile}_API_KEY or YANDEX_AI_STUDIO_API_KEY"
        )
    if not model:
        missing.append(f"YANDEX_AI_STUDIO_{profile}_MODEL or YANDEX_QWEN_MODEL")
    return {
        "profile": profile,
        "target_model_family": "Qwen",
        "base_url": DEFAULT_BASE_URL,
        "status": "ready" if not missing else "gated_skip",
        "missing_env_vars": missing,
        "verification_command": (
            'PATH="$PWD/.local/bin:$PATH" python -m app.llm.yandex_ai_studio'
        ),
    }


def smoke_prompt(profile: str = "QWEN") -> str:
    client = YandexAIStudioClient(profile=profile)
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


if __name__ == "__main__":
    gate = qwen_credential_gate()
    if gate["status"] == "gated_skip":
        print(json.dumps(gate, ensure_ascii=False, indent=2))
    else:
        print(smoke_prompt())
