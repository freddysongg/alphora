import json
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.services.source_clients._http import HttpRequestConfig, request
from app.services.source_clients._rate_limit import RateLimiterProtocol
from app.services.source_clients._registry import get_rate_limiter

_POLYMARKET_DATA_BASE = "https://data-api.polymarket.com"

PolymarketDataInterval = Literal["1h", "6h", "1d", "1w"]


def _rate_limiter() -> RateLimiterProtocol:
    return get_rate_limiter(name="polymarket_data", rate_per_second=5.0, burst=10)


class PolymarketPricePoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    timestamp_s: int = Field(alias="t")
    probability: float = Field(alias="p")
    volume_usd: float | None = Field(default=None, alias="v")


class PolymarketPriceHistory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    market: str
    interval: str
    history: list[PolymarketPricePoint]


async def fetch_polymarket_price_history(
    *,
    client: httpx.AsyncClient,
    market: str,
    interval: PolymarketDataInterval = "1d",
    start_ts: int | None = None,
    end_ts: int | None = None,
) -> tuple[PolymarketPriceHistory, str]:
    params: dict[str, str | int | float] = {"market": market, "interval": interval}
    if start_ts is not None:
        params["startTs"] = start_ts
    if end_ts is not None:
        params["endTs"] = end_ts

    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_POLYMARKET_DATA_BASE}/prices-history",
            params=params,
        ),
        rate_limiter=_rate_limiter(),
    )

    payload = json.loads(response.body_bytes)
    if isinstance(payload, list):
        payload = {"market": market, "interval": interval, "history": payload}
    elif isinstance(payload, dict):
        payload.setdefault("market", market)
        payload.setdefault("interval", interval)
    parsed = PolymarketPriceHistory.model_validate(payload)
    return parsed, response.content_hash


__all__ = [
    "PolymarketDataInterval",
    "PolymarketPriceHistory",
    "PolymarketPricePoint",
    "fetch_polymarket_price_history",
]
