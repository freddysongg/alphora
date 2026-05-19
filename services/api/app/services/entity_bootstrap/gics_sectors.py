import json
from pathlib import Path
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType
from app.schemas.common import EntityTypeEnum
from app.schemas.extraction import BootstrappedEntity
from app.services.entity_bootstrap._normalize import normalize_alias_set
from app.services.entity_bootstrap._persist import (
    fetch_existing_by_primary_value,
    insert_or_get_entity,
)

_SOURCE_REGISTRY = "gics"
_PRIMARY_KEY = "gics_code"
_GICS_PATH = Path(__file__).resolve().parents[3] / "data" / "gics_industries.json"


async def bootstrap_from_gics(
    *,
    session: AsyncSession,
) -> list[BootstrappedEntity]:
    with _GICS_PATH.open() as fh:
        payload = json.load(fh)
    nodes = payload["nodes"] if isinstance(payload, dict) else payload

    results: list[BootstrappedEntity] = []
    async with session.begin():
        cache = await fetch_existing_by_primary_value(
            session=session,
            entity_type=EntityType.sector,
            primary_external_id_key=_PRIMARY_KEY,
        )
        for row in nodes:
            level = int(row.get("level", 1))
            parent_gics_code = row.get("parent_gics_code")
            extra_attributes: dict[str, object] = {
                "gics_level": level,
                "gics_code": row["gics_code"],
                "parent_gics_code": parent_gics_code,
            }
            entity, _ = await insert_or_get_entity(
                session=session,
                entity_type=EntityType.sector,
                canonical_name=row["name"],
                aliases=normalize_alias_set(row["name"]),
                external_ids={"gics_code": row["gics_code"]},
                primary_external_id_key=_PRIMARY_KEY,
                source_registry=_SOURCE_REGISTRY,
                existing_by_primary_value=cache,
                extra_attributes=extra_attributes,
            )
            results.append(
                BootstrappedEntity(
                    entity_id=entity.id,
                    type=EntityTypeEnum.sector,
                    canonical_name=entity.canonical_name,
                    aliases=list(entity.aliases or []),
                    external_ids={
                        key: str(value)
                        for key, value in (entity.external_ids or {}).items()
                    },
                    source_registry=_SOURCE_REGISTRY,
                )
            )
    return results


async def load_top_level_sector_names(*, session: AsyncSession) -> list[str]:
    """Return canonical names of GICS top-level sectors (level=1) in the db.

    Sourced from the bootstrap-populated `entities` rows where
    `type='sector'` and `attributes.gics_level=1`. Falls back to the
    flat-seed names if no rows are present (i.e. tests that skip bootstrap).
    """
    result = await session.execute(
        select(Entity.canonical_name, Entity.attributes).where(
            Entity.type == EntityType.sector.value
        )
    )
    names: list[str] = []
    for canonical_name, attributes in result.all():
        if not isinstance(attributes, dict):
            continue
        level = attributes.get("gics_level")
        if level == 1 and isinstance(canonical_name, str):
            names.append(canonical_name)
    return sorted(names)


def load_seed_top_level_sector_names() -> list[str]:
    """Return canonical names of GICS top-level sectors from the seed file.

    Used by code paths that need the allowlist without a db session (e.g.
    config-level defaults or sanity-check assertions).
    """
    with _GICS_PATH.open() as fh:
        payload = json.load(fh)
    nodes = payload["nodes"] if isinstance(payload, dict) else payload
    return sorted(
        cast(str, row["name"])
        for row in nodes
        if int(row.get("level", 1)) == 1
    )


__all__ = [
    "bootstrap_from_gics",
    "load_seed_top_level_sector_names",
    "load_top_level_sector_names",
]
