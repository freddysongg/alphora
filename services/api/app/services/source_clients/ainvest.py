from datetime import date

import httpx
from pydantic import BaseModel, ConfigDict

from app.config import get_settings
from app.services.source_clients._http import (
    HttpRequestConfig,
    SourceClientConfigError,
    request,
)
from app.services.source_clients._rate_limit import make_rate_limiter

_AINVEST_BASE = "https://openapi.ainvest.com/open"

_RATE_LIMITER = make_rate_limiter(name="ainvest", rate_per_second=2.0, burst=5)


class AinvestCongressTransaction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    party: str
    state: str
    trade_date: date
    filing_date: date
    reporting_gap: str
    trade_type: str
    size: str


class AinvestCongressData(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    data: list[AinvestCongressTransaction]


class AinvestCongressResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    data: AinvestCongressData
    status_code: int
    status_msg: str


async def fetch_ainvest_congress_transactions(
    *,
    client: httpx.AsyncClient,
    ticker: str,
    page: int | None = None,
    size: int | None = None,
) -> tuple[AinvestCongressResponse, str]:
    settings = get_settings()
    if settings.ainvest_api_key is None:
        raise SourceClientConfigError(setting_name="ainvest_api_key")

    params: dict[str, str | int | float] = {"ticker": ticker}
    if page is not None:
        params["page"] = page
    if size is not None:
        params["size"] = size

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
    parsed = AinvestCongressResponse.model_validate_json(response.body_bytes)
    return parsed, response.content_hash


__all__ = [
    "AinvestCongressData",
    "AinvestCongressResponse",
    "AinvestCongressTransaction",
    "fetch_ainvest_congress_transactions",
]
