# Phase 3a — Source-Client Foundation + FRED + SEC EDGAR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land a reusable outbound HTTP foundation for source clients, plus two anchor providers (FRED, SEC EDGAR), with full unit coverage. No DB writes, no LLM calls, no API routes.

**Architecture:** Functional sub-package `app/services/source_clients/` exposing `fetch_*` async functions. Shared internals: `_http.py` (typed errors + retrying request helper + sha-256 content hashing) and `_rate_limit.py` (asyncio token-bucket with injectable clock for tests). Provider modules own Pydantic response models and a module-level `RateLimiter` singleton.

**Tech Stack:** Python 3.12, `httpx.AsyncClient`, Pydantic v2, `pydantic-settings` for config, `respx` for HTTP mocking in tests, `pytest-asyncio` for async tests. All existing deps — no new packages.

**Spec:** `docs/superpowers/specs/2026-05-18-phase-3a-source-clients-design.md`

**Working directory:** `services/api/` (run all pytest / ruff / mypy commands from there).

---

## File Structure

| File | Responsibility |
|---|---|
| `app/config.py` | MODIFY — add `fred_api_key: SecretStr \| None` and `sec_edgar_user_agent: str` |
| `app/services/source_clients/__init__.py` | NEW — re-export public `fetch_*` + response models + error classes |
| `app/services/source_clients/_http.py` | NEW — typed errors, `HttpRequestConfig`, `HttpResponse`, `request()` with retry loop |
| `app/services/source_clients/_rate_limit.py` | NEW — `RateLimiter` async token-bucket |
| `app/services/source_clients/fred.py` | NEW — `FredObservation`, `FredSeriesObservations`, `fetch_series_observations` |
| `app/services/source_clients/sec_edgar.py` | NEW — `SecCompanyTicker`, `SecCompanyTickersResponse`, `SecSubmissionsResponse`, `fetch_company_tickers`, `fetch_submissions` |
| `tests/test_source_clients_rate_limit.py` | NEW — token-bucket tests |
| `tests/test_source_clients_http.py` | NEW — request helper / retry / content-hash tests |
| `tests/test_source_clients_fred.py` | NEW — FRED happy-path + error tests via `respx` |
| `tests/test_source_clients_sec_edgar.py` | NEW — SEC EDGAR happy-path + UA + flattening tests via `respx` |

Total: 1 file modified, 4 source files + 4 test files created.

---

## Task 1: Add settings for FRED key and SEC EDGAR User-Agent

**Files:**
- Modify: `services/api/app/config.py`
- Test: `services/api/tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Ensure `import pytest` is present at the top of `services/api/tests/test_config.py`, then append:

```python
def test_settings_exposes_fred_api_key_optional_secret() -> None:
    from app.config import Settings

    settings = Settings(_env_file=None)

    assert settings.fred_api_key is None


def test_settings_exposes_sec_edgar_user_agent_default() -> None:
    from app.config import Settings

    settings = Settings(_env_file=None)

    assert settings.sec_edgar_user_agent == "Alphora Research Desk admin@alphora.local"


def test_settings_fred_api_key_reads_secret_str(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import Settings

    monkeypatch.setenv("FRED_API_KEY", "abc123")

    settings = Settings(_env_file=None)

    assert settings.fred_api_key is not None
    assert settings.fred_api_key.get_secret_value() == "abc123"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd services/api
.venv/bin/python -m pytest tests/test_config.py -v
```

Expected: 3 new tests FAIL with `AttributeError: 'Settings' object has no attribute 'fred_api_key'` / `'sec_edgar_user_agent'`.

- [ ] **Step 3: Modify `app/config.py`**

Replace `app/config.py` with:

```python
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]

_DEFAULT_SEC_EDGAR_USER_AGENT = "Alphora Research Desk admin@alphora.local"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Environment = "development"
    api_prefix: str = "/api"
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    database_url: str = "postgresql+asyncpg://alphora:alphora@localhost:5432/alphora"
    redis_url: str = "redis://localhost:6379/0"

    log_level: str = "INFO"
    log_json: bool = True

    secret_box_key: str = ""

    openai_api_key: str = ""

    fred_api_key: SecretStr | None = None
    sec_edgar_user_agent: str = _DEFAULT_SEC_EDGAR_USER_AGENT


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_config.py -v
.venv/bin/python -m ruff check app/config.py tests/test_config.py
.venv/bin/python -m mypy app/config.py
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "add fred api key and sec edgar user-agent settings"
```

---

## Task 2: Build `RateLimiter` (token bucket) with deterministic clock

**Files:**
- Create: `services/api/app/services/source_clients/__init__.py` (empty placeholder for now)
- Create: `services/api/app/services/source_clients/_rate_limit.py`
- Test: `services/api/tests/test_source_clients_rate_limit.py`

- [ ] **Step 1: Write the failing tests**

Create `services/api/tests/test_source_clients_rate_limit.py`:

```python
import asyncio

import pytest


