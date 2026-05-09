from __future__ import annotations

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

    model_config = ConfigDict(extra="forbid")


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
