"""Resolve `SectorCompanyIdea.company_entity_id` at sector brief persistence time.

Each sector synthesis emits company ideas as `name + ticker?`. At persist
time, this helper resolves each idea to a canonical company entity id so
the persisted brief carries a navigable `company_entity_id`. The web UI
links the company name directly to the company thesis page using that id.

Resolution order (matches `_build_company_resolutions` in funnel core):
1. Indexed `ticker_normalized` when the idea carries a ticker.
2. Exact `canonical_name` match.
3. JSON `aliases` fallback (broader load, only when narrow query missed).

Ideas that can't be resolved keep `company_entity_id=None`.
"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType
from app.schemas.sector_brief import SectorBrief, SectorCompanyIdea


async def resolve_sector_company_entity_ids(
    *,
    session: AsyncSession,
    brief: SectorBrief,
) -> SectorBrief:
    if not brief.companies:
        return brief

    names = {company.name for company in brief.companies}
    tickers_uppercase = {
        company.ticker.upper() for company in brief.companies if company.ticker
    }

    narrow_conditions = [Entity.canonical_name.in_(names)]
    if tickers_uppercase:
        narrow_conditions.append(Entity.ticker_normalized.in_(tickers_uppercase))

    narrow_rows = (
        (
            await session.execute(
                select(Entity).where(
                    Entity.type == EntityType.company.value,
                    or_(*narrow_conditions),
                )
            )
        )
        .scalars()
        .all()
    )

    by_canonical_name: dict[str, Entity] = {}
    by_ticker: dict[str, Entity] = {}
    for row in narrow_rows:
        by_canonical_name.setdefault(row.canonical_name, row)
        if row.ticker_normalized:
            by_ticker.setdefault(row.ticker_normalized, row)

    resolved_companies: list[SectorCompanyIdea] = []
    unresolved_indexes: list[int] = []
    for index, company in enumerate(brief.companies):
        entity: Entity | None = None
        if company.ticker:
            entity = by_ticker.get(company.ticker.upper())
        if entity is None:
            entity = by_canonical_name.get(company.name)
        if entity is None:
            resolved_companies.append(company)
            unresolved_indexes.append(index)
            continue
        resolved_companies.append(company.model_copy(update={"company_entity_id": entity.id}))

    if unresolved_indexes:
        all_rows = (
            (
                await session.execute(
                    select(Entity).where(Entity.type == EntityType.company.value)
                )
            )
            .scalars()
            .all()
        )
        by_alias: dict[str, Entity] = {}
        for row in all_rows:
            for alias in row.aliases or []:
                if isinstance(alias, str) and alias:
                    by_alias.setdefault(alias.lower(), row)
        for index in unresolved_indexes:
            original = brief.companies[index]
            entity = by_alias.get(original.name.lower())
            if entity is None:
                continue
            resolved_companies[index] = original.model_copy(
                update={"company_entity_id": entity.id}
            )

    return brief.model_copy(update={"companies": resolved_companies})


__all__ = ["resolve_sector_company_entity_ids"]
