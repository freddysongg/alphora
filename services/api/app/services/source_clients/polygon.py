from datetime import date

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.services.source_clients._http import (
    HttpRequestConfig,
    SourceClientConfigError,
    request,
)
from app.services.source_clients._rate_limit import RateLimiterProtocol
from app.services.source_clients._registry import get_rate_limiter

_POLYGON_BASE = "https://api.polygon.io"


def _rate_limiter() -> RateLimiterProtocol:
    return get_rate_limiter(name="polygon", rate_per_second=4.0, burst=5)


class PolygonTicker(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    ticker: str
    name: str
    market: str
    primary_exchange: str | None = None
    active: bool


class PolygonTickersResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    results: list[PolygonTicker]
    status: str
    count: int


class PolygonAggregateBar(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    open: float = Field(alias="o")
    close: float = Field(alias="c")
    high: float = Field(alias="h")
    low: float = Field(alias="l")
    volume: float = Field(alias="v")
    timestamp_ms: int = Field(alias="t")


class PolygonAggregatesResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    ticker: str
    query_count: int = Field(alias="queryCount")
    results_count: int = Field(alias="resultsCount")
    adjusted: bool
    status: str
    results: list[PolygonAggregateBar] = []


async def fetch_polygon_tickers(
    *,
    client: httpx.AsyncClient,
    market: str | None = None,
    limit: int = 100,
) -> tuple[PolygonTickersResponse, str]:
    settings = get_settings()
    if settings.polygon_api_key is None:
        raise SourceClientConfigError(setting_name="polygon_api_key")

    params: dict[str, str | int] = {
        "apiKey": settings.polygon_api_key.get_secret_value(),
        "limit": limit,
    }
    if market is not None:
        params["market"] = market

    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_POLYGON_BASE}/v3/reference/tickers",
            params=params,
        ),
        rate_limiter=_rate_limiter(),
    )
    parsed = PolygonTickersResponse.model_validate_json(response.body_bytes)
    return parsed, response.content_hash


async def fetch_polygon_aggregates(
    *,
    client: httpx.AsyncClient,
    ticker: str,
    multiplier: int,
    timespan: str,
    from_date: date,
    to_date: date,
    adjusted: bool = True,
) -> tuple[PolygonAggregatesResponse, str]:
    settings = get_settings()
    if settings.polygon_api_key is None:
        raise SourceClientConfigError(setting_name="polygon_api_key")

    url = (
        f"{_POLYGON_BASE}/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/"
        f"{from_date.isoformat()}/{to_date.isoformat()}"
    )
    params: dict[str, str | int] = {
        "apiKey": settings.polygon_api_key.get_secret_value(),
        "adjusted": "true" if adjusted else "false",
    }

    response = await request(
        client,
        HttpRequestConfig(method="GET", url=url, params=params),
        rate_limiter=_rate_limiter(),
    )
    parsed = PolygonAggregatesResponse.model_validate_json(response.body_bytes)
    return parsed, response.content_hash


__all__ = [
    "PolygonAggregateBar",
    "PolygonAggregatesResponse",
    "PolygonTicker",
    "PolygonTickersResponse",
    "fetch_polygon_aggregates",
    "fetch_polygon_tickers",
]
