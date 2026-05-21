import httpx
import pytest
import respx

from app.config import get_settings
from app.services.source_clients._http import SourceClientConfigError


@pytest.mark.asyncio
@respx.mock
async def test_fetch_finnhub_company_news_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    get_settings.cache_clear()
    from app.services.source_clients.finnhub import fetch_finnhub_company_news

    route = respx.get("https://finnhub.io/api/v1/company-news").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "category": "company",
                    "datetime": 1778803200,
                    "headline": "Apple reports Q2 earnings, beats on services",
                    "id": 1234567,
                    "image": "https://example.com/img.jpg",
                    "related": "AAPL",
                    "source": "CNBC",
                    "summary": "Beat by $0.03 with services revenue up 14% YoY.",
                    "url": "https://example.com/aapl",
                }
            ],
        )
    )

    from datetime import date as _date

    async with httpx.AsyncClient() as client:
        items, content_hash = await fetch_finnhub_company_news(
            client=client,
            symbol="AAPL",
            from_date=_date(2026, 5, 1),
            to_date=_date(2026, 5, 18),
        )

    assert route.called
    sent = route.calls.last.request
    assert sent.url.params["symbol"] == "AAPL"
    assert sent.url.params["from"] == "2026-05-01"
    assert sent.url.params["to"] == "2026-05-18"
    assert sent.headers["x-finnhub-token"] == "test-key"
    assert len(items) == 1
    assert items[0].headline == "Apple reports Q2 earnings, beats on services"
    assert items[0].published_at.year == 2026
    assert items[0].published_at.tzinfo is not None
    assert items[0].related == "AAPL"
    assert len(content_hash) == 64


@pytest.mark.asyncio
async def test_fetch_finnhub_company_news_missing_key_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    get_settings.cache_clear()
    from datetime import date as _date

    from app.services.source_clients.finnhub import fetch_finnhub_company_news

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientConfigError):
            await fetch_finnhub_company_news(
                client=client,
                symbol="AAPL",
                from_date=_date(2026, 5, 1),
                to_date=_date(2026, 5, 18),
            )


@pytest.mark.asyncio
@respx.mock
async def test_fetch_finnhub_company_news_accepts_pre_mapped_published_at(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    get_settings.cache_clear()

    respx.get("https://finnhub.io/api/v1/company-news").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "category": "company",
                    "headline": "h",
                    "source": "s",
                    "url": "https://example.com",
                    "published_at": "2026-05-18T14:00:00Z",
                }
            ],
        )
    )
    from datetime import date as _date

    from app.services.source_clients.finnhub import fetch_finnhub_company_news

    async with httpx.AsyncClient() as client:
        items, _ = await fetch_finnhub_company_news(
            client=client,
            symbol="AAPL",
            from_date=_date(2026, 5, 1),
            to_date=_date(2026, 5, 18),
        )

    assert items[0].published_at.year == 2026


@pytest.mark.asyncio
@respx.mock
async def test_fetch_finnhub_earnings_calendar_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    get_settings.cache_clear()
    from app.services.source_clients.finnhub import fetch_finnhub_earnings_calendar

    route = respx.get("https://finnhub.io/api/v1/calendar/earnings").mock(
        return_value=httpx.Response(
            200,
            json={
                "earnings": [
                    {
                        "symbol": "AAPL",
                        "date": "2026-04-30",
                        "epsActual": 1.53,
                        "epsEstimate": 1.50,
                        "revenueActual": 89000000000,
                        "revenueEstimate": 88500000000,
                        "hour": "amc",
                        "quarter": 2,
                        "year": 2026,
                    }
                ]
            },
        )
    )
    from datetime import date as _date

    async with httpx.AsyncClient() as client:
        result, _ = await fetch_finnhub_earnings_calendar(
            client=client,
            from_date=_date(2026, 4, 1),
            to_date=_date(2026, 5, 1),
            symbol="AAPL",
        )

    assert route.called
    sent = route.calls.last.request
    assert sent.url.params["symbol"] == "AAPL"
    assert sent.url.params["from"] == "2026-04-01"
    assert sent.url.params["to"] == "2026-05-01"
    assert len(result.earnings) == 1
    assert result.earnings[0].symbol == "AAPL"
    assert result.earnings[0].hour == "amc"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_finnhub_company_news_500_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    get_settings.cache_clear()
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.finnhub import fetch_finnhub_company_news

    route = respx.get("https://finnhub.io/api/v1/company-news").mock(
        return_value=httpx.Response(500)
    )
    from datetime import date as _date

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError):
            await fetch_finnhub_company_news(
                client=client,
                symbol="AAPL",
                from_date=_date(2026, 5, 1),
                to_date=_date(2026, 5, 18),
            )

    assert route.call_count == 4


def test_finnhub_module_exposes_lazy_rate_limiter() -> None:
    from app.services.source_clients import finnhub
    from app.services.source_clients._rate_limit import LocalTokenBucket
    from app.services.source_clients._registry import reset_registry

    reset_registry()
    limiter = finnhub._rate_limiter()
    assert isinstance(limiter, LocalTokenBucket)
    assert finnhub._rate_limiter() is limiter


@pytest.mark.asyncio
@respx.mock
async def test_fetch_finnhub_recommendation_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    get_settings.cache_clear()
    from app.services.source_clients.finnhub import fetch_finnhub_recommendation

    route = respx.get("https://finnhub.io/api/v1/stock/recommendation").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "symbol": "AAPL",
                    "period": "2026-05-01",
                    "buy": 25,
                    "hold": 8,
                    "sell": 2,
                    "strongBuy": 15,
                    "strongSell": 1,
                },
                {
                    "symbol": "AAPL",
                    "period": "2026-04-01",
                    "buy": 22,
                    "hold": 9,
                    "sell": 3,
                    "strongBuy": 14,
                    "strongSell": 1,
                },
            ],
        )
    )

    async with httpx.AsyncClient() as client:
        items, content_hash = await fetch_finnhub_recommendation(client=client, symbol="AAPL")

    assert route.called
    sent = route.calls.last.request
    assert sent.url.params["symbol"] == "AAPL"
    assert sent.headers["x-finnhub-token"] == "test-key"
    assert len(items) == 2
    assert items[0].period.year == 2026
    assert items[0].buy == 25
    assert items[0].strong_buy == 15
    assert len(content_hash) == 64


@pytest.mark.asyncio
@respx.mock
async def test_fetch_finnhub_price_target_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    get_settings.cache_clear()
    from app.services.source_clients.finnhub import fetch_finnhub_price_target

    route = respx.get("https://finnhub.io/api/v1/stock/price-target").mock(
        return_value=httpx.Response(
            200,
            json={
                "symbol": "AAPL",
                "lastUpdated": "2026-05-18 14:30:00",
                "targetHigh": 250.0,
                "targetLow": 175.0,
                "targetMean": 215.0,
                "targetMedian": 210.0,
                "numberOfAnalysts": 38,
            },
        )
    )

    async with httpx.AsyncClient() as client:
        target, content_hash = await fetch_finnhub_price_target(client=client, symbol="AAPL")

    assert route.called
    assert target.symbol == "AAPL"
    assert target.target_high == 250.0
    assert target.target_median == 210.0
    assert target.number_of_analysts == 38
    assert target.last_updated.year == 2026
    assert len(content_hash) == 64
