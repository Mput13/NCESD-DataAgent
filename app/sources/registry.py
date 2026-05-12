from __future__ import annotations

from app.config import Settings
from app.contracts import SourceAdapter
from app.sources.ckan import CkanAdapter
from app.sources.fedstat import FedStatAdapter
from app.sources.world_bank import WorldBankAdapter


def build_source_adapters(settings: Settings, *, include_network: bool = False) -> list[SourceAdapter]:
    adapters: list[SourceAdapter] = []
    if settings.fedstat_root and settings.fedstat_root.exists():
        adapters.append(FedStatAdapter(root=settings.fedstat_root))
    if settings.world_bank_root and settings.world_bank_root.exists():
        adapters.append(WorldBankAdapter(root=settings.world_bank_root))
    if include_network:
        adapters.append(CkanAdapter(base_url=settings.ckan_base_url, timeout_seconds=settings.request_timeout_seconds))
    return adapters
