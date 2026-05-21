import hashlib
from dataclasses import FrozenInstanceError

import httpx
import pytest
import respx


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

    with pytest.raises(FrozenInstanceError):
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


@respx.mock
async def test_request_max_retries_zero_fails_fast_on_5xx(
    recording_sleep: _RecordingSleep,
) -> None:
    from app.services.source_clients._http import (
        HttpRequestConfig,
        SourceClientHTTPError,
        request,
    )

    route = respx.get("https://example.com/x").mock(return_value=httpx.Response(503))

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError) as exc_info:
            await request(
                client,
                HttpRequestConfig(
                    method="GET", url="https://example.com/x", max_retries=0
                ),
                sleep=recording_sleep,
                jitter=lambda _max: _max,
            )

    assert exc_info.value.status_code == 503
    assert route.call_count == 1
    assert recording_sleep.calls == []


@respx.mock
async def test_request_malformed_retry_after_falls_back_to_backoff(
    recording_sleep: _RecordingSleep,
) -> None:
    from app.services.source_clients._http import HttpRequestConfig, request

    route = respx.get("https://example.com/x")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "not-a-number"}),
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
    assert recording_sleep.calls == [pytest.approx(0.5)]


@respx.mock
async def test_request_uses_request_cache_on_hit() -> None:
    """Second GET to the same URL inside the TTL window does not hit the network."""
    from app.services.source_clients._http import HttpRequestConfig, request
    from app.services.source_clients._request_cache import RequestCache

    body = b"cached body"
    route = respx.get("https://example.com/cache").mock(
        return_value=httpx.Response(200, content=body)
    )
    cache = RequestCache(ttl_seconds=60.0)

    async with httpx.AsyncClient() as client:
        first = await request(
            client,
            HttpRequestConfig(method="GET", url="https://example.com/cache"),
            request_cache=cache,
        )
        second = await request(
            client,
            HttpRequestConfig(method="GET", url="https://example.com/cache"),
            request_cache=cache,
        )

    assert first.body_bytes == body
    assert second.body_bytes == body
    assert route.call_count == 1
    stats = cache.stats()
    assert stats.hits == 1
    assert stats.misses == 1


@respx.mock
async def test_request_skips_cache_for_post_method() -> None:
    """POSTs are not cached even when a cache is installed."""
    from app.services.source_clients._http import HttpRequestConfig, request
    from app.services.source_clients._request_cache import RequestCache

    route = respx.post("https://example.com/post").mock(
        return_value=httpx.Response(200, content=b"x")
    )
    cache = RequestCache(ttl_seconds=60.0)

    async with httpx.AsyncClient() as client:
        await request(
            client,
            HttpRequestConfig(method="POST", url="https://example.com/post"),
            request_cache=cache,
        )
        await request(
            client,
            HttpRequestConfig(method="POST", url="https://example.com/post"),
            request_cache=cache,
        )

    assert route.call_count == 2
    assert cache.stats().hits == 0


@respx.mock
async def test_request_distinct_params_distinct_cache_entries() -> None:
    from app.services.source_clients._http import HttpRequestConfig, request
    from app.services.source_clients._request_cache import RequestCache

    route = respx.get("https://example.com/params").mock(
        return_value=httpx.Response(200, content=b"y")
    )
    cache = RequestCache(ttl_seconds=60.0)

    async with httpx.AsyncClient() as client:
        await request(
            client,
            HttpRequestConfig(
                method="GET",
                url="https://example.com/params",
                params={"q": "a"},
            ),
            request_cache=cache,
        )
        await request(
            client,
            HttpRequestConfig(
                method="GET",
                url="https://example.com/params",
                params={"q": "b"},
            ),
            request_cache=cache,
        )

    assert route.call_count == 2
    assert cache.stats().hits == 0


@respx.mock
async def test_request_resolves_cache_from_registry_when_not_passed() -> None:
    """`request()` falls back to the process-wide cache if none is passed."""
    from app.services.source_clients._http import HttpRequestConfig, request
    from app.services.source_clients._registry import (
        install_request_cache,
        reset_registry,
    )
    from app.services.source_clients._request_cache import RequestCache

    reset_registry()
    cache = RequestCache(ttl_seconds=60.0)
    install_request_cache(cache)
    try:
        body = b"registry-hit"
        route = respx.get("https://example.com/reg").mock(
            return_value=httpx.Response(200, content=body)
        )

        async with httpx.AsyncClient() as client:
            await request(
                client,
                HttpRequestConfig(method="GET", url="https://example.com/reg"),
            )
            await request(
                client,
                HttpRequestConfig(method="GET", url="https://example.com/reg"),
            )

        assert route.call_count == 1
        assert cache.stats().hits == 1
    finally:
        reset_registry()
