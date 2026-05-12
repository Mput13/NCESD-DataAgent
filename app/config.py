from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Settings(BaseModel):
    fedstat_root: Path | None = None
    world_bank_root: Path | None = None
    ckan_base_url: str = "https://repository.nsedc.ru/api/3/action"
    artifact_root: Path = Path(".local/artifacts")
    max_candidates_per_source: int = Field(default=5, ge=1, le=50)
    request_timeout_seconds: int = Field(default=20, ge=1, le=120)


def load_settings() -> Settings:
    load_dotenv(override=False)
    return Settings(
        fedstat_root=_optional_path("FEDSTAT_ROOT"),
        world_bank_root=_optional_path("WORLD_BANK_ROOT"),
        ckan_base_url=os.getenv("CKAN_BASE_URL", "https://repository.nsedc.ru/api/3/action"),
        artifact_root=Path(os.getenv("ARTIFACT_ROOT", ".local/artifacts")),
        max_candidates_per_source=int(os.getenv("MAX_CANDIDATES_PER_SOURCE", "5")),
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
    )


def _optional_path(name: str) -> Path | None:
    raw = os.getenv(name)
    return Path(raw) if raw else None

