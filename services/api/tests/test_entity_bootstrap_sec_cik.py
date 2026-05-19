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


async def test_bootstrap_from_sec_cik_creates_company_entities(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.sec_cik import bootstrap_from_sec_cik
    from app.services.source_clients.sec_edgar import (
        SecCompanyTicker,
        SecCompanyTickersResponse,
    )

    payload = SecCompanyTickersResponse(
        companies=[
            SecCompanyTicker(cik_str=320193, ticker="AAPL", title="Apple Inc."),
            SecCompanyTicker(cik_str=789019, ticker="MSFT", title="Microsoft Corp."),
        ]
    )

    results = await bootstrap_from_sec_cik(session=populated_session, payload=payload)

    assert len(results) == 2
    by_ticker = {r.external_ids["ticker"]: r for r in results}
    aapl = by_ticker["AAPL"]
    assert aapl.canonical_name == "Apple Inc."
    assert aapl.external_ids["cik"] == "0000320193"
    assert "Apple" in aapl.aliases
    assert "Apple Inc." in aapl.aliases
    assert aapl.source_registry == "sec_cik"


async def test_bootstrap_from_sec_cik_pads_cik_to_ten_digits(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.sec_cik import bootstrap_from_sec_cik
    from app.services.source_clients.sec_edgar import (
        SecCompanyTicker,
        SecCompanyTickersResponse,
    )

    payload = SecCompanyTickersResponse(
        companies=[
            SecCompanyTicker(cik_str=42, ticker="ANS", title="Answer Inc."),
        ]
    )

    results = await bootstrap_from_sec_cik(session=populated_session, payload=payload)
    assert results[0].external_ids["cik"] == "0000000042"


async def test_bootstrap_from_sec_cik_is_idempotent(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.sec_cik import bootstrap_from_sec_cik
    from app.services.source_clients.sec_edgar import (
        SecCompanyTicker,
        SecCompanyTickersResponse,
    )

    payload = SecCompanyTickersResponse(
        companies=[SecCompanyTicker(cik_str=320193, ticker="AAPL", title="Apple Inc.")]
    )

    first = await bootstrap_from_sec_cik(session=populated_session, payload=payload)
    second = await bootstrap_from_sec_cik(session=populated_session, payload=payload)

    assert first[0].entity_id == second[0].entity_id


async def test_bootstrap_from_sec_cik_handles_empty_payload(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.sec_cik import bootstrap_from_sec_cik
    from app.services.source_clients.sec_edgar import SecCompanyTickersResponse

    payload = SecCompanyTickersResponse(companies=[])
    results = await bootstrap_from_sec_cik(session=populated_session, payload=payload)
    assert results == []
