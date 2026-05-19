import json
from datetime import date, datetime
from decimal import Decimal

import httpx
from pydantic import BaseModel, ConfigDict

from app.config import get_settings
from app.services.source_clients._http import (
    HttpRequestConfig,
    SourceClientConfigError,
    request,
)
from app.services.source_clients._rate_limit import RateLimiter

_TIINGO_BASE = "https://api.tiingo.com"

_RATE_LIMITER = RateLimiter(rate_per_second=1.0, burst=3)


class TiingoIexQuote(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    ticker: str
    last: Decimal | None = None
    timestamp: datetime
    askPrice: Decimal | None = None  # noqa: N815 — Tiingo API field
    bidPrice: Decimal | None = None  # noqa: N815 — Tiingo API field
    volume: int | None = None


class TiingoDailyPriceRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    date: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    adjClose: Decimal | None = None  # noqa: N815 — Tiingo API field


def _authorization_headers() -> dict[str, str]:
    settings = get_settings()
    if settings.tiingo_api_key is None:
        raise SourceClientConfigError(setting_name="tiingo_api_key")
    return {"Authorization": f"Token {settings.tiingo_api_key.get_secret_value()}"}


async def fetch_tiingo_latest(
    *, client: httpx.AsyncClient, ticker: str
) -> tuple[list[TiingoIexQuote], str]:
    headers = _authorization_headers()

    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_TIINGO_BASE}/iex/{ticker}",
            headers=headers,
        ),
        rate_limiter=_RATE_LIMITER,
    )

    payload = json.loads(response.body_bytes)
    quotes = [TiingoIexQuote.model_validate(row) for row in payload]
    return quotes, response.content_hash


async def fetch_tiingo_daily_prices(
    *,
    client: httpx.AsyncClient,
    ticker: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[list[TiingoDailyPriceRow], str]:
    headers = _authorization_headers()

    params: dict[str, str | int | float] = {}
    if start_date is not None:
        params["startDate"] = start_date.isoformat()
    if end_date is not None:
        params["endDate"] = end_date.isoformat()

    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_TIINGO_BASE}/tiingo/daily/{ticker}/prices",
            headers=headers,
            params=params or None,
        ),
        rate_limiter=_RATE_LIMITER,
    )

    payload = json.loads(response.body_bytes)
    rows = [TiingoDailyPriceRow.model_validate(row) for row in payload]
    return rows, response.content_hash


__all__ = [
    "TiingoDailyPriceRow",
    "TiingoIexQuote",
    "fetch_tiingo_daily_prices",
    "fetch_tiingo_latest",
]
