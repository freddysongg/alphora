from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

_TOP_LEVEL_NAMES: frozenset[str] = frozenset(
    {
        "Energy",
        "Materials",
        "Industrials",
        "Consumer Discretionary",
        "Consumer Staples",
        "Health Care",
        "Financials",
        "Information Technology",
        "Communication Services",
        "Utilities",
        "Real Estate",
    }
)


@pytest.fixture()
async def populated_session(
    initialized_schema: None,
) -> AsyncIterator[AsyncSession]:
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def test_bootstrap_from_gics_creates_full_hierarchy(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.gics_sectors import bootstrap_from_gics

    results = await bootstrap_from_gics(session=populated_session)

    top_level = [
        bootstrap
        for bootstrap in results
        if len(bootstrap.external_ids["gics_code"]) == 2
    ]
    top_level_names = {bootstrap.canonical_name for bootstrap in top_level}
    assert top_level_names == _TOP_LEVEL_NAMES
    assert len(top_level) == 11

    industry_groups = [
        bootstrap
        for bootstrap in results
        if len(bootstrap.external_ids["gics_code"]) == 4
    ]
    assert len(industry_groups) >= 20

    codes = [r.external_ids["gics_code"] for r in results]
    assert len(codes) == len(set(codes))

    energy = next(
        r
        for r in top_level
        if r.canonical_name == "Energy"
    )
    assert energy.external_ids["gics_code"] == "10"
    assert energy.source_registry == "gics"


async def test_bootstrap_from_gics_is_idempotent(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.gics_sectors import bootstrap_from_gics

    first = await bootstrap_from_gics(session=populated_session)
    second = await bootstrap_from_gics(session=populated_session)

    first_ids = {r.entity_id for r in first}
    second_ids = {r.entity_id for r in second}
    assert first_ids == second_ids


async def test_load_top_level_sector_names_from_db(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.gics_sectors import (
        bootstrap_from_gics,
        load_top_level_sector_names,
    )

    await bootstrap_from_gics(session=populated_session)
    names = await load_top_level_sector_names(session=populated_session)
    assert set(names) == _TOP_LEVEL_NAMES


async def test_load_top_level_sector_names_empty_when_no_bootstrap(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.gics_sectors import (
        load_top_level_sector_names,
    )

    names = await load_top_level_sector_names(session=populated_session)
    assert names == []


def test_load_seed_top_level_sector_names_matches_set() -> None:
    from app.services.entity_bootstrap.gics_sectors import (
        load_seed_top_level_sector_names,
    )

    names = load_seed_top_level_sector_names()
    assert set(names) == _TOP_LEVEL_NAMES
    assert len(names) == 11


async def test_bootstrap_attributes_include_gics_level_and_parent(
    populated_session: AsyncSession,
) -> None:
    from sqlalchemy import select

    from app.db.models_graph import Entity, EntityType
    from app.services.entity_bootstrap.gics_sectors import bootstrap_from_gics

    await bootstrap_from_gics(session=populated_session)
    rows = (
        await populated_session.execute(
            select(Entity).where(Entity.type == EntityType.sector.value)
        )
    ).scalars().all()
    by_code: dict[str, Entity] = {}
    for entity in rows:
        ext = entity.external_ids or {}
        code = ext.get("gics_code") if isinstance(ext, dict) else None
        if isinstance(code, str):
            by_code[code] = entity
    energy_top = by_code["10"]
    energy_group = by_code["1010"]
    assert isinstance(energy_top.attributes, dict)
    assert energy_top.attributes.get("gics_level") == 1
    assert energy_top.attributes.get("parent_gics_code") is None
    assert isinstance(energy_group.attributes, dict)
    assert energy_group.attributes.get("gics_level") == 2
    assert energy_group.attributes.get("parent_gics_code") == "10"
