from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from app.artifacts.source_cards import SourceCandidateCard


class SourceCatalog:
    """SQLite catalog for source_cards, embedding_chunks, and rejection metadata.

    The catalog is intentionally plain SQLite so DuckDB can attach or scan it later
    without changing the source-card contract.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def rebuild(self, cards: Iterable[SourceCandidateCard | dict[str, Any]]) -> None:
        parsed_cards = [
            card if isinstance(card, SourceCandidateCard) else SourceCandidateCard.model_validate(card)
            for card in cards
        ]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            self._create_schema(conn)
            self._clear(conn)
            for card in parsed_cards:
                self._insert_card(conn, card)
            conn.commit()

    def count_source_cards(self) -> int:
        return self._scalar("select count(*) from source_cards")

    def count_embedding_chunks(self) -> int:
        return self._scalar("select count(*) from embedding_chunks")

    def source_families(self) -> list[str]:
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                "select distinct source_family from source_cards order by source_family"
            ).fetchall()
        return [str(row[0]) for row in rows]

    def queryable(self) -> bool:
        try:
            self.count_source_cards()
            self.count_embedding_chunks()
            return True
        except sqlite3.Error:
            return False

    def table_counts(self) -> dict[str, int]:
        return {
            "source_cards": self.count_source_cards(),
            "embedding_chunks": self.count_embedding_chunks(),
            "coverage_hints": self._scalar("select count(*) from coverage_hints"),
            "rejection_metadata": self._scalar("select count(*) from rejection_metadata"),
        }

    def _scalar(self, query: str) -> int:
        conn = sqlite3.connect(self.path)
        try:
            row = conn.execute(query).fetchone()
        finally:
            conn.close()
        return int(row[0]) if row else 0

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            create table if not exists source_cards (
                card_id text primary key,
                source_family text not null,
                dataset_id text not null,
                resource_id text,
                title text not null,
                match_mode text not null,
                units text,
                provenance_url text,
                builder_source text not null,
                card_json text not null
            );

            create table if not exists coverage_hints (
                card_id text primary key,
                start_period text,
                end_period text,
                frequency text,
                geography_json text not null,
                coverage_note text,
                foreign key(card_id) references source_cards(card_id)
            );

            create table if not exists embedding_chunks (
                chunk_id text primary key,
                card_id text not null,
                source_id text not null,
                source_family text not null,
                language text not null,
                content_hash text not null,
                metadata_version text not null,
                embedding_text text not null,
                provenance_url text,
                resource_url text,
                chunk_json text not null,
                foreign key(card_id) references source_cards(card_id)
            );

            create table if not exists rejection_metadata (
                card_id text primary key,
                match_mode text not null,
                quality_json text not null,
                availability_json text not null,
                why_matched text not null,
                rejection_ready integer not null,
                foreign key(card_id) references source_cards(card_id)
            );
            """
        )

    def _clear(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            delete from rejection_metadata;
            delete from embedding_chunks;
            delete from coverage_hints;
            delete from source_cards;
            """
        )

    def _insert_card(self, conn: sqlite3.Connection, card: SourceCandidateCard) -> None:
        card_json = json.dumps(card.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        chunk = card.to_embedding_chunk()
        chunk_json = json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        coverage = card.period_coverage
        conn.execute(
            """
            insert into source_cards (
                card_id, source_family, dataset_id, resource_id, title, match_mode,
                units, provenance_url, builder_source, card_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card.card_id,
                card.source,
                card.dataset_id,
                card.resource_id,
                card.title,
                card.match_mode.value,
                card.units,
                card.provenance_url,
                card.builder_source,
                card_json,
            ),
        )
        conn.execute(
            """
            insert into coverage_hints (
                card_id, start_period, end_period, frequency, geography_json, coverage_note
            ) values (?, ?, ?, ?, ?, ?)
            """,
            (
                card.card_id,
                coverage.start_period,
                coverage.end_period,
                coverage.frequency,
                json.dumps(coverage.geography, ensure_ascii=False, sort_keys=True),
                coverage.coverage_note,
            ),
        )
        conn.execute(
            """
            insert into embedding_chunks (
                chunk_id, card_id, source_id, source_family, language, content_hash,
                metadata_version, embedding_text, provenance_url, resource_url, chunk_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk.chunk_id,
                chunk.card_id,
                chunk.source_id,
                chunk.source_family,
                chunk.language,
                chunk.content_hash,
                chunk.metadata_version,
                chunk.embedding_text,
                chunk.provenance_url,
                chunk.resource_url,
                chunk_json,
            ),
        )
        conn.execute(
            """
            insert into rejection_metadata (
                card_id, match_mode, quality_json, availability_json, why_matched, rejection_ready
            ) values (?, ?, ?, ?, ?, ?)
            """,
            (
                card.card_id,
                card.match_mode.value,
                json.dumps(card.quality.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
                json.dumps(card.availability.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
                card.why_matched,
                1,
            ),
        )
