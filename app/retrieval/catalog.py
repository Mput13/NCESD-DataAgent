from __future__ import annotations

from app.contracts import SourceAdapter, SourceCandidate


class SourceCatalog:
    def __init__(self, adapters: list[SourceAdapter]) -> None:
        self._adapters = adapters

    @property
    def adapter_count(self) -> int:
        return len(self._adapters)

    def search(self, query: str, *, limit_per_source: int = 5) -> list[SourceCandidate]:
        candidates: list[SourceCandidate] = []
        for adapter in self._adapters:
            candidates.extend(adapter.search(query, limit=limit_per_source))
        return _deduplicate(candidates)


def _deduplicate(candidates: list[SourceCandidate]) -> list[SourceCandidate]:
    seen: set[str] = set()
    unique: list[SourceCandidate] = []
    for candidate in candidates:
        if candidate.source_id in seen:
            continue
        seen.add(candidate.source_id)
        unique.append(candidate)
    return unique

