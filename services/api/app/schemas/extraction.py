import uuid

from pydantic import BaseModel, ConfigDict

from app.schemas.common import EntityTypeEnum, RelationTypeEnum


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


__all__ = [
    "CandidateEntity",
    "CandidateRelation",
    "EvidenceChunkRef",
    "ExtractionResult",
    "IngestedEvidence",
]
