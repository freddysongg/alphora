from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType


class BootstrapError(Exception):
    """Raised when bootstrap inputs are malformed or persistence cannot proceed."""


async def insert_or_get_entity(
    *,
    session: AsyncSession,
    entity_type: EntityType,
    canonical_name: str,
    aliases: list[str],
    external_ids: dict[str, str],
    primary_external_id_key: str,
    source_registry: str,
) -> tuple[Entity, bool]:
    primary_value = external_ids.get(primary_external_id_key)
    if primary_value is None:
        raise BootstrapError(
            f"missing primary_external_id_key={primary_external_id_key!r} in external_ids"
        )

    candidates_result = await session.execute(
        select(Entity).where(Entity.type == entity_type.value)
    )
    candidates = candidates_result.scalars().all()
    existing = next(
        (
            row
            for row in candidates
            if isinstance(row.external_ids, dict)
            and row.external_ids.get(primary_external_id_key) == primary_value
        ),
        None,
    )

    if existing is not None:
        merged_aliases = sorted(set(existing.aliases or []) | set(aliases))
        merged_external_ids: dict[str, object] = {
            **external_ids,
            **(existing.external_ids or {}),
        }
        existing.aliases = merged_aliases
        existing.external_ids = merged_external_ids
        await session.flush()
        return existing, False

    new_entity = Entity(
        type=entity_type.value,
        canonical_name=canonical_name,
        aliases=list(aliases),
        external_ids=dict(external_ids),
        attributes={"source_registry": source_registry},
        confidence=1.0,
        needs_review=False,
    )
    session.add(new_entity)
    await session.flush()
    return new_entity, True


__all__ = ["BootstrapError", "insert_or_get_entity"]