class _FakeClock:
    def __init__(self) -> None:
        self.now: float = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _RecordingSleep:
    def __init__(self, clock: _FakeClock) -> None:
        self.clock = clock
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.clock.advance(seconds)


@pytest.fixture()
def fake_clock() -> _FakeClock:
    return _FakeClock()


@pytest.fixture()
def recording_sleep(fake_clock: _FakeClock) -> _RecordingSleep:
    return _RecordingSleep(fake_clock)


async def test_burst_does_not_sleep(
    fake_clock: _FakeClock, recording_sleep: _RecordingSleep
) -> None:
    from app.services.source_clients._rate_limit import RateLimiter

    limiter = RateLimiter(
        rate_per_second=2.0, burst=3, clock=fake_clock, sleep=recording_sleep
    )

    for _ in range(3):
        await limiter.acquire()

    assert recording_sleep.calls == []


async def test_acquire_after_burst_sleeps_one_token_interval(
    fake_clock: _FakeClock, recording_sleep: _RecordingSleep
) -> None:
    from app.services.source_clients._rate_limit import RateLimiter

    limiter = RateLimiter(
        rate_per_second=2.0, burst=1, clock=fake_clock, sleep=recording_sleep
    )

    await limiter.acquire()
    await limiter.acquire()

    assert recording_sleep.calls == [pytest.approx(0.5)]


async def test_tokens_refill_over_time(
    fake_clock: _FakeClock, recording_sleep: _RecordingSleep
) -> None:
    from app.services.source_clients._rate_limit import RateLimiter

    limiter = RateLimiter(
        rate_per_second=4.0, burst=1, clock=fake_clock, sleep=recording_sleep
    )

    await limiter.acquire()
    fake_clock.advance(0.25)
    await limiter.acquire()

    assert recording_sleep.calls == []


async def test_concurrent_acquires_serialize(
    fake_clock: _FakeClock, recording_sleep: _RecordingSleep
) -> None:
    from app.services.source_clients._rate_limit import RateLimiter

    limiter = RateLimiter(
        rate_per_second=10.0, burst=2, clock=fake_clock, sleep=recording_sleep
    )

    async def caller() -> None:
        await limiter.acquire()

    await asyncio.gather(caller(), caller(), caller(), caller())

    assert len(recording_sleep.calls) == 2
    for sleep_seconds in recording_sleep.calls:
        assert sleep_seconds == pytest.approx(0.1)


async def test_rate_limiter_rejects_invalid_config() -> None:
    from app.services.source_clients._rate_limit import RateLimiter

    with pytest.raises(ValueError):
        RateLimiter(rate_per_second=0.0, burst=1)
    with pytest.raises(ValueError):
        RateLimiter(rate_per_second=1.0, burst=0)


def test_rate_limiter_uses_module_default_clock_and_sleep() -> None:
    import time

    from app.services.source_clients._rate_limit import RateLimiter

    limiter = RateLimiter(rate_per_second=1.0, burst=1)

    assert limiter._clock is time.monotonic
    assert limiter._sleep is asyncio.sleep
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_source_clients_rate_limit.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.source_clients'`.

- [ ] **Step 3: Create the package and the rate limiter**

Create `services/api/app/services/source_clients/__init__.py` as an empty file for now:

```python
```

Create `services/api/app/services/source_clients/_rate_limit.py`:

```python
import asyncio
import time
from collections.abc import Awaitable, Callable


class RateLimiter:
    """Asyncio token-bucket rate limiter.

    Bucket starts full at `burst` tokens and refills at `rate_per_second` continuously.
    `acquire()` deducts one token; if none available, it sleeps the minimum interval
    needed for a token to arrive, then deducts.
    """

    def __init__(
        self,
        *,
        rate_per_second: float,
        burst: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if rate_per_second <= 0.0:
            raise ValueError("rate_per_second must be positive")
        if burst <= 0:
            raise ValueError("burst must be positive")

        self._rate_per_second = rate_per_second
        self._burst = float(burst)
        self._clock = clock
        self._sleep = sleep
        self._tokens = float(burst)
        self._last_refill = clock()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            needed = 1.0 - self._tokens
            wait_seconds = needed / self._rate_per_second
            await self._sleep(wait_seconds)
            self._refill()
            self._tokens -= 1.0

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._last_refill
        if elapsed <= 0.0:
            return
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate_per_second)
        self._last_refill = now
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_source_clients_rate_limit.py -v
.venv/bin/python -m ruff check app/services/source_clients tests/test_source_clients_rate_limit.py
.venv/bin/python -m mypy app/services/source_clients
```

Expected: 6 PASS, ruff clean, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add app/services/source_clients/__init__.py app/services/source_clients/_rate_limit.py tests/test_source_clients_rate_limit.py
git commit -m "add source-clients package and asyncio rate limiter"
```

---

## Task 3: Define typed errors and value objects in `_http.py`

**Files:**
- Create: `services/api/app/services/source_clients/_http.py` (errors + dataclasses only — request helper comes in Task 4)
- Test: `services/api/tests/test_source_clients_http.py` (errors-only portion)

- [ ] **Step 1: Write the failing tests**

Create `services/api/tests/test_source_clients_http.py`:

```python
import hashlib

