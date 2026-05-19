from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EntityType
from app.schemas.common import EntityTypeEnum
from app.schemas.extraction import BootstrappedEntity
from app.services.entity_bootstrap._persist import insert_or_get_entity

_SOURCE_REGISTRY = "congress_bioguide"


class CongressMemberRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    bioguide_id: str
    full_name: str
    party: str
    state: str
    chamber: str


def _build_person_aliases(full_name: str) -> list[str]:
    cleaned = " ".join(full_name.split())
    aliases: set[str] = {cleaned} if cleaned else set()
    if "," in cleaned:
        last, _, rest = cleaned.partition(",")
        flipped = f"{rest.strip()} {last.strip()}".strip()
        if flipped:
            aliases.add(flipped)
    else:
        parts = cleaned.split()
        if len(parts) >= 2:
            aliases.add(f"{parts[-1]}, {' '.join(parts[:-1])}")
    return sorted(aliases)


async def bootstrap_from_congress_bioguide(
    *,
    session: AsyncSession,
    fetcher: Callable[[], Awaitable[list[CongressMemberRecord]]],
) -> list[BootstrappedEntity]:
    records = await fetcher()
    results: list[BootstrappedEntity] = []
    async with session.begin():
        for record in records:
            aliases = _build_person_aliases(record.full_name)
            entity, _ = await insert_or_get_entity(
                session=session,
                entity_type=EntityType.person,
                canonical_name=record.full_name,
                aliases=aliases,
                external_ids={
                    "bioguide_id": record.bioguide_id,
                    "party": record.party,
                    "state": record.state,
                    "chamber": record.chamber,
                },
                primary_external_id_key="bioguide_id",
                source_registry=_SOURCE_REGISTRY,
            )
            results.append(
                BootstrappedEntity(
                    entity_id=entity.id,
                    type=EntityTypeEnum.person,
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


__all__ = ["CongressMemberRecord", "bootstrap_from_congress_bioguide"]
