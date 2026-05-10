from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MatchMode(str, Enum):
    """How a source candidate matched a user or agent search intent."""

    EXACT = "exact"
    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    PROXY = "proxy"
    CKAN_DISCOVERY = "ckan_discovery"
    METHODOLOGY_MATCH = "methodology_match"


class CoverageHint(BaseModel):
    """Compact coverage description before deterministic extraction runs."""

    start_period: str | None = None
    end_period: str | None = None
    periods: list[str] = Field(default_factory=list)
    frequency: str | None = None
    geography: list[str] = Field(default_factory=list)
    coverage_note: str | None = None

    model_config = ConfigDict(extra="forbid")


class AvailabilityFlags(BaseModel):
    """Availability facts gathered from local dumps or bounded APIs."""

    has_local_metadata: bool = False
    has_local_data: bool = False
    has_live_api: bool = False
    api_checked: bool = False
    resource_inspection_skipped: bool = False
    resource_inspection_truncated: bool = False

    model_config = ConfigDict(extra="forbid")


class QualityFlags(BaseModel):
    """Known quality and normalization risks for a candidate."""

    requires_normalization: bool = False
    incomplete_metadata: bool = False
    has_clean_jsonl: bool = False
    wide_parquet: bool = False
    aggregate_geography: bool = False
    proxy_indicator: bool = False
    methodology_risk: bool = False
    notes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class EmbeddingProviderTarget(BaseModel):
    """Embedding provider contract used by source-card metadata indexes."""

    provider: str = "yandex_ai_studio"
    document_model: str = "text-search-doc"
    query_model: str = "text-search-query"
    credential_env: list[str] = Field(
        default_factory=lambda: [
            "YANDEX_AI_STUDIO_API_KEY",
            "YANDEX_AI_STUDIO_EMBEDDINGS_MODEL",
        ]
    )
    fallback_when_credentials_absent: str = "skip_dense_index_and_record_lexical_only"

    model_config = ConfigDict(extra="forbid")


class EmbeddingIndexContract(BaseModel):
    """Boundary and storage expectations for later dense retrieval."""

    provider_target: EmbeddingProviderTarget = Field(default_factory=EmbeddingProviderTarget)
    input_format_version: str = "source-card-embedding-text-v1"
    metadata_version: str = "source-card-v1"
    index_boundary: str = "source_card_metadata_only"
    storage_interface: str = "vector_store_records"
    storage_required_fields: list[str] = Field(
        default_factory=lambda: [
            "source_id",
            "card_id",
            "chunk_id",
            "source_family",
            "language",
            "content_hash",
            "metadata_version",
            "embedding_text",
            "provenance_url",
        ]
    )
    excluded_content: list[str] = Field(
        default_factory=lambda: [
            "raw_parquet_values",
            "raw_numeric_observations",
            "generated_factual_answers",
            "llm_numeric_memory",
        ]
    )

    model_config = ConfigDict(extra="forbid")


class EmbeddingDocument(BaseModel):
    """Deterministic source-card chunk ready for document embedding."""

    source_id: str
    card_id: str
    chunk_id: str
    source_family: str
    language: str
    embedding_text: str
    text_hash: str
    content_hash: str
    metadata_version: str
    input_format_version: str
    provenance_url: str | None = None
    resource_url: str | None = None
    builder_source: str
    provider_target: EmbeddingProviderTarget = Field(default_factory=EmbeddingProviderTarget)
    index_boundary: str = "source_card_metadata_only"
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


SourceCardEmbeddingChunk = EmbeddingDocument


