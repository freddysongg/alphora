from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, model_validator

from app.config import get_settings
from app.services.source_clients._http import (
    HttpRequestConfig,
    SourceClientConfigError,
    request,
)
from app.services.source_clients._rate_limit import RateLimiter

_AINVEST_BASE = "https://api.openledger.com/api/v1"

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

    @model_validator(mode="before")
    @classmethod
    def _unwrap_data_envelope(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "transactions" in data:
            return data
        outer = data.get("data")
        if isinstance(outer, dict):
            rows = outer.get("data", [])
            count = outer.get("count", len(rows) if isinstance(rows, list) else 0)
            return {"transactions": rows, "count": count}
        return data


async def fetch_ainvest_congress_transactions(
    *,
    client: httpx.AsyncClient,
    ticker: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[AinvestCongressTransactionsResponse, str]:
    settings = get_settings()
    if settings.ainvest_api_key is None:
        raise SourceClientConfigError(setting_name="ainvest_api_key")

    params: dict[str, str | int | float] = {"ticker": ticker}
    if start_date is not None:
        params["start_date"] = start_date.isoformat()
    if end_date is not None:
        params["end_date"] = end_date.isoformat()

    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_AINVEST_BASE}/ownership/congress",
            headers={
                "Authorization": f"Bearer {settings.ainvest_api_key.get_secret_value()}"
            },
            params=params,
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