import pytest


def test_source_client_error_is_exception() -> None:
    from app.services.source_clients._http import SourceClientError

    assert issubclass(SourceClientError, Exception)


def test_source_client_http_error_carries_status_and_url() -> None:
    from app.services.source_clients._http import SourceClientHTTPError

    error = SourceClientHTTPError(
        status_code=503, url="https://example.com", body_excerpt="boom"
    )

    assert error.status_code == 503
    assert error.url == "https://example.com"
    assert error.body_excerpt == "boom"


def test_source_client_timeout_error_carries_url() -> None:
    from app.services.source_clients._http import SourceClientTimeoutError

    error = SourceClientTimeoutError(url="https://example.com")

    assert error.url == "https://example.com"


def test_source_client_rate_limit_error_carries_retry_after() -> None:
    from app.services.source_clients._http import SourceClientRateLimitError

    error = SourceClientRateLimitError(
        url="https://example.com", retry_after_seconds=2.5
    )

    assert error.retry_after_seconds == pytest.approx(2.5)


def test_source_client_config_error_carries_setting_name() -> None:
    from app.services.source_clients._http import SourceClientConfigError

    error = SourceClientConfigError(setting_name="fred_api_key")

    assert error.setting_name == "fred_api_key"


def test_http_request_config_is_frozen() -> None:
    from app.services.source_clients._http import HttpRequestConfig

    config = HttpRequestConfig(method="GET", url="https://example.com")

    with pytest.raises(Exception):
        config.url = "https://other.com"  # type: ignore[misc]


def test_http_response_content_hash_is_sha256_hex() -> None:
    from app.services.source_clients._http import HttpResponse

    body = b"hello world"
    response = HttpResponse(
        status_code=200,
        body_bytes=body,
        headers={},
        content_hash=hashlib.sha256(body).hexdigest(),
        url="https://example.com",
    )

    assert response.content_hash == hashlib.sha256(b"hello world").hexdigest()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_source_clients_http.py -v
```

Expected: all FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `_http.py` with errors and dataclasses**

Create `services/api/app/services/source_clients/_http.py`:

```python
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal


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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_source_clients_http.py -v
.venv/bin/python -m ruff check app/services/source_clients/_http.py tests/test_source_clients_http.py
.venv/bin/python -m mypy app/services/source_clients/_http.py
```

Expected: 7 PASS, ruff clean, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add app/services/source_clients/_http.py tests/test_source_clients_http.py
git commit -m "add typed errors and request/response value objects for source clients"
```

---

## Task 4: Implement `request()` with retries and content hashing

**Files:**
- Modify: `services/api/app/services/source_clients/_http.py` (append `request()` and helpers)
- Modify: `services/api/tests/test_source_clients_http.py` (append retry / hash / timeout tests)

- [ ] **Step 1: Write the failing tests**

Update the imports section at the top of `services/api/tests/test_source_clients_http.py` to:

```python
import hashlib

import httpx
import pytest
import respx
```

Then append the following classes, fixtures, and tests to the end of the file:

