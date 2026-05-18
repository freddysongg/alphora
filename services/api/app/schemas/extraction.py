import uuid

from pydantic import BaseModel, ConfigDict


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


__all__ = [
    "EvidenceChunkRef",
    "IngestedEvidence",
]
