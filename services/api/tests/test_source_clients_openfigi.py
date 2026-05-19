import json
from collections.abc import Iterator

import httpx
import pytest
import respx

_OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"


@pytest.fixture()
def _set_openfigi_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from app.config import get_settings

    monkeypatch.setenv("OPENFIGI_API_KEY", "openfigi-test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@respx.mock
async def test_fetch_openfigi_mapping_parses_batch(_set_openfigi_key: None) -> None:
    from app.services.source_clients.openfigi import fetch_openfigi_mapping

    respx.post(_OPENFIGI_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "data": [
                        {
                            "figi": "BBG000B9XRY4",
                            "name": "APPLE INC",
                            "ticker": "AAPL",
                            "exchCode": "US",
                        }
                    ]
                },
                {"warning": "no match"},
            ],
        )
    )

    async with httpx.AsyncClient() as client:
        results, content_hash = await fetch_openfigi_mapping(
            client=client,
            queries=[
                {"idType": "TICKER", "idValue": "AAPL"},
                {"idType": "TICKER", "idValue": "ZZZZ"},
            ],
        )

    assert len(results) == 2
    assert results[0].data is not None
    assert results[0].data[0].figi == "BBG000B9XRY4"
    assert results[1].warning == "no match"
    assert len(content_hash) == 64


@respx.mock
async def test_fetch_openfigi_mapping_posts_query_body(_set_openfigi_key: None) -> None:
    from app.services.source_clients.openfigi import fetch_openfigi_mapping

    route = respx.post(_OPENFIGI_URL).mock(return_value=httpx.Response(200, json=[]))

    async with httpx.AsyncClient() as client:
        await fetch_openfigi_mapping(
            client=client,
            queries=[{"idType": "TICKER", "idValue": "MSFT"}],
        )

    sent_body = json.loads(route.calls.last.request.content)
    assert sent_body == [{"idType": "TICKER", "idValue": "MSFT"}]


@respx.mock
async def test_fetch_openfigi_mapping_includes_api_key_header_when_configured(
    _set_openfigi_key: None,
) -> None:
    from app.services.source_clients.openfigi import fetch_openfigi_mapping

    route = respx.post(_OPENFIGI_URL).mock(return_value=httpx.Response(200, json=[]))

    async with httpx.AsyncClient() as client:
        await fetch_openfigi_mapping(
            client=client, queries=[{"idType": "TICKER", "idValue": "AAPL"}]
        )

    assert (
        route.calls.last.request.headers["X-OPENFIGI-APIKEY"]
        == "openfigi-test-key"
    )


@respx.mock
async def test_fetch_openfigi_mapping_omits_header_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings
    from app.services.source_clients.openfigi import fetch_openfigi_mapping

    monkeypatch.delenv("OPENFIGI_API_KEY", raising=False)
    get_settings.cache_clear()

    route = respx.post(_OPENFIGI_URL).mock(return_value=httpx.Response(200, json=[]))

    async with httpx.AsyncClient() as client:
        await fetch_openfigi_mapping(
            client=client, queries=[{"idType": "TICKER", "idValue": "AAPL"}]
        )

    assert "X-OPENFIGI-APIKEY" not in route.calls.last.request.headers


@respx.mock
async def test_fetch_openfigi_mapping_403_does_not_retry(
    _set_openfigi_key: None,
) -> None:
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.openfigi import fetch_openfigi_mapping

    route = respx.post(_OPENFIGI_URL).mock(return_value=httpx.Response(403))

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError):
            await fetch_openfigi_mapping(
                client=client, queries=[{"idType": "TICKER", "idValue": "AAPL"}]
            )

    assert route.call_count == 1


def test_openfigi_module_exposes_singleton_rate_limiter() -> None:
    from app.services.source_clients import openfigi
    from app.services.source_clients._rate_limit import RateLimiter

    assert isinstance(openfigi._RATE_LIMITER, RateLimiter)
