import httpx
import pytest
import respx

_GLEIF_SEARCH_URL = "https://api.gleif.org/api/v1/lei-records"
_GLEIF_DETAIL_URL = "https://api.gleif.org/api/v1/lei-records/HWUPKR0MPOU8FGXBT394"


@respx.mock
async def test_fetch_gleif_search_flattens_json_api_payload() -> None:
    from app.services.source_clients.gleif import fetch_gleif_search

    respx.get(_GLEIF_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "type": "lei-records",
                        "id": "HWUPKR0MPOU8FGXBT394",
                        "attributes": {
                            "lei": "HWUPKR0MPOU8FGXBT394",
                            "entity": {
                                "legalName": {"name": "APPLE INC."},
                                "jurisdiction": "US-CA",
                                "otherNames": [
                                    {"name": "Apple Inc"},
                                    {"name": "Apple Computer, Inc."},
                                ],
                            },
                        },
                    }
                ]
            },
        )
    )

    async with httpx.AsyncClient() as client:
        result, content_hash = await fetch_gleif_search(
            client=client, name_query="Apple"
        )

    assert len(result.records) == 1
    record = result.records[0]
    assert record.lei == "HWUPKR0MPOU8FGXBT394"
    assert record.legal_name == "APPLE INC."
    assert record.jurisdiction == "US-CA"
    assert "Apple Inc" in record.other_names
    assert len(content_hash) == 64


@respx.mock
async def test_fetch_gleif_search_sends_name_filter() -> None:
    from app.services.source_clients.gleif import fetch_gleif_search

    route = respx.get(_GLEIF_SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    async with httpx.AsyncClient() as client:
        await fetch_gleif_search(client=client, name_query="Microsoft")

    sent = route.calls.last.request
    assert sent.url.params["filter[entity.legalName]"] == "Microsoft"


@respx.mock
async def test_fetch_gleif_by_lei_parses_single_record() -> None:
    from app.services.source_clients.gleif import fetch_gleif_by_lei

    respx.get(_GLEIF_DETAIL_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "type": "lei-records",
                    "id": "HWUPKR0MPOU8FGXBT394",
                    "attributes": {
                        "lei": "HWUPKR0MPOU8FGXBT394",
                        "entity": {
                            "legalName": {"name": "APPLE INC."},
                            "jurisdiction": "US-CA",
                            "otherNames": [],
                        },
                    },
                }
            },
        )
    )

    async with httpx.AsyncClient() as client:
        record, content_hash = await fetch_gleif_by_lei(
            client=client, lei="HWUPKR0MPOU8FGXBT394"
        )

    assert record.lei == "HWUPKR0MPOU8FGXBT394"
    assert record.legal_name == "APPLE INC."
    assert len(content_hash) == 64


@respx.mock
async def test_fetch_gleif_search_404_does_not_retry() -> None:
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.gleif import fetch_gleif_search

    route = respx.get(_GLEIF_SEARCH_URL).mock(return_value=httpx.Response(404))

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError):
            await fetch_gleif_search(client=client, name_query="nothing")

    assert route.call_count == 1


@respx.mock
async def test_fetch_gleif_by_lei_404_does_not_retry() -> None:
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.gleif import fetch_gleif_by_lei

    route = respx.get(_GLEIF_DETAIL_URL).mock(return_value=httpx.Response(404))

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError):
            await fetch_gleif_by_lei(client=client, lei="HWUPKR0MPOU8FGXBT394")

    assert route.call_count == 1


def test_gleif_module_exposes_singleton_rate_limiter() -> None:
    from app.services.source_clients import gleif
    from app.services.source_clients._rate_limit import RateLimiter

    assert isinstance(gleif._RATE_LIMITER, RateLimiter)
