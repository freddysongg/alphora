"""Capitol Trades client (Ainvest congress fallback).

Capitol Trades does not publish a documented public REST endpoint with a
stable URL — production data lives behind their internal BFF service and is
fronted by HTML pages that change quarterly. Rather than ship a speculative
default that 404s in production, `fetch_capitol_trades` takes a required
`base_url` argument; the caller wires it through Settings (or a deployment
config) the same way CME FedWatch does. Tests pass a mocked URL so the
adapter shape is exercised without depending on the real endpoint.
"""
import json
from datetime import date

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.services.source_clients._http import HttpRequestConfig, request
from app.services.source_clients._rate_limit import RateLimiterProtocol
from app.services.source_clients._registry import get_rate_limiter


def _rate_limiter() -> RateLimiterProtocol:
    return get_rate_limiter(name="capitol_trades", rate_per_second=1.0, burst=3)


class CapitolTradesPolitician(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    party: str | None = None
    chamber: str | None = None
    state: str | None = None


class CapitolTradesIssuer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    ticker: str | None = None
    name: str | None = None


class CapitolTradesTrade(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    trade_id: str
    politician: CapitolTradesPolitician
    issuer: CapitolTradesIssuer
    traded_at: date
    filed_at: date
    reporting_gap_days: int | None = None
    transaction_type: str
    amount_range_usd: list[int] = Field(default_factory=list)
    owner: str | None = None
    source_url: str | None = None


class CapitolTradesResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    page: int | None = None
    page_size: int | None = None
    total_count: int | None = None
    trades: list[CapitolTradesTrade]


async def fetch_capitol_trades(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    ticker: str | None = None,
    politician_id: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> tuple[CapitolTradesResponse, str]:
    params: dict[str, str | int | float] = {}
    if ticker is not None:
        params["ticker"] = ticker
    if politician_id is not None:
        params["politician"] = politician_id
    if page is not None:
        params["page"] = page
    if page_size is not None:
        params["pageSize"] = page_size

    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=base_url,
            params=params or None,
        ),
        rate_limiter=_rate_limiter(),
    )

    payload = json.loads(response.body_bytes)
    parsed = CapitolTradesResponse.model_validate(payload)
    return parsed, response.content_hash


__all__ = [
    "CapitolTradesIssuer",
    "CapitolTradesPolitician",
    "CapitolTradesResponse",
    "CapitolTradesTrade",
    "fetch_capitol_trades",
]
