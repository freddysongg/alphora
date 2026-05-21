"""GDELT 2.0 DOC API client.

GDELT indexes global news in near-real time. The DOC API
(`api.gdeltproject.org/api/v2/doc/doc`) accepts a `query` string in GDELT's
custom syntax and returns matching articles in JSON when `mode=ArtList&format=json`.

Each article carries a `seendate` string in `YYYYMMDDTHHMMSSZ` compact form and a
GDELT taxonomy `themes` field which may be either a list (newer responses) or a
semicolon-delimited string (older responses); the field validator collapses
both shapes to a `list[str]`.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, field_validator

from app.services.source_clients._http import HttpRequestConfig, request
from app.services.source_clients._rate_limit import RateLimiterProtocol
from app.services.source_clients._registry import get_rate_limiter

_GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
_USER_AGENT = "Mozilla/5.0 (compatible; AlphoraResearchBot/1.0)"


def _rate_limiter() -> RateLimiterProtocol:
    return get_rate_limiter(name="gdelt", rate_per_second=0.2, burst=2)


class GdeltArticle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    url: str
    title: str
    seendate: datetime
    domain: str | None = None
    language: str | None = None
    sourcecountry: str | None = None
    tone: float | None = None
    themes: list[str] = []

    @field_validator("seendate", mode="before")
    @classmethod
    def _parse_compact_timestamp(cls, raw: Any) -> Any:
        if isinstance(raw, str) and "T" in raw and raw.endswith("Z") and "-" not in raw:
            return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        return raw

    @field_validator("themes", mode="before")
    @classmethod
    def _coerce_themes(cls, raw: Any) -> Any:
        if raw is None:
            return []
        if isinstance(raw, list):
            return [str(t) for t in raw if t]
        if isinstance(raw, str):
            return [t for t in (chunk.strip() for chunk in raw.split(";")) if t]
        return raw


class GdeltDocResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    articles: list[GdeltArticle]


async def fetch_gdelt_articles(
    *,
    client: httpx.AsyncClient,
    query: str,
    max_records: int = 75,
    start_datetime: datetime | None = None,
    end_datetime: datetime | None = None,
    sort: str = "datedesc",
) -> tuple[GdeltDocResponse, str]:
    if max_records > 250:
        raise ValueError("GDELT DOC API caps maxrecords at 250 per request")

    params: dict[str, str | int | float] = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": max_records,
        "sort": sort,
    }
    if start_datetime is not None:
        params["startdatetime"] = start_datetime.strftime("%Y%m%d%H%M%S")
    if end_datetime is not None:
        params["enddatetime"] = end_datetime.strftime("%Y%m%d%H%M%S")

    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=_GDELT_DOC_URL,
            params=params,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        ),
        rate_limiter=_rate_limiter(),
    )

    payload = json.loads(response.body_bytes)
    if isinstance(payload, dict):
        payload.setdefault("articles", [])
    else:
        payload = {"articles": []}
    parsed = GdeltDocResponse.model_validate(payload)
    return parsed, response.content_hash


__all__ = [
    "GdeltArticle",
    "GdeltDocResponse",
    "fetch_gdelt_articles",
]
