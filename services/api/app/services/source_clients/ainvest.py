from datetime import date

import httpx
from pydantic import BaseModel, ConfigDict

from app.config import get_settings
from app.services.source_clients._http import (
    HttpRequestConfig,
    SourceClientConfigError,
    request,
)
from app.services.source_clients._rate_limit import RateLimiter

_AINVEST_BASE = "https://api.ainvest.com"

_RATE_LIMITER = RateLimiter(rate_per_second=2.0, burst=5)


class AinvestCongressTransaction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    member_name: str
    bioguide_id: str | None = None
    transaction_date: date
    asset_ticker: str | None = None
    asset_name: str
    transaction_type: str
    amount_range: str


class AinvestCongressTransactionsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    transactions: list[AinvestCongressTransaction]
    count: int


async def fetch_ainvest_congress_transactions(
    *,
    client: httpx.AsyncClient,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[AinvestCongressTransactionsResponse, str]:
    settings = get_settings()
    if settings.ainvest_api_key is None:
        raise SourceClientConfigError(setting_name="ainvest_api_key")

    params: dict[str, str | int | float] = {}
    if start_date is not None:
        params["start_date"] = start_date.isoformat()
    if end_date is not None:
        params["end_date"] = end_date.isoformat()

    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_AINVEST_BASE}/v1/congress/transactions",
            headers={"X-API-KEY": settings.ainvest_api_key.get_secret_value()},
            params=params or None,
        ),
        rate_limiter=_RATE_LIMITER,
    )
    parsed = AinvestCongressTransactionsResponse.model_validate_json(
        response.body_bytes
    )
    return parsed, response.content_hash


__all__ = [
    "AinvestCongressTransaction",
    "AinvestCongressTransactionsResponse",
    "fetch_ainvest_congress_transactions",
]
