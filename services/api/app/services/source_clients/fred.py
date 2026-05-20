import json
from datetime import date as _date
from decimal import Decimal
from typing import Any

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

_FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
_FRED_MISSING_VALUE_SENTINEL = "."


def _rate_limiter() -> RateLimiterProtocol:
    return get_rate_limiter(name="fred", rate_per_second=2.0, burst=10)


class FredObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    date: _date
    value: Decimal | None
    realtime_start: _date
    realtime_end: _date

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_missing(cls, raw: object) -> object:
        if raw == _FRED_MISSING_VALUE_SENTINEL:
            return None
        return raw


class FredSeriesObservations(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    series_id: str
    observation_start: _date
    observation_end: _date
    count: int
    observations: list[FredObservation]


async def fetch_series_observations(
    *,
    client: httpx.AsyncClient,
    series_id: str,
    observation_start: _date | None = None,
    observation_end: _date | None = None,
) -> tuple[FredSeriesObservations, str]:
    settings = get_settings()
    if settings.fred_api_key is None:
        raise SourceClientConfigError(setting_name="fred_api_key")

    params: dict[str, str] = {
        "api_key": settings.fred_api_key.get_secret_value(),
        "file_type": "json",
        "series_id": series_id,
    }
    if observation_start is not None:
        params["observation_start"] = observation_start.isoformat()
    if observation_end is not None:
        params["observation_end"] = observation_end.isoformat()

    response = await request(
        client,
        HttpRequestConfig(method="GET", url=_FRED_OBSERVATIONS_URL, params=params),
        rate_limiter=_rate_limiter(),
    )

    payload: dict[str, Any] = json.loads(response.body_bytes)
    payload["series_id"] = series_id
    parsed = FredSeriesObservations.model_validate(payload)
    return parsed, response.content_hash
