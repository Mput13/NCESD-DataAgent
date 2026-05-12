from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write_json(self, run_id: str, name: str, payload: BaseModel | dict) -> Path:
        run_dir = self.root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / name
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

