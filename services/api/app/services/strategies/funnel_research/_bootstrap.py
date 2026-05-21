from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.extraction import BootstrappedEntity
from app.services.entity_bootstrap.gics_sectors import bootstrap_from_gics


async def run(*, session: AsyncSession) -> list[BootstrappedEntity]:
    """Bootstrap the GICS hierarchy and return only top-level (level=1) sectors.

    The Stage 1 macro synthesis prompt consumes only the 11 top-level sectors,
    so deeper levels are persisted but filtered out of the return value.
    """
    all_entities = await bootstrap_from_gics(session=session)
    return [
        entity
        for entity in all_entities
        if entity.external_ids.get("gics_code", "") != ""
        and len(entity.external_ids["gics_code"]) == 2
    ]


__all__ = ["run"]
