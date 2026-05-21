from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType


class BootstrapError(Exception):
    """Raised when bootstrap inputs are malformed or persistence cannot proceed."""


def _derive_ticker_normalized(external_ids: Mapping[str, object]) -> str | None:
    ticker = external_ids.get("ticker")
    if isinstance(ticker, str) and ticker:
        return ticker.upper()
    return None


async def fetch_existing_by_primary_value(
    *,
    session: AsyncSession,
    entity_type: EntityType,
    primary_external_id_key: str,
) -> dict[str, Entity]:
    result = await session.execute(
        select(Entity).where(Entity.type == entity_type.value)
    )
    cache: dict[str, Entity] = {}
    for row in result.scalars():
        external_ids = row.external_ids
        if not isinstance(external_ids, dict):
            continue
        value = external_ids.get(primary_external_id_key)
        if isinstance(value, str):
            cache[value] = row
    return cache


async def insert_or_get_entity(
    *,
    session: AsyncSession,
    entity_type: EntityType,
    canonical_name: str,
    aliases: list[str],
    external_ids: dict[str, str],
    primary_external_id_key: str,
    source_registry: str,
    existing_by_primary_value: dict[str, Entity] | None = None,
    extra_attributes: dict[str, object] | None = None,
) -> tuple[Entity, bool]:
    primary_value = external_ids.get(primary_external_id_key)
    if primary_value is None:
        raise BootstrapError(
            f"missing primary_external_id_key={primary_external_id_key!r} in external_ids"
        )

    cache = existing_by_primary_value
    if cache is None:
        cache = await fetch_existing_by_primary_value(
            session=session,
            entity_type=entity_type,
            primary_external_id_key=primary_external_id_key,
        )

    existing = cache.get(primary_value)
    if existing is not None:
        merged_aliases = sorted(set(existing.aliases or []) | set(aliases))
        merged_external_ids: dict[str, object] = {
            **external_ids,
            **(existing.external_ids or {}),
        }
        existing.aliases = merged_aliases
        existing.external_ids = merged_external_ids
        existing.ticker_normalized = _derive_ticker_normalized(merged_external_ids)
        if extra_attributes is not None:
            merged_attributes: dict[str, object] = {
                **(existing.attributes or {}),
                **extra_attributes,
            }
            existing.attributes = merged_attributes
        await session.flush()
        return existing, False

    new_attributes: dict[str, object] = {"source_registry": source_registry}
    if extra_attributes is not None:
        new_attributes.update(extra_attributes)
    new_entity = Entity(
        type=entity_type.value,
        canonical_name=canonical_name,
        aliases=list(aliases),
        external_ids=dict(external_ids),
        attributes=new_attributes,
        ticker_normalized=_derive_ticker_normalized(external_ids),
        confidence=1.0,
        needs_review=False,
    )
    session.add(new_entity)
    await session.flush()
    cache[primary_value] = new_entity
    return new_entity, True


__all__ = [
    "BootstrapError",
    "fetch_existing_by_primary_value",
    "insert_or_get_entity",
]
