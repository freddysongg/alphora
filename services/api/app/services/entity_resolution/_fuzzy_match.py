from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity
from app.services.entity_resolution._normalize import normalize_for_match

_FUZZY_THRESHOLD: float = 0.85
_AMBIGUITY_MARGIN: float = 0.80


def _score(left: str, right: str) -> float:
    return float(fuzz.token_set_ratio(left, right)) / 100.0


async def step_3_fuzzy_match(
    *,
    session: AsyncSession,
    candidate_text: str,
) -> tuple[Entity | None, float]:
    normalized_candidate = normalize_for_match(candidate_text)
    if not normalized_candidate:
        return None, 0.0

    result = await session.execute(
        select(Entity).where(Entity.merged_into_id.is_(None))
    )
    entities = result.scalars().all()
    if not entities:
        return None, 0.0

    scored: list[tuple[Entity, float]] = []
    for entity in entities:
        names: list[str] = [entity.canonical_name, *list(entity.aliases or [])]
        best = max(
            _score(normalized_candidate, normalize_for_match(name))
            for name in names
        )
        scored.append((entity, best))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    top_entity, top_score = scored[0]
    if top_score < _FUZZY_THRESHOLD:
        return None, top_score

    second_score = scored[1][1] if len(scored) > 1 else 0.0
    if second_score >= _AMBIGUITY_MARGIN:
        return None, top_score

    return top_entity, top_score


__all__ = ["step_3_fuzzy_match"]
