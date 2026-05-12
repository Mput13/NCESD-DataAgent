from __future__ import annotations

import csv
from pathlib import Path

from app.contracts import (
    CoverageReport,
    IntentFrame,
    MatchMode,
    SourceAdapter,
    SourceCandidate,
    SourceFamily,
)
from app.sources.base import lexical_score, read_jsonl


class FedStatAdapter(SourceAdapter):
    family: SourceFamily = SourceFamily.FEDSTAT
    root: Path

    def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]:
        metadata_path = self.root / "metadata.jsonl"
        indicators_path = self.root / "indicators.csv"
        candidates: list[tuple[int, SourceCandidate]] = []

        if metadata_path.exists():
            for item in read_jsonl(metadata_path):
                code = str(item.get("code") or item.get("id") or "").strip()
                title = str(item.get("name") or item.get("title") or code).strip()
                score = lexical_score(query, [code, title, str(item)])
                if score <= 0 or not code or not title:
                    continue
                candidates.append((score, self._candidate(code=code, title=title, why=f"metadata lexical score={score}")))

        if not candidates and indicators_path.exists():
            with indicators_path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    code = str(row.get("code") or "").strip()
                    if not code:
                        continue
                    score = lexical_score(query, [code])
                    if score > 0:
                        candidates.append((score, self._candidate(code=code, title=code, why=f"indicator lexical score={score}")))

        candidates.sort(key=lambda item: item[0], reverse=True)
        return [candidate for _, candidate in candidates[:limit]]

    def coverage(self, candidate: SourceCandidate, intent: IntentFrame) -> CoverageReport:
        parquet_path = self.root / "parquet" / f"{candidate.indicator_id}.parquet"
        clean_path = self.root / "clean_jsonl" / f"{candidate.indicator_id}.jsonl.gz"
        if parquet_path.exists() or clean_path.exists():
            return CoverageReport(
                candidate=candidate,
                status="unknown",
                warnings=["coverage inspection is not implemented yet; source file exists"],
            )
        return CoverageReport(
            candidate=candidate,
            status="not_enough",
            missing_requirements=["source data file"],
            warnings=["candidate metadata exists but no local data file was found"],
        )

    def _candidate(self, *, code: str, title: str, why: str) -> SourceCandidate:
        parquet_path = self.root / "parquet" / f"{code}.parquet"
        local_path = parquet_path if parquet_path.exists() else None
        return SourceCandidate(
            source_id=f"fedstat:{code}",
            source_family=SourceFamily.FEDSTAT,
            title=title,
            indicator_id=code,
            indicator_name=title,
            local_path=local_path,
            match_mode=MatchMode.LEXICAL,
            why_matched=why,
        )

