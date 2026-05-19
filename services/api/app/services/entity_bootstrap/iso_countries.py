import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EntityType
from app.schemas.common import EntityTypeEnum
from app.schemas.extraction import BootstrappedEntity
from app.services.entity_bootstrap._persist import insert_or_get_entity

_SOURCE_REGISTRY = "iso_3166"
_ISO_PATH = Path(__file__).resolve().parents[3] / "data" / "iso_3166_countries.json"


async def bootstrap_from_iso_countries(
    *,
    session: AsyncSession,
) -> list[BootstrappedEntity]:
    with _ISO_PATH.open() as fh:
        rows = json.load(fh)

    results: list[BootstrappedEntity] = []
    async with session.begin():
        for row in rows:
            aliases = sorted({row["name"], row["iso_alpha2"], row["iso_alpha3"]})
            entity, _ = await insert_or_get_entity(
                session=session,
                entity_type=EntityType.country,
                canonical_name=row["name"],
                aliases=aliases,
                external_ids={
                    "iso_alpha2": row["iso_alpha2"],
                    "iso_alpha3": row["iso_alpha3"],
                },
                primary_external_id_key="iso_alpha2",
                source_registry=_SOURCE_REGISTRY,
            )
            results.append(
                BootstrappedEntity(
                    entity_id=entity.id,
                    type=EntityTypeEnum.country,
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


__all__ = ["bootstrap_from_iso_countries"]
