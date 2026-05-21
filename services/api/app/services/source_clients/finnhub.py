import json
from datetime import UTC, date, datetime

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class FinnhubRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    symbol: str
    period: date
    buy: int
    hold: int
    sell: int
    strong_buy: int = Field(alias="strongBuy")
    strong_sell: int = Field(alias="strongSell")


class FinnhubPriceTarget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    symbol: str
    last_updated: datetime = Field(alias="lastUpdated")
    target_high: float = Field(alias="targetHigh")
    target_low: float = Field(alias="targetLow")
    target_mean: float = Field(alias="targetMean")
    target_median: float = Field(alias="targetMedian")
    number_of_analysts: int = Field(alias="numberOfAnalysts")

    @field_validator("last_updated", mode="before")
    @classmethod
    def _coerce_naive_datetime(cls, raw: object) -> object:
        if isinstance(raw, str) and "T" not in raw and raw.count(" ") == 1:
            return datetime.fromisoformat(raw.replace(" ", "T")).replace(tzinfo=UTC)
        return raw


class FinnhubInsiderTransaction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    name: str
    share: int
    change: int
    filing_date: date = Field(alias="filingDate")
    transaction_date: date = Field(alias="transactionDate")
    transaction_code: str = Field(alias="transactionCode")
    transaction_price: float | None = Field(default=None, alias="transactionPrice")


class FinnhubInsiderTransactionsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    symbol: str
    data: list[FinnhubInsiderTransaction]


class FinnhubCompanyProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    country: str | None = None
    currency: str | None = None
    exchange: str | None = None
    finnhub_industry: str | None = Field(default=None, alias="finnhubIndustry")
    ipo: date | None = None
    logo: str | None = None
    market_capitalization: float | None = Field(default=None, alias="marketCapitalization")
    name: str | None = None
    phone: str | None = None
    share_outstanding: float | None = Field(default=None, alias="shareOutstanding")
    ticker: str | None = None
    weburl: str | None = None


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


async def fetch_finnhub_recommendation(
    *,
    client: httpx.AsyncClient,
    symbol: str,
) -> tuple[list[FinnhubRecommendation], str]:
    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_FINNHUB_BASE}/stock/recommendation",
            headers=_auth_headers(),
            params={"symbol": symbol},
        ),
        rate_limiter=_rate_limiter(),
    )

    payload = json.loads(response.body_bytes)
    items = [FinnhubRecommendation.model_validate(row) for row in payload]
    return items, response.content_hash


async def fetch_finnhub_price_target(
    *,
    client: httpx.AsyncClient,
    symbol: str,
) -> tuple[FinnhubPriceTarget, str]:
    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_FINNHUB_BASE}/stock/price-target",
            headers=_auth_headers(),
            params={"symbol": symbol},
        ),
        rate_limiter=_rate_limiter(),
    )
    target = FinnhubPriceTarget.model_validate_json(response.body_bytes)
    return target, response.content_hash


async def fetch_finnhub_insider_transactions(
    *,
    client: httpx.AsyncClient,
    symbol: str,
    from_date: date,
    to_date: date,
) -> tuple[FinnhubInsiderTransactionsResponse, str]:
    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_FINNHUB_BASE}/stock/insider-transactions",
            headers=_auth_headers(),
            params={
                "symbol": symbol,
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
            },
        ),
        rate_limiter=_rate_limiter(),
    )
    parsed = FinnhubInsiderTransactionsResponse.model_validate_json(response.body_bytes)
    return parsed, response.content_hash


async def fetch_finnhub_peers(
    *,
    client: httpx.AsyncClient,
    symbol: str,
) -> tuple[list[str], str]:
    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_FINNHUB_BASE}/stock/peers",
            headers=_auth_headers(),
            params={"symbol": symbol},
        ),
        rate_limiter=_rate_limiter(),
    )
    payload = json.loads(response.body_bytes)
    return [str(t) for t in payload], response.content_hash


async def fetch_finnhub_profile(
    *,
    client: httpx.AsyncClient,
    symbol: str,
) -> tuple[FinnhubCompanyProfile, str]:
    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_FINNHUB_BASE}/stock/profile2",
            headers=_auth_headers(),
            params={"symbol": symbol},
        ),
        rate_limiter=_rate_limiter(),
    )
    profile = FinnhubCompanyProfile.model_validate_json(response.body_bytes)
    return profile, response.content_hash


__all__ = [
    "FinnhubCompanyProfile",
    "FinnhubEarningsCalendar",
    "FinnhubEarningsRow",
    "FinnhubInsiderTransaction",
    "FinnhubInsiderTransactionsResponse",
    "FinnhubNewsItem",
    "FinnhubPriceTarget",
    "FinnhubRecommendation",
    "fetch_finnhub_company_news",
    "fetch_finnhub_earnings_calendar",
    "fetch_finnhub_insider_transactions",
    "fetch_finnhub_peers",
    "fetch_finnhub_price_target",
    "fetch_finnhub_profile",
    "fetch_finnhub_recommendation",
]
