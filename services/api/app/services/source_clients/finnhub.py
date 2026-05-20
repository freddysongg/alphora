import json
from datetime import UTC, date, datetime

import httpx
from pydantic import BaseModel, ConfigDict, field_validator

from app.config import get_settings
from app.services.source_clients._http import (
    HttpRequestConfig,
    SourceClientConfigError,
    request,
)
from app.services.source_clients._rate_limit import RateLimiterProtocol
from app.services.source_clients._registry import get_rate_limiter

_FINNHUB_BASE = "https://finnhub.io/api/v1"


def _rate_limiter() -> RateLimiterProtocol:
    return get_rate_limiter(name="finnhub", rate_per_second=1.0, burst=5)


def _auth_headers() -> dict[str, str]:
    settings = get_settings()
    if settings.finnhub_api_key is None:
        raise SourceClientConfigError(setting_name="finnhub_api_key")
    return {"X-Finnhub-Token": settings.finnhub_api_key.get_secret_value()}


class FinnhubNewsItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int
    category: str
    headline: str
    summary: str | None = None
    source: str
    url: str
    image: str | None = None
    related: str | None = None
    published_at: datetime

    @field_validator("published_at", mode="before")
    @classmethod
    def _coerce_epoch_seconds(cls, raw: object) -> object:
        if isinstance(raw, int | float):
            return datetime.fromtimestamp(float(raw), tz=UTC)
        return raw


class FinnhubEarningsRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    symbol: str
    date: date
    eps_actual: float | None = None
    eps_estimate: float | None = None
    revenue_actual: float | None = None
    revenue_estimate: float | None = None
    hour: str | None = None
    quarter: int | None = None
    year: int | None = None


class FinnhubEarningsCalendar(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    earnings: list[FinnhubEarningsRow]


def _remap_news_row(row: object) -> FinnhubNewsItem:
    """Finnhub returns `datetime` as epoch seconds at the top level. Map it to
    `published_at` so the public model uses an explicit, non-shadowing name.
    """
    if not isinstance(row, dict):
        return FinnhubNewsItem.model_validate(row)
    if "published_at" in row:
        return FinnhubNewsItem.model_validate(row)
    remapped = dict(row)
    if "datetime" in remapped:
        remapped["published_at"] = remapped.pop("datetime")
    return FinnhubNewsItem.model_validate(remapped)


async def fetch_finnhub_company_news(
    *,
    client: httpx.AsyncClient,
    symbol: str,
    from_date: date,
    to_date: date,
) -> tuple[list[FinnhubNewsItem], str]:
    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_FINNHUB_BASE}/company-news",
            headers=_auth_headers(),
            params={
                "symbol": symbol,
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
            },
        ),
        rate_limiter=_rate_limiter(),
    )

    payload = json.loads(response.body_bytes)
    items = [_remap_news_row(row) for row in payload]
    return items, response.content_hash


async def fetch_finnhub_earnings_calendar(
    *,
    client: httpx.AsyncClient,
    from_date: date,
    to_date: date,
    symbol: str | None = None,
) -> tuple[FinnhubEarningsCalendar, str]:
    params: dict[str, str | int | float] = {
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
    }
    if symbol is not None:
        params["symbol"] = symbol

    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_FINNHUB_BASE}/calendar/earnings",
            headers=_auth_headers(),
            params=params,
        ),
        rate_limiter=_rate_limiter(),
    )

    parsed = FinnhubEarningsCalendar.model_validate_json(response.body_bytes)
    return parsed, response.content_hash


__all__ = [
    "FinnhubEarningsCalendar",
    "FinnhubEarningsRow",
    "FinnhubNewsItem",
    "fetch_finnhub_company_news",
    "fetch_finnhub_earnings_calendar",
]
