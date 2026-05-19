import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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


__all__ = [
    "EntityMergeCommand",
    "EvidenceChunkRef",
    "IngestedEvidence",
]
