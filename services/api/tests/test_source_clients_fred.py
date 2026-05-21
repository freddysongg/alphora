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
    from app.services.source_clients._http import SourceClientConfigError
    from app.services.source_clients.fred import fetch_series_observations

    monkeypatch.delenv("FRED_API_KEY", raising=False)
    get_settings.cache_clear()

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientConfigError) as exc_info:
            await fetch_series_observations(client=client, series_id="GDP")

    assert exc_info.value.setting_name == "fred_api_key"


@respx.mock
async def test_fetch_series_observations_400_does_not_retry() -> None:
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.fred import fetch_series_observations

    route = respx.get(_FRED_BASE).mock(
        return_value=httpx.Response(400, content=b'{"error_message": "bad series"}')
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError) as exc_info:
            await fetch_series_observations(client=client, series_id="BAD")

    assert exc_info.value.status_code == 400
    assert route.call_count == 1


def test_fred_module_exposes_lazy_rate_limiter() -> None:
    from app.services.source_clients import fred
    from app.services.source_clients._rate_limit import LocalTokenBucket
    from app.services.source_clients._registry import reset_registry

    reset_registry()
    limiter = fred._rate_limiter()
    assert isinstance(limiter, LocalTokenBucket)
    assert fred._rate_limiter() is limiter
