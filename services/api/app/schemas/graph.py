import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.common import (
    AuditActionEnum,
    EntityResolutionDecisionEnum,
    EntityResolutionReviewStatusEnum,
    EntityTypeEnum,
    HypothesisStatusEnum,
    ProposedTypeKindEnum,
    ProposedTypeStatusEnum,
    RelationTypeEnum,
)


class DataSourcePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    name: str
    kind: str
    description: str | None
    homepage_url: str | None
    attributes: dict[str, object] | None
    created_at: datetime
    updated_at: datetime


class EvidencePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    source: str
    source_id: uuid.UUID | None
    document_id: str
    raw_url: str | None
    raw_blob_ref: str | None
    content_hash: str
    structured: dict[str, object] | None
    extracted_at: datetime
    extracted_by_model: str | None
    prompt_version: str | None
    sign: float
    created_at: datetime
    updated_at: datetime


class EvidenceChunkPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    evidence_id: uuid.UUID
    chunk_index: int
    text: str
    start_offset: int | None
    end_offset: int | None
    attributes: dict[str, object] | None
    content_hash: str
    created_at: datetime


class EntityPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    type: EntityTypeEnum
    canonical_name: str
    aliases: list[str]
    external_ids: dict[str, object]
    attributes: dict[str, object]
    confidence: float
    needs_review: bool
    merged_into_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class RelationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    from_id: uuid.UUID
    to_id: uuid.UUID
    type: RelationTypeEnum
    attributes: dict[str, object]
    valid_from: datetime | None
    valid_to: datetime | None
    extraction_confidence: float | None
    source_id: uuid.UUID | None
    corroboration_count: int
    extracted_by_model: str | None
    prompt_version: str | None
    is_explicit: bool
    sign: float
    created_at: datetime


class HypothesisPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    claim_text: str
    scope_entity_ids: list[str]
    scope_theme_ids: list[str]
    status: HypothesisStatusEnum
    valid_until: datetime | None
    proposed_by_run_id: uuid.UUID | None
    belief: float | None
    belief_history: list[dict[str, object]]
    created_at: datetime
    updated_at: datetime


class BeliefRecomputationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    hypothesis_id: uuid.UUID
    computed_at: datetime
    belief: float
    contributing_evidence_ids: list[str]
    computation_method: str


class EntityResolutionReviewPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    candidate_text: str
    suggested_type: EntityTypeEnum
    context_excerpt: str | None
    decision_kind: EntityResolutionDecisionEnum
    candidate_entity_ids: list[str]
    chosen_entity_id: uuid.UUID | None
    status: EntityResolutionReviewStatusEnum
    confidence: float | None
    evidence_id: uuid.UUID | None
    notes: str | None
    resolved_at: datetime | None
    created_at: datetime


class EntityMergePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    surviving_id: uuid.UUID
    merged_id: uuid.UUID
    reason: str
    merged_by: str
    merged_at: datetime
    reversible_until: datetime | None
    reversed_at: datetime | None


class ProposedTypePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    kind: ProposedTypeKindEnum
    proposed_name: str
    description: str | None
    example_evidence_ids: list[str]
    proposed_by: str
    vote_count: int
    status: ProposedTypeStatusEnum
    created_at: datetime
    updated_at: datetime


class AuditLogPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    table_name: str
    row_id: uuid.UUID
    action: AuditActionEnum
    before: dict[str, object] | None
    after: dict[str, object] | None
    actor: str
    at: datetime


__all__ = [
    "AuditLogPublic",
    "BeliefRecomputationPublic",
    "DataSourcePublic",
    "EntityMergePublic",
    "EntityPublic",
    "EntityResolutionReviewPublic",
    "EvidenceChunkPublic",
    "EvidencePublic",
    "HypothesisPublic",
    "ProposedTypePublic",
    "RelationPublic",
]
