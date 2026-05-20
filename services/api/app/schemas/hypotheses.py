import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.graph import BeliefRecomputationPublic, EventResolutionPublic


class HypothesisStateFilter(StrEnum):
    proposed = "proposed"
    active = "active"
    all = "all"


class HypothesisState(StrEnum):
    proposed = "proposed"
    active = "active"
    validated = "validated"
    falsified = "falsified"
    expired = "expired"
    superseded = "superseded"


class DedupVerdict(StrEnum):
    duplicate = "duplicate"
    supersedes = "supersedes"
    unrelated = "unrelated"


class HypothesisDedupAction(StrEnum):
    inserted = "inserted"
    merged = "merged"
    superseded = "superseded"


class HypothesisPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_text: str
    state: HypothesisState
    scope_entity_ids: list[uuid.UUID]
    scope_theme_ids: list[uuid.UUID]
    source_run_id: uuid.UUID | None
    entity_id: uuid.UUID | None
    belief: float | None
    belief_history: list[dict[str, object]]
    parent_hypothesis_id: uuid.UUID | None
    superseded_by_id: uuid.UUID | None
    last_activity_at: datetime | None
    stagnation_flagged_at: datetime | None
    archived_at: datetime | None
    archived_reason: str | None
    valid_until: datetime | None
    created_at: datetime
    updated_at: datetime


class HypothesisListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[HypothesisPublic]
    next_cursor: str | None = Field(default=None)


class HypothesisBeliefResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis: HypothesisPublic
    latest: BeliefRecomputationPublic | None


class HypothesisHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[BeliefRecomputationPublic]


class ConditionalEdgePublic(BaseModel):
    model_config = ConfigDict(frozen=True)

    relation_id: uuid.UUID
    relation_type: str
    event_entity_id: uuid.UUID
    event_entity_name: str | None


class HypothesisLifecycleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis: HypothesisPublic
    parent: HypothesisPublic | None
    children: list[HypothesisPublic]
    supersedes: HypothesisPublic | None
    superseded_by: HypothesisPublic | None
    conditional_edges: list[ConditionalEdgePublic]
    recent_event_resolutions: list[EventResolutionPublic]


class HypothesisTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: HypothesisState
    reason: str | None = Field(default=None, max_length=500)


class LifecycleSweepCounts(BaseModel):
    model_config = ConfigDict(frozen=True)

    expired: int
    archived_belief_floor: int
    validated: int
    falsified: int
    stagnation_flagged: int


class LifecycleSweepResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counts: LifecycleSweepCounts
    expired_ids: list[uuid.UUID]
    archived_belief_floor_ids: list[uuid.UUID]
    validated_ids: list[uuid.UUID]
    falsified_ids: list[uuid.UUID]
    stagnation_flagged_ids: list[uuid.UUID]


class EventResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(..., max_length=32)
    resolved_at: datetime | None = Field(default=None)
    source_id: uuid.UUID | None = Field(default=None)
    notes: str | None = Field(default=None, max_length=1000)
    payload: dict[str, object] | None = Field(default=None)


class EventResolutionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution: EventResolutionPublic
    validated_hypothesis_ids: list[uuid.UUID]
    falsified_hypothesis_ids: list[uuid.UUID]


__all__ = [
    "ConditionalEdgePublic",
    "DedupVerdict",
    "EventResolutionRequest",
    "EventResolutionResponse",
    "HypothesisBeliefResponse",
    "HypothesisDedupAction",
    "HypothesisHistoryResponse",
    "HypothesisLifecycleResponse",
    "HypothesisListResponse",
    "HypothesisPublic",
    "HypothesisState",
    "HypothesisStateFilter",
    "HypothesisTransitionRequest",
    "LifecycleSweepCounts",
    "LifecycleSweepResponse",
]