```python
class _FakeClock:
    def __init__(self) -> None:
        self.now: float = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _RecordingSleep:
    def __init__(self, clock: _FakeClock) -> None:
        self.clock = clock
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.clock.advance(seconds)


@pytest.fixture()
def fake_clock() -> _FakeClock:
    return _FakeClock()


@pytest.fixture()
def recording_sleep(fake_clock: _FakeClock) -> _RecordingSleep:
    return _RecordingSleep(fake_clock)


@respx.mock
async def test_request_returns_response_with_content_hash() -> None:
    from app.services.source_clients._http import HttpRequestConfig, request

    body = b'{"ok": true}'
    respx.get("https://example.com/x").mock(
        return_value=httpx.Response(200, content=body, headers={"Content-Type": "application/json"})
    )

    async with httpx.AsyncClient() as client:
        response = await request(
            client,
            HttpRequestConfig(method="GET", url="https://example.com/x"),
        )

    assert response.status_code == 200
    assert response.body_bytes == body
    assert response.content_hash == hashlib.sha256(body).hexdigest()
    assert response.url == "https://example.com/x"


@respx.mock
async def test_request_retries_5xx_then_succeeds(
    recording_sleep: _RecordingSleep,
) -> None:
    from app.services.source_clients._http import HttpRequestConfig, request

    route = respx.get("https://example.com/x")
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(200, content=b"ok"),
    ]

    async with httpx.AsyncClient() as client:
        response = await request(
            client,
            HttpRequestConfig(
                method="GET",
                url="https://example.com/x",
                max_retries=3,
                backoff_base_seconds=0.5,
                backoff_max_seconds=8.0,
            ),
            sleep=recording_sleep,
            jitter=lambda _max: _max,
        )

    assert response.status_code == 200
    assert recording_sleep.calls == [pytest.approx(0.5), pytest.approx(1.0)]


@respx.mock
async def test_request_retries_429_with_retry_after_header(
    recording_sleep: _RecordingSleep,
) -> None:
    from app.services.source_clients._http import HttpRequestConfig, request

    route = respx.get("https://example.com/x")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "3"}),
        httpx.Response(200, content=b"ok"),
    ]

    async with httpx.AsyncClient() as client:
        response = await request(
            client,
            HttpRequestConfig(method="GET", url="https://example.com/x"),
            sleep=recording_sleep,
            jitter=lambda _max: _max,
        )

    assert response.status_code == 200
    assert recording_sleep.calls == [pytest.approx(3.0)]


@respx.mock
async def test_request_raises_after_retries_exhausted_on_503(
    recording_sleep: _RecordingSleep,
) -> None:
    from app.services.source_clients._http import (
        HttpRequestConfig,
        SourceClientHTTPError,
        request,
    )

    respx.get("https://example.com/x").mock(return_value=httpx.Response(503))

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError) as exc_info:
            await request(
                client,
                HttpRequestConfig(
                    method="GET", url="https://example.com/x", max_retries=2
                ),
                sleep=recording_sleep,
                jitter=lambda _max: _max,
            )

    assert exc_info.value.status_code == 503
    assert len(recording_sleep.calls) == 2


@respx.mock
async def test_request_raises_after_retries_exhausted_on_429() -> None:
    from app.services.source_clients._http import (
        HttpRequestConfig,
        SourceClientRateLimitError,
        request,
    )

    async def no_sleep(_seconds: float) -> None:
        return None

    respx.get("https://example.com/x").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "1"})
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientRateLimitError) as exc_info:
            await request(
                client,
                HttpRequestConfig(
                    method="GET", url="https://example.com/x", max_retries=1
                ),
                sleep=no_sleep,
            )

    assert exc_info.value.retry_after_seconds == pytest.approx(1.0)


@respx.mock
async def test_request_does_not_retry_404() -> None:
    from app.services.source_clients._http import (
        HttpRequestConfig,
        SourceClientHTTPError,
        request,
    )

    route = respx.get("https://example.com/x").mock(
        return_value=httpx.Response(404, content=b"not found")
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError) as exc_info:
            await request(
                client,
                HttpRequestConfig(method="GET", url="https://example.com/x"),
            )

    assert exc_info.value.status_code == 404
    assert route.call_count == 1


@respx.mock
async def test_request_retries_on_connect_error_then_succeeds(
    recording_sleep: _RecordingSleep,
) -> None:
    from app.services.source_clients._http import HttpRequestConfig, request

    route = respx.get("https://example.com/x")
    route.side_effect = [
        httpx.ConnectError("boom"),
        httpx.Response(200, content=b"ok"),
    ]

    async with httpx.AsyncClient() as client:
        response = await request(
            client,
            HttpRequestConfig(method="GET", url="https://example.com/x"),
            sleep=recording_sleep,
            jitter=lambda _max: _max,
        )

    assert response.status_code == 200
    assert len(recording_sleep.calls) == 1


@respx.mock
async def test_request_raises_timeout_error_after_exhaustion() -> None:
    from app.services.source_clients._http import (
        HttpRequestConfig,
        SourceClientTimeoutError,
        request,
    )

    async def no_sleep(_seconds: float) -> None:
        return None

    respx.get("https://example.com/x").mock(side_effect=httpx.ReadTimeout("slow"))

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientTimeoutError):
            await request(
                client,
                HttpRequestConfig(
                    method="GET", url="https://example.com/x", max_retries=1
                ),
                sleep=no_sleep,
            )


@respx.mock
async def test_request_passes_params_and_headers() -> None:
    from app.services.source_clients._http import HttpRequestConfig, request

    route = respx.get("https://example.com/x").mock(
        return_value=httpx.Response(200, content=b"ok")
    )

    async with httpx.AsyncClient() as client:
        await request(
            client,
            HttpRequestConfig(
                method="GET",
                url="https://example.com/x",
                params={"a": "1", "b": 2},
                headers={"X-Custom": "yes"},
            ),
        )

    sent = route.calls.last.request
    assert sent.headers["X-Custom"] == "yes"
    assert sent.url.params["a"] == "1"
    assert sent.url.params["b"] == "2"


@respx.mock
async def test_request_calls_rate_limiter_before_each_attempt(
    recording_sleep: _RecordingSleep,
) -> None:
    from app.services.source_clients._http import HttpRequestConfig, request

    acquire_count = 0

    class _Limiter:
        async def acquire(self) -> None:
            nonlocal acquire_count
            acquire_count += 1

    route = respx.get("https://example.com/x")
    route.side_effect = [httpx.Response(503), httpx.Response(200, content=b"ok")]

    async with httpx.AsyncClient() as client:
        await request(
            client,
            HttpRequestConfig(method="GET", url="https://example.com/x"),
            rate_limiter=_Limiter(),
            sleep=recording_sleep,
            jitter=lambda _max: _max,
        )

    assert acquire_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_source_clients_http.py -v
```

Expected: 10 new tests FAIL with `ImportError: cannot import name 'request'` and friends.

