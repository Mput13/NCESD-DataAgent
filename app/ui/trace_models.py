from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.artifacts.workflow_artifacts import FeedbackArtifact, TraceEvent


IndexState = Literal["building", "ready", "stale", "gated_skip"]


class IndexStatusView(BaseModel):
    state: IndexState
    collection_name: str | None = None
    dense_status: str | None = None
    build_log_path: str | None = None
    gated_reason: str | None = None

    model_config = ConfigDict(extra="forbid")


class FeedbackRequest(BaseModel):
    run_id: str
    artifact_id: str | None = None
    rating: Literal["positive", "negative", "neutral", "not_set"] = "not_set"
    comment: str | None = None
    diagnostic: bool = True

    def to_artifact(self) -> FeedbackArtifact:
        return FeedbackArtifact(
            run_id=self.run_id,
            artifact_id=self.artifact_id or self.run_id,
            rating=self.rating,
            user_comment=self.comment,
        )

    model_config = ConfigDict(extra="forbid")


class FixRequest(BaseModel):
    run_id: str
    target_state: str
    requested_change: str | None = None
    diagnostic: bool = True

    model_config = ConfigDict(extra="forbid")


class WorkflowTraceViewModel(BaseModel):
    run_id: str
    index_status: IndexStatusView
    trace_events: list[TraceEvent] = Field(default_factory=list)
    selected_sources: list[dict[str, object]] = Field(default_factory=list)
    rejected_sources: list[dict[str, object]] = Field(default_factory=list)
    artifacts: list[dict[str, object]] = Field(default_factory=list)
    feedback: FeedbackRequest | None = None
    fix_request: FixRequest | None = None
    diagnostic: bool = True

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")
