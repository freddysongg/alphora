import json
from datetime import datetime

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

_TIINGO_NEWS_URL = "https://api.tiingo.com/tiingo/news"


def _rate_limiter() -> RateLimiterProtocol:
    return get_rate_limiter(name="tiingo_news", rate_per_second=1.0, burst=3)


class TiingoNewsItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int
    title: str
    description: str | None = None
    url: str
    publishedDate: datetime  # noqa: N815 — Tiingo API field
    source: str
    tickers: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


def _authorization_headers() -> dict[str, str]:
    settings = get_settings()
    if settings.tiingo_api_key is None:
        raise SourceClientConfigError(setting_name="tiingo_api_key")
    return {"Authorization": f"Token {settings.tiingo_api_key.get_secret_value()}"}


async def fetch_tiingo_news(
    *,
    client: httpx.AsyncClient,
    tickers: list[str] | None = None,
    limit: int = 50,
) -> tuple[list[TiingoNewsItem], str]:
    headers = _authorization_headers()
    params: dict[str, str | int | float] = {"limit": limit}
    if tickers:
        params["tickers"] = ",".join(tickers)

    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=_TIINGO_NEWS_URL,
            headers=headers,
            params=params,
        ),
        rate_limiter=_rate_limiter(),
    )

    payload = json.loads(response.body_bytes)
    items = [TiingoNewsItem.model_validate(row) for row in payload]
    return items, response.content_hash


__all__ = ["TiingoNewsItem", "fetch_tiingo_news"]
