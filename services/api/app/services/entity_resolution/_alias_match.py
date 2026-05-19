from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity


async def step_1_alias_match(
    *,
    session: AsyncSession,
    candidate_text: str,
) -> Entity | None:
    result = await session.execute(
        select(Entity).where(Entity.merged_into_id.is_(None))
    )
    matches = [
        entity
        for entity in result.scalars().all()
        if isinstance(entity.aliases, list) and candidate_text in entity.aliases
    ]
    if len(matches) == 1:
        return matches[0]
    return None


__all__ = ["step_1_alias_match"]
