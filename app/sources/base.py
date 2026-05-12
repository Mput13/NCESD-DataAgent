from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def tokenize(text: str) -> set[str]:
    return {part.lower() for part in text.replace("_", " ").replace("-", " ").split() if len(part) > 2}


def lexical_score(query: str, fields: Iterable[str | None]) -> int:
    query_tokens = tokenize(query)
    haystack = tokenize(" ".join(field or "" for field in fields))
    return len(query_tokens & haystack)


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                payload = json.loads(line)
                if isinstance(payload, dict):
                    yield payload

