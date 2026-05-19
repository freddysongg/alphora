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


async def test_bootstrap_from_iso_countries_creates_country_entities(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.iso_countries import bootstrap_from_iso_countries

    results = await bootstrap_from_iso_countries(session=populated_session)

    assert len(results) >= 5
    alpha2 = {r.external_ids["iso_alpha2"] for r in results}
    assert "US" in alpha2

    us = next(r for r in results if r.external_ids["iso_alpha2"] == "US")
    assert us.canonical_name == "United States"
    assert us.external_ids["iso_alpha3"] == "USA"
    assert us.source_registry == "iso_3166"


async def test_bootstrap_from_iso_countries_is_idempotent(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.iso_countries import bootstrap_from_iso_countries

    first = await bootstrap_from_iso_countries(session=populated_session)
    second = await bootstrap_from_iso_countries(session=populated_session)

    first_ids = {r.entity_id for r in first}
    second_ids = {r.entity_id for r in second}
    assert first_ids == second_ids
