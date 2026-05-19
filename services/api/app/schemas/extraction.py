import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models_graph import EntityResolutionDecisionKind
from app.schemas.common import EntityTypeEnum, RelationTypeEnum


class EntityMergeCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    surviving_id: uuid.UUID
    merged_id: uuid.UUID
    reason: str
    merged_by: str
    reversible_until: datetime | None


class IngestedEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: uuid.UUID
    content_hash: str
    chunk_count: int
    source: str
    document_id: str


class EvidenceChunkRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: uuid.UUID
    evidence_id: uuid.UUID
    chunk_index: int
    text: str
    attributes: dict[str, object]


class BootstrappedEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity_id: uuid.UUID
    type: EntityTypeEnum
    canonical_name: str
    aliases: list[str]
    external_ids: dict[str, str]
    source_registry: str


class CandidateEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    text_span: str
    suggested_type: EntityTypeEnum
    context_excerpt: str
    exact_quote: str
    chunk_id: uuid.UUID
    extraction_confidence: float


class CandidateRelation(BaseModel):
    model_config = ConfigDict(frozen=True)

    subj_span: str
    predicate: RelationTypeEnum
    obj_span: str
    exact_quote: str
    chunk_id: uuid.UUID
    is_explicit: bool
    extraction_confidence: float


class ExtractionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: uuid.UUID
    candidate_entities: list[CandidateEntity]
    candidate_relations: list[CandidateRelation]
    model_id: str
    prompt_version: str
    verified: bool
    rejection_reasons: list[str]


class EntityResolutionOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_text: str
    decision_kind: EntityResolutionDecisionKind
    chosen_entity_id: uuid.UUID | None
    review_id: uuid.UUID | None
    confidence: float


__all__ = [
    "BootstrappedEntity",
    "CandidateEntity",
    "CandidateRelation",
    "EntityMergeCommand",
    "EntityResolutionOutcome",
    "EvidenceChunkRef",
    "ExtractionResult",
    "IngestedEvidence",
]
