from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EntityType
from app.schemas.common import EntityTypeEnum
from app.schemas.extraction import BootstrappedEntity
from app.services.entity_bootstrap._normalize import normalize_alias_set
from app.services.entity_bootstrap._persist import insert_or_get_entity

_SOURCE_REGISTRY = "tiingo_tickers"


class TiingoTickerRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    ticker: str
    name: str
    exchange: str


async def bootstrap_from_tiingo_tickers(
    *,
    session: AsyncSession,
    fetcher: Callable[[], Awaitable[list[TiingoTickerRecord]]],
) -> list[BootstrappedEntity]:
    records = await fetcher()
    results: list[BootstrappedEntity] = []
    async with session.begin():
        for record in records:
            aliases = normalize_alias_set(record.name)
            entity, _ = await insert_or_get_entity(
                session=session,
                entity_type=EntityType.company,
                canonical_name=record.name,
                aliases=aliases,
                external_ids={
                    "tiingo_ticker": record.ticker,
                    "ticker": record.ticker,
                    "exchange": record.exchange,
                },
                primary_external_id_key="tiingo_ticker",
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


__all__ = ["TiingoTickerRecord", "bootstrap_from_tiingo_tickers"]
