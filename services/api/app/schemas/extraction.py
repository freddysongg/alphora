import uuid

from pydantic import BaseModel, ConfigDict

from app.db.models_graph import EntityResolutionDecisionKind


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


class EntityResolutionOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_text: str
    decision_kind: EntityResolutionDecisionKind
    chosen_entity_id: uuid.UUID | None
    review_id: uuid.UUID | None
    confidence: float


__all__ = [
    "EntityResolutionOutcome",
    "EvidenceChunkRef",
    "IngestedEvidence",
]
