import json
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.source_clients._http import HttpRequestConfig, request
from app.services.source_clients._rate_limit import make_rate_limiter

_POLYMARKET_GAMMA_BASE = "https://gamma-api.polymarket.com"

_RATE_LIMITER = make_rate_limiter(name="polymarket", rate_per_second=5.0, burst=10)


class PolymarketEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    slug: str
    title: str
    active: bool | None = None
    closed: bool | None = None
    category: str | None = None


class PolymarketMarket(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="ignore", populate_by_name=True
    )

    id: str
    question: str
    slug: str
    outcomes: list[str] = []
    outcome_prices: list[str] = Field(default_factory=list, alias="outcomePrices")
    volume: str | None = None
    liquidity: str | None = None
    active: bool | None = None
    closed: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def _decode_json_encoded_arrays(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        result = dict(data)
        for key in ("outcomes", "outcomePrices"):
            value = result.get(key)
            if isinstance(value, str):
                try:
                    result[key] = json.loads(value)
                except json.JSONDecodeError:
                    result[key] = []
        return result


def _bool_param(value: bool) -> str:
    return "true" if value else "false"


async def fetch_polymarket_events(
    *,
    client: httpx.AsyncClient,
    limit: int | None = None,
    offset: int | None = None,
    active: bool | None = None,
    closed: bool | None = None,
) -> tuple[list[PolymarketEvent], str]:
    params: dict[str, str | int | float] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    if active is not None:
        params["active"] = _bool_param(active)
    if closed is not None:
        params["closed"] = _bool_param(closed)

    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_POLYMARKET_GAMMA_BASE}/events",
            params=params or None,
        ),
        rate_limiter=_RATE_LIMITER,
    )

    payload = json.loads(response.body_bytes)
    events = [PolymarketEvent.model_validate(row) for row in payload]
    return events, response.content_hash


async def fetch_polymarket_markets(
    *,
    client: httpx.AsyncClient,
    limit: int | None = None,
    offset: int | None = None,
    active: bool | None = None,
    closed: bool | None = None,
) -> tuple[list[PolymarketMarket], str]:
    params: dict[str, str | int | float] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    if active is not None:
        params["active"] = _bool_param(active)
    if closed is not None:
        params["closed"] = _bool_param(closed)

    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_POLYMARKET_GAMMA_BASE}/markets",
            params=params or None,
        ),
        rate_limiter=_RATE_LIMITER,
    )

    payload = json.loads(response.body_bytes)
    markets = [PolymarketMarket.model_validate(row) for row in payload]
    return markets, response.content_hash


__all__ = [
    "PolymarketEvent",
    "PolymarketMarket",
    "fetch_polymarket_events",
    "fetch_polymarket_markets",
]
