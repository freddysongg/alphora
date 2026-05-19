from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture()
async def populated_session(
    initialized_schema: None,
) -> AsyncIterator[AsyncSession]:
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def test_bootstrap_from_gics_creates_sector_entities(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.gics_sectors import bootstrap_from_gics

    results = await bootstrap_from_gics(session=populated_session)

    assert len(results) == 11
    names = {bootstrap.canonical_name for bootstrap in results}
    assert names == {
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
    codes = [r.external_ids["gics_code"] for r in results]
    assert len(codes) == len(set(codes))
    energy = next(r for r in results if r.canonical_name == "Energy")
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
