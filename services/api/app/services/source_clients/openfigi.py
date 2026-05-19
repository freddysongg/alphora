import hashlib
import json

import httpx
from pydantic import BaseModel, ConfigDict

from app.config import get_settings
from app.services.source_clients._http import (
    SourceClientHTTPError,
    SourceClientTimeoutError,
)
from app.services.source_clients._rate_limit import make_rate_limiter

_OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
_DEFAULT_TIMEOUT_SECONDS = 30.0

_RATE_LIMITER = make_rate_limiter(name="openfigi", rate_per_second=4.0, burst=5)


class OpenFigiResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    figi: str
    name: str | None = None
    ticker: str | None = None
    exchCode: str | None = None  # noqa: N815 — OpenFIGI API field


class OpenFigiMappingResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    data: list[OpenFigiResult] | None = None
    warning: str | None = None
    error: str | None = None


def _build_headers() -> dict[str, str]:
    settings = get_settings()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if settings.openfigi_api_key is not None:
        headers["X-OPENFIGI-APIKEY"] = settings.openfigi_api_key.get_secret_value()
    return headers


async def fetch_openfigi_mapping(
    *,
    client: httpx.AsyncClient,
    queries: list[dict[str, str]],
) -> tuple[list[OpenFigiMappingResponse], str]:
    await _RATE_LIMITER.acquire()

    try:
        httpx_response = await client.request(
            method="POST",
            url=_OPENFIGI_URL,
            json=queries,
            headers=_build_headers(),
            timeout=_DEFAULT_TIMEOUT_SECONDS,
        )
    except httpx.TransportError as exc:
        raise SourceClientTimeoutError(url=_OPENFIGI_URL) from exc

    body = httpx_response.content
    status = httpx_response.status_code

    if not (200 <= status < 400):
        raise SourceClientHTTPError(
            status_code=status,
            url=_OPENFIGI_URL,
            body_excerpt=body.decode("utf-8", errors="replace")[:512],
        )

    content_hash = hashlib.sha256(body).hexdigest()
    payload = json.loads(body)
    results = [OpenFigiMappingResponse.model_validate(row) for row in payload]
    return results, content_hash


__all__ = [
    "OpenFigiMappingResponse",
    "OpenFigiResult",
    "fetch_openfigi_mapping",
]
