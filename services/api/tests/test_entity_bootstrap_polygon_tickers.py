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


async def test_bootstrap_from_polygon_tickers_creates_company_entities(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.polygon_tickers import (
        PolygonTickerRecord,
        bootstrap_from_polygon_tickers,
    )

    async def fake_fetcher() -> list[PolygonTickerRecord]:
        return [
            PolygonTickerRecord(
                polygon_id="AAPL",
                ticker="AAPL",
                name="Apple Inc.",
                market="stocks",
            ),
            PolygonTickerRecord(
                polygon_id="MSFT",
                ticker="MSFT",
                name="Microsoft Corp.",
                market="stocks",
            ),
        ]

    results = await bootstrap_from_polygon_tickers(
        session=populated_session, fetcher=fake_fetcher
    )

    assert len(results) == 2
    apple = next(r for r in results if r.canonical_name == "Apple Inc.")
    assert apple.external_ids["polygon_id"] == "AAPL"
    assert apple.external_ids["ticker"] == "AAPL"
    assert apple.external_ids["market"] == "stocks"
    assert apple.source_registry == "polygon_tickers"


async def test_bootstrap_from_polygon_tickers_via_respx_mocked_endpoint(
    populated_session: AsyncSession,
) -> None:
    import httpx
    import respx

    from app.services.entity_bootstrap.polygon_tickers import (
        PolygonTickerRecord,
        bootstrap_from_polygon_tickers,
    )

    payload = {
        "results": [
            {
                "ticker": "AAPL",
                "name": "Apple Inc.",
                "market": "stocks",
                "primary_exchange": "XNAS",
            }
        ]
    }

    with respx.mock(base_url="https://api.polygon.io/v3") as mock:
        mock.get("/reference/tickers").mock(
            return_value=httpx.Response(200, json=payload)
        )

        async def fetcher() -> list[PolygonTickerRecord]:
            async with httpx.AsyncClient(
                base_url="https://api.polygon.io/v3"
            ) as client:
                response = await client.get("/reference/tickers")
                response.raise_for_status()
                records: list[PolygonTickerRecord] = []
                for row in response.json()["results"]:
                    records.append(
                        PolygonTickerRecord(
                            polygon_id=row["ticker"],
                            ticker=row["ticker"],
                            name=row["name"],
                            market=row["market"],
                        )
                    )
                return records

        results = await bootstrap_from_polygon_tickers(
            session=populated_session, fetcher=fetcher
        )

    assert len(results) == 1
    assert results[0].external_ids["polygon_id"] == "AAPL"


async def test_bootstrap_from_polygon_tickers_is_idempotent(
    populated_session: AsyncSession,
) -> None:
    from app.services.entity_bootstrap.polygon_tickers import (
        PolygonTickerRecord,
        bootstrap_from_polygon_tickers,
    )

    async def fake_fetcher() -> list[PolygonTickerRecord]:
        return [
            PolygonTickerRecord(
                polygon_id="AAPL",
                ticker="AAPL",
                name="Apple Inc.",
                market="stocks",
            )
        ]

    first = await bootstrap_from_polygon_tickers(
        session=populated_session, fetcher=fake_fetcher
    )
    second = await bootstrap_from_polygon_tickers(
        session=populated_session, fetcher=fake_fetcher
    )

    assert first[0].entity_id == second[0].entity_id
