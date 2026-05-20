from collections.abc import Iterator

import httpx
import pytest
import respx

_BILLS_URL = "https://api.congress.gov/v3/bill"
_MEMBERS_URL = "https://api.congress.gov/v3/member"


@pytest.fixture(autouse=True)
def _set_congress_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from app.config import get_settings

    monkeypatch.setenv("CONGRESS_API_KEY", "congress-test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@respx.mock
async def test_fetch_congress_bills_parses_payload() -> None:
    from app.services.source_clients.congress_gov import fetch_congress_bills

    respx.get(_BILLS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "bills": [
                    {
                        "congress": 118,
                        "type": "HR",
                        "number": "1234",
                        "title": "Sample bill",
                        "updateDate": "2024-01-02T00:00:00Z",
                    }
                ]
            },
        )
    )

    async with httpx.AsyncClient() as client:
        result, content_hash = await fetch_congress_bills(client=client)

    assert len(result.bills) == 1
    assert result.bills[0].congress == 118
    assert result.bills[0].number == "1234"
    assert len(content_hash) == 64


@respx.mock
async def test_fetch_congress_bills_sends_api_key_param() -> None:
    from app.services.source_clients.congress_gov import fetch_congress_bills

    route = respx.get(f"{_BILLS_URL}/118/hr").mock(
        return_value=httpx.Response(200, json={"bills": []})
    )

    async with httpx.AsyncClient() as client:
        await fetch_congress_bills(client=client, congress=118, bill_type="hr")

    sent = route.calls.last.request
    assert sent.url.params["api_key"] == "congress-test-key"
    assert sent.url.params["format"] == "json"


async def test_fetch_congress_bills_raises_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings
    from app.services.source_clients._http import SourceClientConfigError
    from app.services.source_clients.congress_gov import fetch_congress_bills

    monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
    get_settings.cache_clear()

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientConfigError) as exc_info:
            await fetch_congress_bills(client=client)

    assert exc_info.value.setting_name == "congress_api_key"


@respx.mock
async def test_fetch_congress_bills_403_does_not_retry() -> None:
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.congress_gov import fetch_congress_bills

    route = respx.get(_BILLS_URL).mock(return_value=httpx.Response(403))

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError):
            await fetch_congress_bills(client=client)

    assert route.call_count == 1


@respx.mock
async def test_fetch_congress_members_parses_payload() -> None:
    from app.services.source_clients.congress_gov import fetch_congress_members

    respx.get(_MEMBERS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "members": [
                    {
                        "bioguideId": "P000197",
                        "name": "Pelosi, Nancy",
                        "state": "California",
                        "partyName": "Democratic",
                    }
                ]
            },
        )
    )

    async with httpx.AsyncClient() as client:
        result, content_hash = await fetch_congress_members(client=client)

    assert len(result.members) == 1
    assert result.members[0].bioguideId == "P000197"
    assert len(content_hash) == 64


async def test_fetch_congress_members_raises_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings
    from app.services.source_clients._http import SourceClientConfigError
    from app.services.source_clients.congress_gov import fetch_congress_members

    monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
    get_settings.cache_clear()

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientConfigError) as exc_info:
            await fetch_congress_members(client=client)

    assert exc_info.value.setting_name == "congress_api_key"


def test_congress_module_exposes_lazy_rate_limiter() -> None:
    from app.services.source_clients import congress_gov
    from app.services.source_clients._rate_limit import LocalTokenBucket
    from app.services.source_clients._registry import reset_registry

    reset_registry()
    limiter = congress_gov._rate_limiter()
    assert isinstance(limiter, LocalTokenBucket)
    assert congress_gov._rate_limiter() is limiter
