from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EntityType
from app.schemas.common import EntityTypeEnum
from app.schemas.extraction import BootstrappedEntity
from app.services.entity_bootstrap._normalize import normalize_alias_set
from app.services.entity_bootstrap._persist import insert_or_get_entity

_SOURCE_REGISTRY = "gleif"


class GleifRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    lei: str
    legal_name: str
    other_names: list[str]
    jurisdiction: str


async def bootstrap_from_gleif(
    *,
    session: AsyncSession,
    fetcher: Callable[[], Awaitable[list[GleifRecord]]],
) -> list[BootstrappedEntity]:
    records = await fetcher()
    results: list[BootstrappedEntity] = []
    async with session.begin():
        for record in records:
            aliases = normalize_alias_set(record.legal_name, *record.other_names)
            entity, _ = await insert_or_get_entity(
                session=session,
                entity_type=EntityType.company,
                canonical_name=record.legal_name,
                aliases=aliases,
                external_ids={"lei": record.lei, "jurisdiction": record.jurisdiction},
                primary_external_id_key="lei",
                source_registry=_SOURCE_REGISTRY,
            )
            results.append(
                BootstrappedEntity(
                    entity_id=entity.id,
                    type=EntityTypeEnum.company,
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


__all__ = ["GleifRecord", "bootstrap_from_gleif"]
