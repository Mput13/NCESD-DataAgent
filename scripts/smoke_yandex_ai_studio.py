from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.yandex_ai_studio import smoke_prompt


if __name__ == "__main__":
    print(smoke_prompt())
