from datetime import datetime

import httpx
from pydantic import BaseModel, ConfigDict

from app.services.source_clients._http import HttpRequestConfig, request
from app.services.source_clients._rate_limit import RateLimiter

_KALSHI_PUBLIC_BASE = "https://external-api.kalshi.com/trade-api/v2"

_RATE_LIMITER = RateLimiter(rate_per_second=8.0, burst=5)


class KalshiMarket(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    ticker: str
    event_ticker: str
    title: str
    status: str
    yes_bid: int | None = None
    yes_ask: int | None = None
    open_time: datetime
    close_time: datetime
    volume: int | None = None


class KalshiMarketsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    markets: list[KalshiMarket]
    cursor: str | None = None


class KalshiMarketDetailResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    market: KalshiMarket


async def fetch_kalshi_markets(
    *,
    client: httpx.AsyncClient,
    cursor: str | None = None,
    limit: int | None = None,
    series_ticker: str | None = None,
    event_ticker: str | None = None,
    status: str | None = None,
) -> tuple[KalshiMarketsResponse, str]:
    params: dict[str, str | int | float] = {}
    if cursor is not None:
        params["cursor"] = cursor
    if limit is not None:
        params["limit"] = limit
    if series_ticker is not None:
        params["series_ticker"] = series_ticker
    if event_ticker is not None:
        params["event_ticker"] = event_ticker
    if status is not None:
        params["status"] = status

    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_KALSHI_PUBLIC_BASE}/markets",
            params=params or None,
        ),
        rate_limiter=_RATE_LIMITER,
    )
    parsed = KalshiMarketsResponse.model_validate_json(response.body_bytes)
    return parsed, response.content_hash


async def fetch_kalshi_market_detail(
    *, client: httpx.AsyncClient, ticker: str
) -> tuple[KalshiMarketDetailResponse, str]:
    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_KALSHI_PUBLIC_BASE}/markets/{ticker}",
        ),
        rate_limiter=_RATE_LIMITER,
    )
    parsed = KalshiMarketDetailResponse.model_validate_json(response.body_bytes)
    return parsed, response.content_hash


__all__ = [
    "KalshiMarket",
    "KalshiMarketDetailResponse",
    "KalshiMarketsResponse",
    "fetch_kalshi_market_detail",
    "fetch_kalshi_markets",
]
