import asyncio
import hashlib
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx


class SourceClientError(Exception):
    """Base for all source-client errors."""


class SourceClientHTTPError(SourceClientError):
    """Non-retryable HTTP failure (4xx other than 429, or 5xx after retries)."""

    def __init__(self, *, status_code: int, url: str, body_excerpt: str) -> None:
        super().__init__(
            f"HTTP {status_code} from {url}: {body_excerpt[:200]}"
        )
        self.status_code = status_code
        self.url = url
        self.body_excerpt = body_excerpt


class SourceClientTimeoutError(SourceClientError):
    """Connect or read timeout after retries."""

    def __init__(self, *, url: str) -> None:
        super().__init__(f"timeout calling {url}")
        self.url = url


class SourceClientRateLimitError(SourceClientError):
    """429 after retries exhausted."""

    def __init__(self, *, url: str, retry_after_seconds: float | None) -> None:
        super().__init__(
            f"rate limited by {url} (retry_after={retry_after_seconds})"
        )
        self.url = url
        self.retry_after_seconds = retry_after_seconds


class SourceClientConfigError(SourceClientError):
    """Raised when a required key/setting is missing at call time."""

    def __init__(self, *, setting_name: str) -> None:
        super().__init__(f"required setting '{setting_name}' is not configured")
        self.setting_name = setting_name


@dataclass(frozen=True)
class HttpRequestConfig:
    method: Literal["GET", "POST"]
    url: str
    params: Mapping[str, str | int | float] | None = None
    headers: Mapping[str, str] | None = None
    json_body: Mapping[str, object] | None = None
    timeout_seconds: float = 30.0
    max_retries: int = 3
    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 8.0


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    body_bytes: bytes
    headers: Mapping[str, str]
    content_hash: str
    url: str


_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


class _RateLimiterProtocol(Protocol):
    async def acquire(self) -> None: ...


def _full_jitter(max_seconds: float) -> float:
    return random.uniform(0.0, max_seconds)


def _parse_retry_after(headers: httpx.Headers) -> float | None:
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _backoff_seconds(
    *, attempt: int, base: float, max_seconds: float, jitter: Callable[[float], float]
) -> float:
    cap = min(max_seconds, base * (2**attempt))
    return jitter(cap)


def _excerpt(body_bytes: bytes) -> str:
    return body_bytes.decode("utf-8", errors="replace")[:512]


async def request(
    client: httpx.AsyncClient,
    config: HttpRequestConfig,
    *,
    rate_limiter: _RateLimiterProtocol | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    jitter: Callable[[float], float] = _full_jitter,
) -> HttpResponse:
    last_error: SourceClientError | None = None

    for attempt in range(config.max_retries + 1):
        if rate_limiter is not None:
            await rate_limiter.acquire()
        try:
            httpx_response = await client.request(
                method=config.method,
                url=config.url,
                params=dict(config.params) if config.params is not None else None,
                headers=dict(config.headers) if config.headers is not None else None,
                json=dict(config.json_body) if config.json_body is not None else None,
                timeout=config.timeout_seconds,
            )
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError):
            last_error = SourceClientTimeoutError(url=config.url)
            if attempt >= config.max_retries:
                raise last_error from None
            backoff = _backoff_seconds(
                attempt=attempt,
                base=config.backoff_base_seconds,
                max_seconds=config.backoff_max_seconds,
                jitter=jitter,
            )
            await sleep(backoff)
            continue

        body = httpx_response.content
        status = httpx_response.status_code

        if status not in _RETRYABLE_STATUS_CODES and 200 <= status < 400:
            return HttpResponse(
                status_code=status,
                body_bytes=body,
                headers=dict(httpx_response.headers),
                content_hash=hashlib.sha256(body).hexdigest(),
                url=str(httpx_response.url),
            )

        if status not in _RETRYABLE_STATUS_CODES:
            raise SourceClientHTTPError(
                status_code=status, url=config.url, body_excerpt=_excerpt(body)
            )

        if status == 429:
            retry_after = _parse_retry_after(httpx_response.headers)
            last_error = SourceClientRateLimitError(
                url=config.url, retry_after_seconds=retry_after
            )
        else:
            last_error = SourceClientHTTPError(
                status_code=status, url=config.url, body_excerpt=_excerpt(body)
            )

        if attempt >= config.max_retries:
            raise last_error

        if (
            status == 429
            and (retry_after := _parse_retry_after(httpx_response.headers)) is not None
        ):
            await sleep(retry_after)
        else:
            backoff = _backoff_seconds(
                attempt=attempt,
                base=config.backoff_base_seconds,
                max_seconds=config.backoff_max_seconds,
                jitter=jitter,
            )
            await sleep(backoff)

    assert last_error is not None  # unreachable
    raise last_error
