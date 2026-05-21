from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EntityType
from app.schemas.common import EntityTypeEnum
from app.schemas.extraction import BootstrappedEntity
from app.services.entity_bootstrap._normalize import normalize_alias_set
from app.services.entity_bootstrap._persist import (
    fetch_existing_by_primary_value,
    insert_or_get_entity,
)

_SOURCE_REGISTRY = "polygon_tickers"
_PRIMARY_KEY = "polygon_id"


class PolygonTickerRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    polygon_id: str
    ticker: str
    name: str
    market: str


async def bootstrap_from_polygon_tickers(
    *,
    session: AsyncSession,
    fetcher: Callable[[], Awaitable[list[PolygonTickerRecord]]],
) -> list[BootstrappedEntity]:
    records = await fetcher()
    results: list[BootstrappedEntity] = []
    async with session.begin():
        cache = await fetch_existing_by_primary_value(
            session=session,
            entity_type=EntityType.company,
            primary_external_id_key=_PRIMARY_KEY,
        )
        for record in records:
            aliases = normalize_alias_set(record.name)
            entity, _ = await insert_or_get_entity(
                session=session,
                entity_type=EntityType.company,
                canonical_name=record.name,
                aliases=aliases,
                external_ids={
                    "polygon_id": record.polygon_id,
                    "ticker": record.ticker,
                    "market": record.market,
                },
                primary_external_id_key=_PRIMARY_KEY,
                source_registry=_SOURCE_REGISTRY,
                existing_by_primary_value=cache,
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


__all__ = ["PolygonTickerRecord", "bootstrap_from_polygon_tickers"]
