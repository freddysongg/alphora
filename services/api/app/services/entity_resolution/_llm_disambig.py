import uuid
from collections.abc import Awaitable, Callable

from app.db.models_graph import Entity
from app.services.entity_resolution._types import CandidateLike

LlmDisambiguator = Callable[
    [CandidateLike, list[Entity]],
    Awaitable[uuid.UUID | None],
]


async def step_4_llm_disambiguation(
    *,
    candidate: CandidateLike,
    candidate_entities: list[Entity],
    disambiguator: LlmDisambiguator | None,
) -> uuid.UUID | None:
    if disambiguator is None:
        return None
    return await disambiguator(candidate, candidate_entities)


__all__ = ["LlmDisambiguator", "step_4_llm_disambiguation"]
