from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.extraction import BootstrappedEntity
from app.services.entity_bootstrap.gics_sectors import bootstrap_from_gics


async def run(*, session: AsyncSession) -> list[BootstrappedEntity]:
    return await bootstrap_from_gics(session=session)


__all__ = ["run"]
