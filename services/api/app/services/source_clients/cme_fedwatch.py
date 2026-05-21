"""CME FedWatch client.

CME publishes FOMC target-rate probabilities through the FedWatch tool. There
is no documented stable public REST endpoint; the tool's UI loads a JSON
payload from a back-end URL under `cmegroup.com/CmeWS/mvc/...` that CME
rotates without notice.

The client therefore exposes `base_url` as a **required** argument — callers
(production deploys, scrapers, tests) must wire the URL they want to hit.
There is no built-in default because every speculative URL we tried returned
HTTP 404 in production; shipping a default would silently break every
unsuspecting caller. Production wiring is a `Settings` field per deployment.

Output shape is the structured tuple `{as_of, meeting_date,
current_target_low_bps, current_target_high_bps, probabilities:
[{target_low_bps, target_high_bps, probability}]}`. Bands are integer basis
points and probabilities sum to ~1.0 within rounding.
"""
import json
from datetime import date, datetime

import httpx
from pydantic import BaseModel, ConfigDict

from app.services.source_clients._http import HttpRequestConfig, request
from app.services.source_clients._rate_limit import RateLimiterProtocol
from app.services.source_clients._registry import get_rate_limiter


def _rate_limiter() -> RateLimiterProtocol:
    return get_rate_limiter(name="cme_fedwatch", rate_per_second=0.5, burst=2)


class FedWatchProbability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    target_low_bps: int
    target_high_bps: int
    probability: float


class FedWatchMeeting(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    as_of: datetime
    meeting_date: date
    current_target_low_bps: int
    current_target_high_bps: int
    probabilities: list[FedWatchProbability]


async def fetch_cme_fedwatch_probabilities(
    *,
    client: httpx.AsyncClient,
    meeting_date: date,
    base_url: str,
) -> tuple[FedWatchMeeting, str]:
    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=base_url,
            params={"meetingDate": meeting_date.isoformat()},
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; AlphoraResearchBot/1.0)",
            },
        ),
        rate_limiter=_rate_limiter(),
    )

    payload = json.loads(response.body_bytes)
    parsed = FedWatchMeeting.model_validate(payload)
    return parsed, response.content_hash


__all__ = [
    "FedWatchMeeting",
    "FedWatchProbability",
    "fetch_cme_fedwatch_probabilities",
]