class EmbeddingCorpusManifest(BaseModel):
    """Durable manifest for generated source-card embedding documents."""

    artifact_path: str
    manifest_path: str
    chunk_count: int
    source_families: list[str] = Field(default_factory=list)
    content_hash: str
    chunk_hashes: dict[str, str] = Field(default_factory=dict)
    provider: str = "yandex_ai_studio"
    document_model: str = "text-search-doc"
    query_model: str = "text-search-query"
    metadata_version: str = "source-card-v1"
    input_format_version: str = "source-card-embedding-text-v1"
    provider_hints: dict[str, str] = Field(
        default_factory=lambda: {
            "document_model_env": "YANDEX_EMBEDDING_DOC_MODEL",
            "query_model_env": "YANDEX_EMBEDDING_QUERY_MODEL",
            "dimensions_env": "YANDEX_EMBEDDING_DIMENSIONS",
            "default_dimensions": "256",
        }
    )
    local_artifacts: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SourceCandidateCard(BaseModel):
    """Source-bound candidate metadata passed between scout and coverage steps."""

    source: str
    builder_source: str
    dataset_id: str
    resource_id: str | None = None
    title: str
    match_mode: MatchMode
    units: str | None = None
    geography: list[str] = Field(default_factory=list)
    period_coverage: CoverageHint = Field(default_factory=CoverageHint)
    provenance_url: str | None = None
    provenance_note: str | None = None
    local_paths: list[str] = Field(default_factory=list)
    api_endpoint: str | None = None
    availability: AvailabilityFlags = Field(default_factory=AvailabilityFlags)
    quality: QualityFlags = Field(default_factory=QualityFlags)
    dimensions: list[str] = Field(default_factory=list)
    frequency: str | None = None
    description: str | None = None
    why_matched: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: EmbeddingIndexContract = Field(default_factory=EmbeddingIndexContract)

    model_config = ConfigDict(extra="forbid")

    @property
    def card_id(self) -> str:
        resource_part = self.resource_id or "metadata"
        return f"{self.source}:{self.dataset_id}:{resource_part}"

    def to_embedding_chunk(self, *, language: str = "mixed") -> SourceCardEmbeddingChunk:
        embedding_text = self.to_embedding_text()
        content_hash = hashlib.sha256(embedding_text.encode("utf-8")).hexdigest()
        chunk_id = f"{self.card_id}:{self.embedding.metadata_version}:{content_hash[:16]}"
        return SourceCardEmbeddingChunk(
            source_id=self.dataset_id,
            card_id=self.card_id,
            chunk_id=chunk_id,
            source_family=self.source,
            language=language,
            embedding_text=embedding_text,
            text_hash=content_hash,
            content_hash=content_hash,
            metadata_version=self.embedding.metadata_version,
            input_format_version=self.embedding.input_format_version,
            provenance_url=self.provenance_url,
            resource_url=self._primary_resource_url(),
            builder_source=self.builder_source,
            provider_target=self.embedding.provider_target,
            index_boundary=self.embedding.index_boundary,
            metadata={
                "match_mode": self.match_mode.value,
                "availability": self.availability.model_dump(),
                "quality": self.quality.model_dump(),
            },
        )

    def to_embedding_text(self) -> str:
        """Build stable metadata-only text for document embeddings."""

        fields = [
            ("source_family", self.source),
            ("builder_source", self.builder_source),
            ("title", self.title),
            ("dataset_id", self.dataset_id),
            ("resource_id", self.resource_id),
            ("match_mode", self.match_mode.value),
            ("units", self.units),
            ("geography", "; ".join(self.geography)),
            ("period_start", self.period_coverage.start_period),
            ("period_end", self.period_coverage.end_period),
            ("periods", "; ".join(self.period_coverage.periods)),
            ("frequency", self.frequency or self.period_coverage.frequency),
            ("dimensions", "; ".join(self.dimensions)),
            ("provenance_url", self.provenance_url),
            ("api_endpoint", self.api_endpoint),
            ("description", self.description),
            ("why_matched", self.why_matched),
        ]
        lines = [f"{name}: {_bounded_embedding_value(str(value))}" for name, value in fields if value]
        for name, value in sorted(self.metadata.items()):
            if name in _NON_EMBEDDABLE_METADATA_KEYS:
                continue
            rendered = _render_embedding_metadata(value)
            if rendered:
                lines.append(f"metadata.{name}: {_bounded_embedding_value(rendered)}")
        embedding_text = "\n".join(lines)
        if len(embedding_text) <= _MAX_EMBEDDING_TEXT_CHARS:
            return embedding_text
        return (
            embedding_text[: _MAX_EMBEDDING_TEXT_CHARS - 25].rstrip()
            + "\ntruncated_for_embedding: true"
        )

    def _primary_resource_url(self) -> str | None:
        resources = self.metadata.get("resources")
        if isinstance(resources, list):
            for resource in resources:
                if isinstance(resource, dict):
                    url = resource.get("url")
                    if isinstance(url, str) and url.strip():
                        return url.strip()
        return self.provenance_url


class RejectedCandidate(BaseModel):
    """Candidate rejected before extraction, with traceable reason."""

    candidate: SourceCandidateCard
    reason_code: str
    reason: str
    rejected_by: str | None = None

    model_config = ConfigDict(extra="forbid")


class EvidenceBundle(BaseModel):
    """Candidate bundle for coverage and extraction planning, without answer text."""

    coverage_intent: str
    selected_candidates: list[SourceCandidateCard] = Field(default_factory=list)
    rejected_candidates: list[RejectedCandidate] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    builder_source: str | None = None
    source_query: str | None = None
    notes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


_NON_EMBEDDABLE_METADATA_KEYS = {
    "rows",
    "filesize",
    "resources_total",
    "resources_inspected",
    "country_count",
    "aggregate_count",
}

_MAX_EMBEDDING_TEXT_CHARS = 6000
_MAX_EMBEDDING_FIELD_CHARS = 1200


def _render_embedding_metadata(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return ""
    if isinstance(value, list):
        rendered_items = [_render_embedding_metadata(item) for item in value]
        return "; ".join(item for item in rendered_items if item)
    if isinstance(value, dict):
        rendered_pairs = []
        for key, nested_value in sorted(value.items()):
            rendered = _render_embedding_metadata(nested_value)
            if rendered:
                rendered_pairs.append(f"{key}={rendered}")
        return "; ".join(rendered_pairs)
    return str(value).strip()


def _bounded_embedding_value(value: str) -> str:
    value = " ".join(value.split())
    if len(value) <= _MAX_EMBEDDING_FIELD_CHARS:
        return value
    return value[: _MAX_EMBEDDING_FIELD_CHARS - 24].rstrip() + " [truncated_for_embedding]"