- [ ] **Step 3: Implement `request()` in `_http.py`**

Append to `services/api/app/services/source_clients/_http.py`:

```python
import asyncio
import hashlib
import random
from collections.abc import Awaitable, Callable
from typing import Protocol

import httpx

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
    cap = min(max_seconds, base * (2 ** attempt))
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
                raise last_error
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

        if status == 429 and (retry_after := _parse_retry_after(httpx_response.headers)) is not None:
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_source_clients_http.py -v
.venv/bin/python -m ruff check app/services/source_clients/_http.py tests/test_source_clients_http.py
.venv/bin/python -m mypy app/services/source_clients/_http.py
```

Expected: all PASS (17 total tests in this file), ruff clean, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add app/services/source_clients/_http.py tests/test_source_clients_http.py
git commit -m "add retrying request helper with content hashing for source clients"
```

---

## Task 5: Implement FRED client (`fred.py`)

**Files:**
- Create: `services/api/app/services/source_clients/fred.py`
- Test: `services/api/tests/test_source_clients_fred.py`

- [ ] **Step 1: Write the failing tests**

Create `services/api/tests/test_source_clients_fred.py`:

```python
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

_FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


@pytest.fixture(autouse=True)
def _set_fred_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from app.config import get_settings

    monkeypatch.setenv("FRED_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@respx.mock
async def test_fetch_series_observations_parses_payload() -> None:
    from app.services.source_clients.fred import fetch_series_observations

    payload = {
        "observation_start": "2024-01-01",
        "observation_end": "2024-03-01",
        "count": 2,
        "observations": [
            {
                "date": "2024-01-01",
                "value": "100.5",
                "realtime_start": "2024-01-15",
                "realtime_end": "2024-12-31",
            },
            {
                "date": "2024-02-01",
                "value": ".",
                "realtime_start": "2024-02-15",
                "realtime_end": "2024-12-31",
            },
        ],
    }
    respx.get(_FRED_BASE).mock(return_value=httpx.Response(200, json=payload))

    async with httpx.AsyncClient() as client:
        result, content_hash = await fetch_series_observations(
            client=client, series_id="GDP"
        )

    assert result.series_id == "GDP"
    assert result.count == 2
    assert result.observations[0].value == Decimal("100.5")
    assert result.observations[1].value is None
    assert isinstance(content_hash, str) and len(content_hash) == 64


@respx.mock
async def test_fetch_series_observations_sends_key_and_dates_as_params() -> None:
    from app.services.source_clients.fred import fetch_series_observations

    route = respx.get(_FRED_BASE).mock(
        return_value=httpx.Response(
            200,
            json={
                "observation_start": "2024-01-01",
                "observation_end": "2024-03-01",
                "count": 0,
                "observations": [],
            },
        )
    )

    async with httpx.AsyncClient() as client:
        await fetch_series_observations(
            client=client,
            series_id="GDP",
            observation_start=date(2024, 1, 1),
            observation_end=date(2024, 3, 1),
        )

    sent = route.calls.last.request
    assert sent.url.params["api_key"] == "test-key"
    assert sent.url.params["series_id"] == "GDP"
    assert sent.url.params["file_type"] == "json"
    assert sent.url.params["observation_start"] == "2024-01-01"
    assert sent.url.params["observation_end"] == "2024-03-01"


async def test_fetch_series_observations_raises_when_api_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings
    from app.services.source_clients.fred import fetch_series_observations
    from app.services.source_clients._http import SourceClientConfigError

    monkeypatch.delenv("FRED_API_KEY", raising=False)
    get_settings.cache_clear()

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientConfigError) as exc_info:
            await fetch_series_observations(client=client, series_id="GDP")

    assert exc_info.value.setting_name == "fred_api_key"


@respx.mock
async def test_fetch_series_observations_400_does_not_retry() -> None:
    from app.services.source_clients.fred import fetch_series_observations
    from app.services.source_clients._http import SourceClientHTTPError

    route = respx.get(_FRED_BASE).mock(
        return_value=httpx.Response(400, content=b'{"error_message": "bad series"}')
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError) as exc_info:
            await fetch_series_observations(client=client, series_id="BAD")

    assert exc_info.value.status_code == 400
    assert route.call_count == 1


def test_fred_module_exposes_singleton_rate_limiter() -> None:
    from app.services.source_clients import fred
    from app.services.source_clients._rate_limit import RateLimiter

    assert isinstance(fred._RATE_LIMITER, RateLimiter)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_source_clients_fred.py -v
```

Expected: all FAIL with `ModuleNotFoundError: No module named 'app.services.source_clients.fred'`.

- [ ] **Step 3: Implement `fred.py`**

Create `services/api/app/services/source_clients/fred.py`:

```python
import json
from datetime import date
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
from app.services.source_clients._rate_limit import RateLimiter

_FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
_FRED_MISSING_VALUE_SENTINEL = "."

_RATE_LIMITER = RateLimiter(rate_per_second=2.0, burst=10)


class FredObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    date: date
    value: Decimal | None
    realtime_start: date
    realtime_end: date

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_missing(cls, raw: object) -> object:
        if raw == _FRED_MISSING_VALUE_SENTINEL:
            return None
        return raw


class FredSeriesObservations(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    series_id: str
    observation_start: date
    observation_end: date
    count: int
    observations: list[FredObservation]


async def fetch_series_observations(
    *,
    client: httpx.AsyncClient,
    series_id: str,
    observation_start: date | None = None,
    observation_end: date | None = None,
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
        rate_limiter=_RATE_LIMITER,
    )

    payload: dict[str, Any] = json.loads(response.body_bytes)
    payload["series_id"] = series_id
    parsed = FredSeriesObservations.model_validate(payload)
    return parsed, response.content_hash
```

FRED's JSON body does not echo `series_id`. We inject it from the request argument so the parsed model carries it; the merged dict is then validated.

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_source_clients_fred.py -v
.venv/bin/python -m ruff check app/services/source_clients/fred.py tests/test_source_clients_fred.py
.venv/bin/python -m mypy app/services/source_clients/fred.py
```

Expected: 5 PASS, ruff clean, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add app/services/source_clients/fred.py tests/test_source_clients_fred.py
git commit -m "add fred series observations client"
```

---

## Task 6: Implement SEC EDGAR client (`sec_edgar.py`)

**Files:**
- Create: `services/api/app/services/source_clients/sec_edgar.py`
- Test: `services/api/tests/test_source_clients_sec_edgar.py`

- [ ] **Step 1: Write the failing tests**

Create `services/api/tests/test_source_clients_sec_edgar.py`:

```python
from collections.abc import Iterator
from datetime import date

import httpx
import pytest
import respx


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@respx.mock
async def test_fetch_company_tickers_flattens_dict_of_dicts() -> None:
    from app.services.source_clients.sec_edgar import fetch_company_tickers

    payload = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
    }
    respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json=payload)
    )

    async with httpx.AsyncClient() as client:
        result, content_hash = await fetch_company_tickers(client=client)

    assert len(result.companies) == 2
    assert {c.ticker for c in result.companies} == {"AAPL", "MSFT"}
    assert result.companies[0].cik_str == 320193
    assert isinstance(content_hash, str) and len(content_hash) == 64


@respx.mock
async def test_fetch_company_tickers_sends_user_agent() -> None:
    from app.services.source_clients.sec_edgar import fetch_company_tickers

    route = respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json={})
    )

    async with httpx.AsyncClient() as client:
        await fetch_company_tickers(client=client)

    sent = route.calls.last.request
    assert sent.headers["User-Agent"] == "Alphora Research Desk admin@alphora.local"


@respx.mock
async def test_fetch_submissions_pads_cik_in_url() -> None:
    from app.services.source_clients.sec_edgar import fetch_submissions

    route = respx.get(
        "https://data.sec.gov/submissions/CIK0000320193.json"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "cik": "0000320193",
                "name": "Apple Inc.",
                "sic": "3571",
                "tickers": ["AAPL"],
                "filings": {
                    "recent": {
                        "accessionNumber": ["0000320193-24-000001"],
                        "filingDate": ["2024-02-01"],
                        "reportDate": ["2023-12-31"],
                        "form": ["10-K"],
                        "primaryDocument": ["aapl-20231231.htm"],
                        "primaryDocDescription": ["10-K"],
                    }
                },
            },
        )
    )

    async with httpx.AsyncClient() as client:
        result, _ = await fetch_submissions(client=client, cik="320193")

    assert route.call_count == 1
    assert result.cik == "0000320193"
    assert result.name == "Apple Inc."
    assert result.tickers == ["AAPL"]
    assert len(result.recent) == 1
    submission = result.recent[0]
    assert submission.accession_number == "0000320193-24-000001"
    assert submission.filing_date == date(2024, 2, 1)
    assert submission.report_date == date(2023, 12, 31)
    assert submission.form == "10-K"
    assert submission.primary_document == "aapl-20231231.htm"
    assert submission.primary_doc_description == "10-K"


@respx.mock
async def test_fetch_submissions_flattens_parallel_arrays() -> None:
    from app.services.source_clients.sec_edgar import fetch_submissions

    respx.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "cik": "0000320193",
                "name": "Apple Inc.",
                "sic": None,
                "tickers": [],
                "filings": {
                    "recent": {
                        "accessionNumber": ["a", "b"],
                        "filingDate": ["2024-01-01", "2024-02-01"],
                        "reportDate": ["2023-12-01", None],
                        "form": ["10-Q", "8-K"],
                        "primaryDocument": ["a.htm", "b.htm"],
                        "primaryDocDescription": [None, "current report"],
                    }
                },
            },
        )
    )

    async with httpx.AsyncClient() as client:
        result, _ = await fetch_submissions(client=client, cik="320193")

    assert [s.form for s in result.recent] == ["10-Q", "8-K"]
    assert result.recent[1].report_date is None
    assert result.recent[0].primary_doc_description is None


