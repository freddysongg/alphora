import uuid
from typing import Protocol, runtime_checkable

from app.db.models_graph import EntityType


@runtime_checkable
class CandidateLike(Protocol):
    text_span: str
    suggested_type: EntityType
    context_excerpt: str
    exact_quote: str
    chunk_id: uuid.UUID
    extraction_confidence: float


__all__ = ["CandidateLike"]
