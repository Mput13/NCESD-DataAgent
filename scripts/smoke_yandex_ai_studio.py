from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.yandex_ai_studio import smoke_prompt


if __name__ == "__main__":
    profile = sys.argv[1] if len(sys.argv) > 1 else "QWEN"
    print(smoke_prompt(profile=profile))