@respx.mock
async def test_fetch_company_tickers_403_does_not_retry() -> None:
    from app.services.source_clients.sec_edgar import fetch_company_tickers
    from app.services.source_clients._http import SourceClientHTTPError

    route = respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(403, content=b"forbidden")
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError) as exc_info:
            await fetch_company_tickers(client=client)

    assert exc_info.value.status_code == 403
    assert route.call_count == 1


def test_sec_edgar_module_exposes_singleton_rate_limiter() -> None:
    from app.services.source_clients import sec_edgar
    from app.services.source_clients._rate_limit import RateLimiter

    assert isinstance(sec_edgar._RATE_LIMITER, RateLimiter)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_source_clients_sec_edgar.py -v
```

Expected: all FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `sec_edgar.py`**

Create `services/api/app/services/source_clients/sec_edgar.py`:

```python
from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, model_validator

from app.config import get_settings
from app.services.source_clients._http import HttpRequestConfig, request
from app.services.source_clients._rate_limit import RateLimiter

_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{padded_cik}.json"

_RATE_LIMITER = RateLimiter(rate_per_second=8.0, burst=5)


def _user_agent_headers() -> dict[str, str]:
    return {"User-Agent": get_settings().sec_edgar_user_agent}


def _padded_cik(cik: str) -> str:
    return cik.zfill(10)


