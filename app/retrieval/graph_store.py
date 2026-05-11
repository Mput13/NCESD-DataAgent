"""
Knowledge graph store for Graph RAG.

Architecture:
  - Nodes: SourceCard, Indicator, Dataset, Provider, Unit, Geography, Period
  - Edges: MEASURES, IN_DATASET, PROVIDED_BY, HAS_UNIT, COVERS_GEO, COVERS_PERIOD,
           HAS_RESOURCE, SIMILAR_TO
  - Entity linking: dense retrieval results → graph nodes via card_id
  - Subgraph extraction: 1–2 hop neighbourhood from seed nodes
  - Graph-first lookup: deterministic concept/entity matching over source-card metadata
  - Graph expansion: neighbour traversal from dense-retrieval seed cards

The graph is built deterministically from source-card metadata at startup.
No golden labels and no separate graph database are required. Current graph-aware
retrieval reuses the source-card corpus/Qdrant collection for dense retrieval and
uses this SQLite graph for deterministic metadata traversal.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from app.retrieval.query_understanding import (
    concept_keys_for_text,
    concept_spec,
    normalize_query_value,
    parse_query_intent,
)

# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[\wА-Яа-яЁё]+", re.UNICODE)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_CODE_RE = re.compile(r"\b[A-Za-z]{1,8}(?:[._-][A-Za-z0-9]{1,12}){1,8}\b|\b\d{4,8}\b")

_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "as", "by", "data", "dataset", "find", "for",
        "from", "in", "of", "on", "or", "show", "source", "the", "to", "with",
        "а", "в", "во", "год", "году", "данные", "дай", "для", "за", "и", "или",
        "источник", "источники", "как", "какой", "найди", "о", "об", "по",
        "покажи", "про", "с", "со", "что",
    }
)

# Synonym expansion: maps a token → set of equivalent tokens.
# Used both when building node text representations and when parsing queries.
_SYNONYMS: dict[str, list[str]] = {
    "ввп": ["gdp", "валовой", "внутренний", "продукт"],
    "gdp": ["ввп"],
    "инфляция": ["cpi", "inflation", "ипц"],
    "ипц": ["cpi", "inflation", "инфляция"],
    "cpi": ["ипц", "инфляция"],
    "inflation": ["ипц", "инфляция"],
}


def _tokenize(text: str, *, expand_synonyms: bool = True) -> list[str]:
    raw = [t.casefold() for t in _TOKEN_RE.findall(text)]
    out: list[str] = []
    for token in raw:
        if token in _STOPWORDS or token.isdigit() or len(token) <= 1:
            continue
        out.append(token)
        if expand_synonyms:
            out.extend(_SYNONYMS.get(token, []))
    return out


def _normalize_id(value: str) -> str:
    s = value.strip().casefold()
    s = re.sub(r"^https?://", "", s)
    s = s.replace("www.", "")
    s = re.sub(r"\.(?:parquet|csv|json|jsonl|xlsx?)$", "", s)
    s = re.sub(r"[/\\._\-]+", ".", s)
    s = re.sub(r"[^a-z0-9а-яё.]+", ".", s)
    s = re.sub(r"\.+", ".", s).strip(".")
    return s


def _extract_codes(text: str) -> set[str]:
    return {_normalize_id(m) for m in _CODE_RE.findall(text) if len(m) > 1}


def _parse_year(value: str | None) -> int | None:
    if not value:
        return None
    m = _YEAR_RE.search(value)
    return int(m.group(0)) if m else None


def _parse_fields(embedding_text: str) -> dict[str, str]:
    """Parse ``key: value`` structured fields from an embedding_text blob."""
    fields: dict[str, str] = {}
    current: str | None = None
    for raw in embedding_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            k_norm = k.strip().casefold()
            if k_norm and re.fullmatch(r"[a-zA-Z_][\w_]*", k_norm):
                current = k_norm
                fields[current] = v.strip()
                continue
        if current:
            fields[current] = f"{fields[current]} {line}".strip()
    return fields


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

NODE_TYPES = frozenset(
    {
        "SourceCard",
        "Indicator",
        "Dataset",
        "Provider",
        "Unit",
        "Geography",
        "Period",
        "Resource",
        "Concept",
        "Alias",
    }
)

EDGE_TYPES = frozenset(
    {
        "MEASURES",       # SourceCard → Indicator
        "IN_DATASET",     # SourceCard → Dataset
        "PROVIDED_BY",    # SourceCard → Provider
        "HAS_UNIT",       # SourceCard → Unit
        "COVERS_GEO",     # SourceCard → Geography
        "COVERS_PERIOD",  # SourceCard → Period
        "HAS_RESOURCE",   # SourceCard → Resource
        "ALIAS_OF",       # Alias → Concept
        "MENTIONED_IN",   # Concept → SourceCard
        "MEASURED_BY",    # Concept → Indicator
        "SIMILAR_TO",     # SourceCard ↔ SourceCard (cross-source semantic edge)
    }
)


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    node_type: str
    name: str
    card_id: str          # which SourceCard this node belongs to (empty for shared nodes)
    properties: dict[str, Any] = field(default_factory=dict)

    def text_for_embedding(self) -> str:
        """Canonical text representation used when embedding this node."""
        parts = [f"type: {self.node_type}", f"name: {self.name}"]
        for k in ("title", "source_family", "units", "geography", "period_start", "period_end"):
            v = self.properties.get(k)
            if v:
                parts.append(f"{k}: {v}")
        return "\n".join(parts)


@dataclass(frozen=True)
class GraphEdge:
    src: str
    dst: str
    edge_type: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class SubgraphContext:
    """Result of a subgraph extraction query — what gets passed upstream to LLM/reranker."""
    seed_card_ids: list[str]
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    neighbour_card_ids: list[str]   # card_ids reachable within hop limit

    def as_text(self) -> str:
        """Serialise to a compact text block suitable for LLM context."""
        lines: list[str] = []
        for node in self.nodes:
            props = ", ".join(f"{k}={v}" for k, v in node.properties.items() if v)
            lines.append(f"[{node.node_type}] {node.name} ({props})")
        for edge in self.edges:
            lines.append(f"  {edge.src} --{edge.edge_type}--> {edge.dst}")
        return "\n".join(lines)

    def neighbour_card_ids_ranked(self) -> list[str]:
        """Deduplicated neighbour card_ids preserving encounter order."""
        seen: set[str] = set()
        result: list[str] = []
        for cid in self.seed_card_ids + self.neighbour_card_ids:
            if cid not in seen:
                seen.add(cid)
                result.append(cid)
        return result


# ---------------------------------------------------------------------------
# Core graph store (SQLite-backed, built from source-card metadata)
# ---------------------------------------------------------------------------

class KnowledgeGraphStore:
    """
    SQLite property graph built from source-card metadata at startup.

    Responsibilities:
      1. Ingesting source cards → nodes + edges
      2. entity_link(card_ids) → seed GraphNodes
      3. expand_subgraph(seed_node_ids, hops) → SubgraphContext
      4. Providing canonical text for each node if later offline graph embedding is added
    """

    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._create_schema()
        self._ingest(documents)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def entity_link(self, card_ids: list[str]) -> list[GraphNode]:
        """Return SourceCard nodes for a list of card_ids (entity linking step)."""
        if not card_ids:
            return []
        placeholders = ",".join("?" * len(card_ids))
        rows = self._conn.execute(
            f"SELECT node_id, node_type, name, card_id, properties_json "
            f"FROM nodes WHERE card_id IN ({placeholders}) AND node_type = 'SourceCard'",
            card_ids,
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def graph_first_card_ids(self, query: str, *, limit: int = 50) -> list[str]:
        """Return SourceCard ids directly from deterministic query concepts."""
        intent = parse_query_intent(query)
        if not intent.has_graph_entry:
            return []

        scores: dict[str, float] = {}
        if intent.concepts:
            concept_ids = [f"concept:{key}" for key in intent.concepts]
            for batch in _batched(concept_ids, 400):
                ph = ",".join("?" * len(batch))
                rows = self._conn.execute(
                    f"""
                    SELECT n.card_id
                    FROM edges e
                    JOIN nodes n ON n.node_id = e.dst_node_id
                    WHERE e.src_node_id IN ({ph})
                      AND e.edge_type = 'MENTIONED_IN'
                      AND n.node_type = 'SourceCard'
                    """,
                    batch,
                ).fetchall()
                for row in rows:
                    cid = str(row["card_id"])
                    scores[cid] = scores.get(cid, 0.0) + 4.0

        if not scores and (intent.geographies or intent.years or intent.source_families):
            for row in self._conn.execute(
                "SELECT card_id, properties_json FROM nodes WHERE node_type = 'SourceCard'"
            ).fetchall():
                score = self._query_filter_score(json.loads(row["properties_json"]), intent)
                if score > 0:
                    scores[str(row["card_id"])] = score

        for cid in list(scores):
            row = self._conn.execute(
                "SELECT properties_json FROM nodes WHERE node_type = 'SourceCard' AND card_id = ?",
                (cid,),
            ).fetchone()
            if row is not None:
                scores[cid] += self._query_filter_score(json.loads(row["properties_json"]), intent)

        return [
            cid
            for cid, _score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
        ]

    def expand_subgraph(self, seed_node_ids: list[str], *, hops: int = 2) -> SubgraphContext:
        """
        Traverse the graph up to `hops` hops from seed nodes.
        Uses batched SQLite queries to stay within the 999-variable limit.
        """
        if not seed_node_ids:
            return SubgraphContext([], [], [], [])

        visited_nodes: set[str] = set(seed_node_ids)
        frontier: set[str] = set(seed_node_ids)
        all_edges: list[GraphEdge] = []

        for _ in range(hops):
            if not frontier:
                break
            edge_rows: list[sqlite3.Row] = []
            for batch in _batched(list(frontier), 400):
                ph = ",".join("?" * len(batch))
                edge_rows += self._conn.execute(
                    f"SELECT src_node_id, dst_node_id, edge_type, properties_json "
                    f"FROM edges WHERE src_node_id IN ({ph}) OR dst_node_id IN ({ph})",
                    batch * 2,
                ).fetchall()
            new_frontier: set[str] = set()
            for row in edge_rows:
                src, dst, etype, props_json = (
                    row["src_node_id"], row["dst_node_id"],
                    row["edge_type"], row["properties_json"],
                )
                if self._is_noisy_bridge(src, dst, etype):
                    continue
                all_edges.append(GraphEdge(src, dst, etype, json.loads(props_json)))
                for nid in (src, dst):
                    if nid not in visited_nodes:
                        visited_nodes.add(nid)
                        new_frontier.add(nid)
            frontier = new_frontier

        node_rows: list[sqlite3.Row] = []
        for batch in _batched(list(visited_nodes), 900):
            ph = ",".join("?" * len(batch))
            node_rows += self._conn.execute(
                f"SELECT node_id, node_type, name, card_id, properties_json FROM nodes "
                f"WHERE node_id IN ({ph})",
                batch,
            ).fetchall()

        seed_set = set(seed_node_ids)
        nodes = [self._row_to_node(r) for r in node_rows]
        neighbour_card_ids = [
            n.card_id for n in nodes
            if n.node_type == "SourceCard" and n.node_id not in seed_set and n.card_id
        ]
        seed_card_ids = [
            n.card_id for n in nodes
            if n.node_type == "SourceCard" and n.node_id in seed_set and n.card_id
        ]
        return SubgraphContext(
            seed_card_ids=seed_card_ids,
            nodes=nodes,
            edges=all_edges,
            neighbour_card_ids=neighbour_card_ids,
        )

    def _query_filter_score(self, properties: dict[str, Any], intent: Any) -> float:
        score = 0.0
        source_family = str(properties.get("source_family") or "").casefold().replace(" ", "_")
        title = str(properties.get("title") or "").casefold()
        geography = str(properties.get("geography") or "").casefold()
        text = f"{title} {geography}"
        normalized_text = normalize_query_value(text)
        source_geo_keys = set(parse_query_intent(text).geographies)
        if intent.source_families and source_family in set(intent.source_families):
            score += 1.0
        if intent.geographies and (
            set(intent.geographies).intersection(source_geo_keys)
            or any(geo in normalized_text for geo in intent.geographies)
        ):
            score += 0.5
        start = properties.get("period_start")
        end = properties.get("period_end")
        if intent.years and isinstance(start, int) and isinstance(end, int):
            if any(start <= year <= end for year in intent.years):
                score += 0.75
        return score

    def _is_noisy_bridge(self, src: str, dst: str, edge_type: str) -> bool:
        """Prevent broad period/geography/unit nodes from flooding 2-hop expansion."""
        weak_edges = {"COVERS_GEO", "COVERS_PERIOD", "HAS_UNIT", "PROVIDED_BY"}
        if edge_type not in weak_edges:
            return False
        bridge = dst if src.startswith("card:") else src
        degree = self._conn.execute(
            "SELECT COUNT(*) FROM edges WHERE src_node_id = ? OR dst_node_id = ?",
            (bridge, bridge),
        ).fetchone()[0]
        return int(degree) > 50

    def all_nodes_for_embedding(self) -> list[GraphNode]:
        """Return all SourceCard nodes — used for offline graph embedding population."""
        rows = self._conn.execute(
            "SELECT node_id, node_type, name, card_id, properties_json "
            "FROM nodes WHERE node_type = 'SourceCard'"
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def add_similar_to_edges(self, pairs: list[tuple[str, str]]) -> None:
        """
        Add SIMILAR_TO edges between pairs of node_ids.
        Called after offline similarity computation (e.g. graph embedding ANN).
        """
        for src, dst in pairs:
            self._insert_edge(src, dst, "SIMILAR_TO", {})
            self._insert_edge(dst, src, "SIMILAR_TO", {})
        self._conn.commit()

    def node_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]

    def edge_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _create_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE nodes (
                node_id       TEXT PRIMARY KEY,
                node_type     TEXT NOT NULL,
                name          TEXT NOT NULL,
                card_id       TEXT NOT NULL DEFAULT '',
                properties_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX nodes_card_idx ON nodes(card_id);
            CREATE INDEX nodes_type_idx ON nodes(node_type);

            CREATE TABLE edges (
                src_node_id  TEXT NOT NULL,
                dst_node_id  TEXT NOT NULL,
                edge_type    TEXT NOT NULL,
                properties_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (src_node_id, dst_node_id, edge_type)
            );
            CREATE INDEX edges_src_idx ON edges(src_node_id);
            CREATE INDEX edges_dst_idx ON edges(dst_node_id);
        """)

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def _ingest(self, documents: list[dict[str, Any]]) -> None:
        for doc in documents:
            self._ingest_document(doc)
        self._conn.commit()

    def _ingest_document(self, doc: dict[str, Any]) -> None:
        fields = _parse_fields(str(doc.get("embedding_text") or ""))
        card_id = str(doc.get("card_id") or "")
        if not card_id:
            return

        title = (
            fields.get("title")
            or str(doc.get("title") or "")
            or card_id
        )
        source_family = str(doc.get("source_family") or fields.get("source_family") or "")
        period_start = _parse_year(fields.get("period_start"))
        period_end = _parse_year(fields.get("period_end"))
        readiness = _extraction_readiness(doc, fields)

        card_node_id = f"card:{card_id}"
        self._insert_node(
            card_node_id, "SourceCard", title, card_id,
            {
                "card_id": card_id,
                "chunk_id": str(doc.get("chunk_id") or ""),
                "source_family": source_family,
                "title": title,
                "geography": fields.get("geography") or "",
                "period_start": period_start,
                "period_end": period_end,
                "provenance_url": str(doc.get("provenance_url") or ""),
                "resource_url": str(doc.get("resource_url") or ""),
                "readiness_status": readiness["status"],
            },
        )

        concept_text = "\n".join(
            str(value)
            for value in (
                title,
                fields.get("description"),
                fields.get("why_matched"),
                fields.get("indicator_code"),
                fields.get("dataset_id"),
                doc.get("source_id"),
            )
            if value
        )
        for concept_key in concept_keys_for_text(concept_text):
            self._insert_concept_edges(card_node_id, concept_key)

        # Provider
        if source_family:
            prov_id = f"provider:{_normalize_id(source_family)}"
            self._insert_node(prov_id, "Provider", source_family, "", {})
            self._insert_edge(card_node_id, prov_id, "PROVIDED_BY", {})

        # Indicator
        indicator = _first(
            fields.get("indicator_code"),
            fields.get("dataset_id"),
            doc.get("source_id"),
        )
        if indicator:
            ind_key = _normalize_id(str(indicator))
            ind_id = f"indicator:{ind_key}"
            self._insert_node(
                ind_id, "Indicator", str(indicator), "",
                {"title": title, "source_family": source_family},
            )
            self._insert_edge(card_node_id, ind_id, "MEASURES", {})
            for concept_key in concept_keys_for_text(str(indicator)):
                self._insert_edge(
                    f"concept:{concept_key}",
                    ind_id,
                    "MEASURED_BY",
                    {"weight": 1.0},
                )

        # Dataset
        dataset = _first(fields.get("dataset_id"), doc.get("source_id"))
        if dataset:
            ds_key = _normalize_id(str(dataset))
            ds_id = f"dataset:{ds_key}"
            self._insert_node(ds_id, "Dataset", str(dataset), "", {})
            self._insert_edge(card_node_id, ds_id, "IN_DATASET", {})

        # Resource
        resource = _first(
            fields.get("resource_id"),
            doc.get("resource_url"),
            doc.get("provenance_url"),
        )
        if resource:
            res_key = _normalize_id(str(resource))
            res_id = f"resource:{res_key}"
            self._insert_node(res_id, "Resource", str(resource)[:200], "", readiness)
            self._insert_edge(card_node_id, res_id, "HAS_RESOURCE", readiness)

        # Unit
        if fields.get("units"):
            unit_key = _normalize_id(fields["units"][:100])
            unit_id = f"unit:{unit_key}"
            self._insert_node(unit_id, "Unit", fields["units"][:100], "", {})
            self._insert_edge(card_node_id, unit_id, "HAS_UNIT", {})

        # Geography
        if fields.get("geography"):
            geo_key = _normalize_id(fields["geography"][:100])
            geo_id = f"geography:{geo_key}"
            self._insert_node(geo_id, "Geography", fields["geography"][:100], "", {})
            self._insert_edge(card_node_id, geo_id, "COVERS_GEO", {})

        # Period
        if period_start or period_end:
            period_name = f"{period_start or '?'}-{period_end or '?'}"
            period_id = f"period:{period_name}"
            self._insert_node(
                period_id, "Period", period_name, "",
                {"period_start": period_start, "period_end": period_end},
            )
            self._insert_edge(card_node_id, period_id, "COVERS_PERIOD", {})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _insert_node(
        self,
        node_id: str,
        node_type: str,
        name: str,
        card_id: str,
        properties: dict[str, Any],
    ) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO nodes (node_id, node_type, name, card_id, properties_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (node_id, node_type, name, card_id, json.dumps(properties, ensure_ascii=False)),
        )

    def _insert_edge(
        self,
        src: str,
        dst: str,
        edge_type: str,
        properties: dict[str, Any],
    ) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO edges (src_node_id, dst_node_id, edge_type, properties_json) "
            "VALUES (?, ?, ?, ?)",
            (src, dst, edge_type, json.dumps(properties, ensure_ascii=False)),
        )

    def _insert_concept_edges(self, card_node_id: str, concept_key: str) -> None:
        spec = concept_spec(concept_key)
        if spec is None:
            return
        concept_id = f"concept:{spec.key}"
        self._insert_node(
            concept_id,
            "Concept",
            spec.label,
            "",
            {"concept_key": spec.key, "aliases": list(spec.aliases)},
        )
        self._insert_edge(concept_id, card_node_id, "MENTIONED_IN", {"weight": 1.0})
        for alias in spec.aliases:
            alias_id = f"alias:{_normalize_id(alias)}"
            self._insert_node(alias_id, "Alias", alias, "", {"concept_key": spec.key})
            self._insert_edge(alias_id, concept_id, "ALIAS_OF", {"weight": 1.0})

    @staticmethod
    def _row_to_node(row: sqlite3.Row) -> GraphNode:
        return GraphNode(
            node_id=row["node_id"],
            node_type=row["node_type"],
            name=row["name"],
            card_id=row["card_id"],
            properties=json.loads(row["properties_json"]),
        )


