from datetime import datetime

import httpx
from pydantic import BaseModel, ConfigDict

from app.config import get_settings
from app.services.source_clients._http import (
    HttpRequestConfig,
    SourceClientConfigError,
    request,
)
from app.services.source_clients._rate_limit import RateLimiterProtocol
from app.services.source_clients._registry import get_rate_limiter

_CONGRESS_BASE = "https://api.congress.gov/v3"


def _rate_limiter() -> RateLimiterProtocol:
    return get_rate_limiter(name="congress_gov", rate_per_second=1.0, burst=5)


class CongressBill(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    congress: int
    type: str
    number: str
    title: str | None = None
    updateDate: datetime | None = None  # noqa: N815 — Congress API field


class CongressBillsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    bills: list[CongressBill]


class CongressMember(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    bioguideId: str  # noqa: N815 — Congress API field
    name: str
    state: str | None = None
    partyName: str | None = None  # noqa: N815 — Congress API field


class CongressMembersResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    members: list[CongressMember]


def _base_params() -> dict[str, str | int | float]:
    settings = get_settings()
    if settings.congress_api_key is None:
        raise SourceClientConfigError(setting_name="congress_api_key")
    return {
        "api_key": settings.congress_api_key.get_secret_value(),
        "format": "json",
    }


async def fetch_congress_bills(
    *,
    client: httpx.AsyncClient,
    congress: int | None = None,
    bill_type: str | None = None,
    limit: int | None = None,
) -> tuple[CongressBillsResponse, str]:
    params = _base_params()
    if limit is not None:
        params["limit"] = limit

    parts = [f"{_CONGRESS_BASE}/bill"]
    if congress is not None:
        parts.append(str(congress))
        if bill_type is not None:
            parts.append(bill_type)
    url = "/".join(parts)

    response = await request(
        client,
        HttpRequestConfig(method="GET", url=url, params=params),
        rate_limiter=_rate_limiter(),
    )
    parsed = CongressBillsResponse.model_validate_json(response.body_bytes)
    return parsed, response.content_hash


async def fetch_congress_members(
    *,
    client: httpx.AsyncClient,
    state_code: str | None = None,
    limit: int | None = None,
) -> tuple[CongressMembersResponse, str]:
    params = _base_params()
    if limit is not None:
        params["limit"] = limit

    url = f"{_CONGRESS_BASE}/member"
    if state_code is not None:
        url = f"{url}/{state_code}"

    response = await request(
        client,
        HttpRequestConfig(method="GET", url=url, params=params),
        rate_limiter=_rate_limiter(),
    )
    parsed = CongressMembersResponse.model_validate_json(response.body_bytes)
    return parsed, response.content_hash


__all__ = [
    "CongressBill",
    "CongressBillsResponse",
    "CongressMember",
    "CongressMembersResponse",
    "fetch_congress_bills",
    "fetch_congress_members",
]