class SecCompanyTicker(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    cik_str: int
    ticker: str
    title: str


class SecCompanyTickersResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    companies: list[SecCompanyTicker]

    @model_validator(mode="before")
    @classmethod
    def _flatten_dict_of_dicts(cls, data: Any) -> Any:
        if isinstance(data, dict) and "companies" not in data:
            return {"companies": list(data.values())}
        return data


class SecRecentSubmission(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    accession_number: str
    filing_date: date
    report_date: date | None
    form: str
    primary_document: str
    primary_doc_description: str | None


class SecSubmissionsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    cik: str
    name: str
    sic: str | None
    tickers: list[str]
    recent: list[SecRecentSubmission]

    @model_validator(mode="before")
    @classmethod
    def _flatten_recent_arrays(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "recent" in data:
            return data
        filings = data.get("filings")
        if not isinstance(filings, dict):
            return data
        recent_arrays = filings.get("recent")
        if not isinstance(recent_arrays, dict):
            return data

        accession_numbers = recent_arrays.get("accessionNumber", [])
        filing_dates = recent_arrays.get("filingDate", [])
        report_dates = recent_arrays.get("reportDate", [])
        forms = recent_arrays.get("form", [])
        primary_documents = recent_arrays.get("primaryDocument", [])
        primary_doc_descriptions = recent_arrays.get("primaryDocDescription", [])

        rows: list[dict[str, Any]] = []
        for index, accession in enumerate(accession_numbers):
            rows.append(
                {
                    "accession_number": accession,
                    "filing_date": filing_dates[index],
                    "report_date": (
                        report_dates[index] if index < len(report_dates) else None
                    ),
                    "form": forms[index],
                    "primary_document": primary_documents[index],
                    "primary_doc_description": (
                        primary_doc_descriptions[index]
                        if index < len(primary_doc_descriptions)
                        else None
                    ),
                }
            )
        out = dict(data)
        out["recent"] = rows
        return out


async def fetch_company_tickers(
    *, client: httpx.AsyncClient,
) -> tuple[SecCompanyTickersResponse, str]:
    response = await request(
        client,
        HttpRequestConfig(
            method="GET", url=_COMPANY_TICKERS_URL, headers=_user_agent_headers()
        ),
        rate_limiter=_RATE_LIMITER,
    )
    parsed = SecCompanyTickersResponse.model_validate_json(response.body_bytes)
    return parsed, response.content_hash


async def fetch_submissions(
    *, client: httpx.AsyncClient, cik: str,
) -> tuple[SecSubmissionsResponse, str]:
    url = _SUBMISSIONS_URL_TEMPLATE.format(padded_cik=_padded_cik(cik))
    response = await request(
        client,
        HttpRequestConfig(method="GET", url=url, headers=_user_agent_headers()),
        rate_limiter=_RATE_LIMITER,
    )
    parsed = SecSubmissionsResponse.model_validate_json(response.body_bytes)
    return parsed, response.content_hash
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_source_clients_sec_edgar.py -v
.venv/bin/python -m ruff check app/services/source_clients/sec_edgar.py tests/test_source_clients_sec_edgar.py
.venv/bin/python -m mypy app/services/source_clients/sec_edgar.py
```

Expected: 6 PASS, ruff clean, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add app/services/source_clients/sec_edgar.py tests/test_source_clients_sec_edgar.py
git commit -m "add sec edgar company tickers and submissions clients"
```

---

## Task 7: Wire `__init__.py` public exports

**Files:**
- Modify: `services/api/app/services/source_clients/__init__.py`
- Test: `services/api/tests/test_source_clients_http.py` (append exports test)

- [ ] **Step 1: Write the failing test**

Create a new test file `services/api/tests/test_source_clients_exports.py` (keeping the exports check isolated so other test files stay focused):

```python
def test_public_exports_include_fetch_functions_and_models_and_errors() -> None:
    from app.services import source_clients

    expected = {
        "FredObservation",
        "FredSeriesObservations",
        "SecCompanyTicker",
        "SecCompanyTickersResponse",
        "SecRecentSubmission",
        "SecSubmissionsResponse",
        "SourceClientConfigError",
        "SourceClientError",
        "SourceClientHTTPError",
        "SourceClientRateLimitError",
        "SourceClientTimeoutError",
        "fetch_company_tickers",
        "fetch_series_observations",
        "fetch_submissions",
    }

    actual = set(source_clients.__all__)

    assert expected.issubset(actual)
    for name in expected:
        assert hasattr(source_clients, name), f"missing export: {name}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_source_clients_exports.py -v
```

Expected: FAIL with `AssertionError` (most names missing from `__all__`).

- [ ] **Step 3: Populate `__init__.py`**

Overwrite `services/api/app/services/source_clients/__init__.py`:

```python
from app.services.source_clients._http import (
    SourceClientConfigError,
    SourceClientError,
    SourceClientHTTPError,
    SourceClientRateLimitError,
    SourceClientTimeoutError,
)
from app.services.source_clients.fred import (
    FredObservation,
    FredSeriesObservations,
    fetch_series_observations,
)
from app.services.source_clients.sec_edgar import (
    SecCompanyTicker,
    SecCompanyTickersResponse,
    SecRecentSubmission,
    SecSubmissionsResponse,
    fetch_company_tickers,
    fetch_submissions,
)

__all__ = [
    "FredObservation",
    "FredSeriesObservations",
    "SecCompanyTicker",
    "SecCompanyTickersResponse",
    "SecRecentSubmission",
    "SecSubmissionsResponse",
    "SourceClientConfigError",
    "SourceClientError",
    "SourceClientHTTPError",
    "SourceClientRateLimitError",
    "SourceClientTimeoutError",
    "fetch_company_tickers",
    "fetch_series_observations",
    "fetch_submissions",
]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_source_clients_exports.py -v
.venv/bin/python -m ruff check app/services/source_clients/__init__.py tests/test_source_clients_exports.py
.venv/bin/python -m mypy app/services/source_clients
```

Expected: PASS, ruff clean, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add app/services/source_clients/__init__.py tests/test_source_clients_exports.py
git commit -m "expose source-client public api from package root"
```

---

## Task 8: Full verification sweep

**Files:** none modified. Pure verification.

- [ ] **Step 1: Run the full test suite**

```bash
cd services/api
.venv/bin/python -m pytest
```

Expected: ≥ 237 passing (Phase 2 baseline 219 + at least 18 new). Zero failures, zero errors, zero warnings related to our code.

- [ ] **Step 2: Run ruff across the whole project**

```bash
.venv/bin/python -m ruff check
```

Expected: clean (no diagnostics).

- [ ] **Step 3: Run mypy strict on `app`**

```bash
.venv/bin/python -m mypy app
```

Expected: `Success: no issues found in 68 source files` (was 64; we added 4 new modules — `__init__.py`, `_http.py`, `_rate_limit.py`, `fred.py`, `sec_edgar.py` = 5 new, so 64 + 5 = 69 if `__init__.py` is counted; the exact number depends on mypy's file-count logic but it must be `Success`).

- [ ] **Step 4: Re-verify alembic round-trip is unaffected**

```bash
rm -f /tmp/alembic_check.db
DATABASE_URL="sqlite+aiosqlite:////tmp/alembic_check.db" \
    .venv/bin/python -m alembic upgrade head
DATABASE_URL="sqlite+aiosqlite:////tmp/alembic_check.db" \
    .venv/bin/python -m alembic check
DATABASE_URL="sqlite+aiosqlite:////tmp/alembic_check.db" \
    .venv/bin/python -m alembic downgrade base
rm -f /tmp/alembic_check.db
```

Expected: upgrade succeeds, `alembic check` reports "No new upgrade operations detected.", downgrade succeeds.

- [ ] **Step 5: Confirm git is clean and commit history is tidy**

```bash
git status
git log --oneline -10
```

Expected: working tree clean (or only the untracked `services/api/uv.lock` from Phase 2). Last 7 commits are Phase 3a's task commits in order.

---

## Done criteria

- All 8 tasks complete.
- `pytest` green, ≥ 237 passing.
- `ruff check` clean.
- `mypy app` clean.
- `alembic check` clean.
- 7 new commits on `freddysongg/trading-llm-signals`, none pushed.
- 1 file modified (`app/config.py`), 4 source files created (`__init__.py`, `_http.py`, `_rate_limit.py`, `fred.py`, `sec_edgar.py`), 5 test files created (`test_source_clients_rate_limit.py`, `test_source_clients_http.py`, `test_source_clients_fred.py`, `test_source_clients_sec_edgar.py`, `test_source_clients_exports.py`).
- No DB writes, no LLM calls, no API routes, no SSE wiring, no UI changes, no new dependencies.
