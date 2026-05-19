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


async def test_bootstrap_from_tiingo_tickers_creates_company_entities(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.tiingo_tickers import (
        TiingoTickerRecord,
        bootstrap_from_tiingo_tickers,
    )

    async def fake_fetcher() -> list[TiingoTickerRecord]:
        return [
            TiingoTickerRecord(ticker="AAPL", name="Apple Inc.", exchange="NASDAQ"),
            TiingoTickerRecord(
                ticker="MSFT", name="Microsoft Corp.", exchange="NASDAQ"
            ),
        ]

    results = await bootstrap_from_tiingo_tickers(
        session=populated_session, fetcher=fake_fetcher
    )

    assert len(results) == 2
    apple = next(r for r in results if r.canonical_name == "Apple Inc.")
    assert apple.external_ids["tiingo_ticker"] == "AAPL"
    assert apple.external_ids["ticker"] == "AAPL"
    assert apple.external_ids["exchange"] == "NASDAQ"
    assert apple.source_registry == "tiingo_tickers"


async def test_bootstrap_from_tiingo_tickers_via_respx_mocked_endpoint(
    populated_session: AsyncSession,
) -> None:
    import httpx
    import respx

    from app.services.entity_bootstrap.tiingo_tickers import (
        TiingoTickerRecord,
        bootstrap_from_tiingo_tickers,
    )

    payload = [
        {"ticker": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ"},
    ]

    with respx.mock(base_url="https://api.tiingo.com") as mock:
        mock.get("/tiingo/fundamentals/meta").mock(
            return_value=httpx.Response(200, json=payload)
        )

        async def fetcher() -> list[TiingoTickerRecord]:
            async with httpx.AsyncClient(base_url="https://api.tiingo.com") as client:
                response = await client.get("/tiingo/fundamentals/meta")
                response.raise_for_status()
                records: list[TiingoTickerRecord] = []
                for row in response.json():
                    records.append(
                        TiingoTickerRecord(
                            ticker=row["ticker"],
                            name=row["name"],
                            exchange=row["exchange"],
                        )
                    )
                return records

        results = await bootstrap_from_tiingo_tickers(
            session=populated_session, fetcher=fetcher
        )

    assert len(results) == 1
    assert results[0].external_ids["tiingo_ticker"] == "AAPL"


async def test_bootstrap_from_tiingo_tickers_is_idempotent(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.tiingo_tickers import (
        TiingoTickerRecord,
        bootstrap_from_tiingo_tickers,
    )

    async def fake_fetcher() -> list[TiingoTickerRecord]:
        return [TiingoTickerRecord(ticker="AAPL", name="Apple Inc.", exchange="NASDAQ")]

    first = await bootstrap_from_tiingo_tickers(
        session=populated_session, fetcher=fake_fetcher
    )
    second = await bootstrap_from_tiingo_tickers(
        session=populated_session, fetcher=fake_fetcher
    )

    assert first[0].entity_id == second[0].entity_id
