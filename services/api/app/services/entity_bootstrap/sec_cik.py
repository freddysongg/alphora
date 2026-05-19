from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EntityType
from app.schemas.common import EntityTypeEnum
from app.schemas.extraction import BootstrappedEntity
from app.services.entity_bootstrap._normalize import normalize_alias_set
from app.services.entity_bootstrap._persist import insert_or_get_entity
from app.services.source_clients.sec_edgar import SecCompanyTickersResponse

_SOURCE_REGISTRY = "sec_cik"


async def bootstrap_from_sec_cik(
    *,
    session: AsyncSession,
    payload: SecCompanyTickersResponse,
) -> list[BootstrappedEntity]:
    results: list[BootstrappedEntity] = []
    async with session.begin():
        for company in payload.companies:
            padded_cik = str(company.cik_str).zfill(10)
            aliases = normalize_alias_set(company.title)
            entity, _ = await insert_or_get_entity(
                session=session,
                entity_type=EntityType.company,
                canonical_name=company.title,
                aliases=aliases,
                external_ids={"cik": padded_cik, "ticker": company.ticker},
                primary_external_id_key="cik",
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


__all__ = ["bootstrap_from_sec_cik"]
