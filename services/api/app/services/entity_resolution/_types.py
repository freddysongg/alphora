import uuid
from typing import Protocol, runtime_checkable

from app.schemas.common import EntityTypeEnum


@runtime_checkable
class CandidateLike(Protocol):
    text_span: str
    suggested_type: EntityTypeEnum
    context_excerpt: str
    exact_quote: str
    chunk_id: uuid.UUID
    extraction_confidence: float


__all__ = ["CandidateLike"]
