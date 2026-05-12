from __future__ import annotations

import json
from pathlib import Path

from app.contracts import (
    CoverageReport,
    IntentFrame,
    MatchMode,
    SourceAdapter,
    SourceCandidate,
    SourceFamily,
)
from app.sources.base import lexical_score


class WorldBankAdapter(SourceAdapter):
    family: SourceFamily = SourceFamily.WORLD_BANK
    root: Path

    def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]:
        indicators_path = self.root / "indicators.json"
        if not indicators_path.exists():
            return []

        payload = json.loads(indicators_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return []

        candidates: list[tuple[int, SourceCandidate]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            indicator_id = str(item.get("id") or "").strip()
            title = str(item.get("name") or indicator_id).strip()
            fields = [indicator_id, title, item.get("unit"), item.get("sourceNote"), json.dumps(item, ensure_ascii=False)]
            score = lexical_score(query, fields)
            if score <= 0 or not indicator_id:
                continue
            path = self.root / "parquet" / f"{indicator_id}.parquet"
            candidates.append(
                (
                    score,
                    SourceCandidate(
                        source_id=f"world_bank:{indicator_id}",
                        source_family=SourceFamily.WORLD_BANK,
                        title=title,
                        indicator_id=indicator_id,
                        indicator_name=title,
                        unit=item.get("unit") or None,
                        local_path=path if path.exists() else None,
                        match_mode=MatchMode.LEXICAL,
                        why_matched=f"indicator metadata lexical score={score}",
                    ),
                )
            )

        candidates.sort(key=lambda item: item[0], reverse=True)
        return [candidate for _, candidate in candidates[:limit]]

    def coverage(self, candidate: SourceCandidate, intent: IntentFrame) -> CoverageReport:
        if candidate.local_path and candidate.local_path.exists():
            return CoverageReport(
                candidate=candidate,
                status="unknown",
                warnings=["coverage inspection is not implemented yet; source file exists"],
            )
        return CoverageReport(
            candidate=candidate,
            status="not_enough",
            missing_requirements=["source parquet file"],
            warnings=["candidate metadata exists but no local parquet file was found"],
        )