# ---------------------------------------------------------------------------
# Utilities shared with other modules
# ---------------------------------------------------------------------------

def extract_canonical_ids(document: dict[str, Any]) -> set[str]:
    """Extract all normalised identifier strings from a source-card document."""
    fields = _parse_fields(str(document.get("embedding_text") or ""))
    values = [
        document.get("card_id"),
        document.get("chunk_id"),
        document.get("source_id"),
        fields.get("dataset_id"),
        fields.get("indicator_code"),
        fields.get("resource_id"),
        document.get("provenance_url"),
        document.get("resource_url"),
    ]
    identifiers: set[str] = set()
    for v in values:
        if not v:
            continue
        s = str(v)
        identifiers.add(_normalize_id(s))
        for part in re.split(r"[:/\\]", s):
            p = _normalize_id(part)
            if p:
                identifiers.add(p)
    return {i for i in identifiers if len(i) > 1}


def extraction_readiness(document: dict[str, Any]) -> dict[str, Any]:
    fields = _parse_fields(str(document.get("embedding_text") or ""))
    return _extraction_readiness(document, fields)


def _extraction_readiness(document: dict[str, Any], fields: dict[str, str]) -> dict[str, Any]:
    metadata = document.get("metadata") or {}
    availability = metadata.get("availability") or {}
    has_local = bool(availability.get("has_local_data"))
    has_api = bool(availability.get("has_live_api"))
    has_resource = bool(fields.get("resource_id") or document.get("resource_url"))
    has_provenance = bool(fields.get("provenance_url") or document.get("provenance_url"))

    flags: list[str] = []
    if has_local:
        flags.append("has_local_data")
    if has_api:
        flags.append("has_live_api")
    if has_resource:
        flags.append("has_resource_id")
    if has_provenance:
        flags.append("has_provenance")
    if not flags:
        flags.append("metadata_only")

    if has_local or has_api:
        status = "ready"
    elif has_resource and has_provenance:
        status = "candidate"
    else:
        status = "metadata_only"
    return {"status": status, "flags": flags}


# Kept for backward compat with evaluate_retrieval_modes.py
def normalize_identifier(value: str) -> str:
    return _normalize_id(value)


def _first(*values: Any) -> Any:
    for v in values:
        if v is not None and str(v).strip():
            return v
    return None


def _batched(items: list, size: int) -> list[list]:
    """Split list into chunks of at most `size` items."""
    return [items[i : i + size] for i in range(0, len(items), size)]
