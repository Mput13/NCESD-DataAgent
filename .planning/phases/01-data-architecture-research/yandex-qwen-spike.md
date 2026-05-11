# Yandex/Qwen AI Studio Spike

## Target

Phase 1 targets Qwen through the Yandex AI Studio OpenAI-compatible Chat Completions API:

- Base URL: `https://llm.api.cloud.yandex.net/v1`
- Chat endpoint: `https://llm.api.cloud.yandex.net/v1/chat/completions`
- Auth header: `Authorization: Api-Key <key>`
- Target model family: Qwen
- Expected model URI shape: `gpt://<folder_id>/qwen3/latest`

DeepSeek historical fallback only: DeepSeek 3.2 remains documented as the earlier smoke-test model, but it is not the default Phase 1 target.

## Environment

Required for a live Qwen smoke test:

- `YANDEX_AI_STUDIO_QWEN_API_KEY` or `YANDEX_AI_STUDIO_API_KEY`
- `YANDEX_AI_STUDIO_QWEN_MODEL` or `YANDEX_QWEN_MODEL`
- Optional: `YANDEX_AI_STUDIO_BASE_URL=https://llm.api.cloud.yandex.net/v1`

The folder id inside the model URI must match the service account folder id. Secrets stay in `.env` or the shell environment and are not committed.

## Structured-output Check

`app/llm/yandex_ai_studio.py` exposes `YandexAIStudioClient.structured_chat(...)`, which sends `response_format={"type": "json_schema", ...}` and validates the returned JSON into a Pydantic artifact. This is the structured-output path for the intended first structured artifact: an intent frame or related workflow artifact. Numeric values are still prohibited unless produced by deterministic tools.

Local unit verification covers request construction without requiring credentials:

```bash
PATH="$PWD/.local/bin:$PATH" python3 -m pytest tests/test_yandex_ai_studio.py
```

## Tool-call Readiness

The client supports passing OpenAI-compatible `tools` payloads through `chat(...)`. Tool execution remains owned by the local deterministic layer; Qwen may select tool plans, but tools extract numbers and build artifacts.

## Credential Gate

Current local status: `gated_skip` unless both a Qwen API key and Qwen model URI are present in the environment.

The explicit gate check is:

```bash
PATH="$PWD/.local/bin:$PATH" python -m app.llm.yandex_ai_studio
```

Expected gated evidence when credentials are absent:

```json
{
  "profile": "QWEN",
  "target_model_family": "Qwen",
  "base_url": "https://llm.api.cloud.yandex.net/v1",
  "status": "gated_skip",
  "missing_env_vars": [
    "YANDEX_AI_STUDIO_QWEN_API_KEY or YANDEX_AI_STUDIO_API_KEY",
    "YANDEX_AI_STUDIO_QWEN_MODEL or YANDEX_QWEN_MODEL"
  ]
}
```

When credentials are available, the same command runs a short Qwen smoke prompt through AI Studio rather than pretending a gated call succeeded.
