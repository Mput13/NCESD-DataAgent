from __future__ import annotations

from typing import Any

import requests

from app.contracts import (
    CoverageReport,
    IntentFrame,
    MatchMode,
    SourceAdapter,
    SourceCandidate,
    SourceFamily,
)


class CkanAdapter(SourceAdapter):
    family: SourceFamily = SourceFamily.CKAN
    base_url: str
    timeout_seconds: int = 20

    def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]:
        response = requests.get(
            f"{self.base_url.rstrip('/')}/package_search",
            params={"q": query, "rows": limit},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("result", {}).get("results", [])
        if not isinstance(results, list):
            return []

        candidates: list[SourceCandidate] = []
        for item in results[:limit]:
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("id") or item.get("name") or "").strip()
            title = str(item.get("title") or item.get("name") or source_id).strip()
            if not source_id or not title:
                continue
            candidates.append(
                SourceCandidate(
                    source_id=f"ckan:{source_id}",
                    source_family=SourceFamily.CKAN,
                    title=title,
                    provenance_url=_url(item),
                    match_mode=MatchMode.CKAN_DISCOVERY,
                    why_matched="CKAN package_search returned this package",
                    limitations=["CKAN candidate requires package_show/resource validation before extraction"],
                )
            )
        return candidates

    def coverage(self, candidate: SourceCandidate, intent: IntentFrame) -> CoverageReport:
        return CoverageReport(
            candidate=candidate,
            status="unknown",
            warnings=["CKAN resource coverage validation is not implemented yet"],
        )


def _url(item: dict[str, Any]) -> str | None:
    raw = item.get("url")
    return str(raw) if raw else None

