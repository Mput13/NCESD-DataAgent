# Yandex AI Studio LLM setup

The project reads Yandex AI Studio credentials from a local `.env` file.
Do not commit `.env`.

```powershell
Copy-Item .env.example .env
```

Fill these variables:

```text
YANDEX_AI_STUDIO_BASE_URL=https://ai.api.cloud.yandex.net/v1

YANDEX_AI_STUDIO_QWEN_API_KEY=...
YANDEX_AI_STUDIO_QWEN_MODEL=gpt://<folder_id>/qwen3.6-35b-a3b/latest

YANDEX_AI_STUDIO_DEEPSEEK_API_KEY=...
YANDEX_AI_STUDIO_DEEPSEEK_MODEL=gpt://<folder_id>/deepseek-v32/latest
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run a smoke test:

```powershell
python scripts\smoke_yandex_ai_studio.py QWEN
python scripts\smoke_yandex_ai_studio.py DEEPSEEK
```

Expected result: a short Russian sentence confirming that the model connection works.
