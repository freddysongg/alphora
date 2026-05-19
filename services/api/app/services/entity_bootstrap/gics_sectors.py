import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EntityType
from app.schemas.common import EntityTypeEnum
from app.schemas.extraction import BootstrappedEntity
from app.services.entity_bootstrap._normalize import normalize_alias_set
from app.services.entity_bootstrap._persist import insert_or_get_entity

_SOURCE_REGISTRY = "gics"
_GICS_PATH = Path(__file__).resolve().parents[3] / "data" / "gics_industries.json"


async def bootstrap_from_gics(
    *,
    session: AsyncSession,
) -> list[BootstrappedEntity]:
    with _GICS_PATH.open() as fh:
        rows = json.load(fh)

    results: list[BootstrappedEntity] = []
    async with session.begin():
        for row in rows:
            entity, _ = await insert_or_get_entity(
                session=session,
                entity_type=EntityType.sector,
                canonical_name=row["name"],
                aliases=normalize_alias_set(row["name"]),
                external_ids={"gics_code": row["gics_code"]},
                primary_external_id_key="gics_code",
                source_registry=_SOURCE_REGISTRY,
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


__all__ = ["bootstrap_from_gics"]
