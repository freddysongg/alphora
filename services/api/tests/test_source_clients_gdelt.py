from datetime import datetime

import httpx
import pytest
import respx

_GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def _sample_payload() -> dict[str, object]:
    return {
        "articles": [
            {
                "url": "https://example.com/article-a",
                "title": "China announces new export controls on rare earths",
                "seendate": "20260518T143000Z",
                "domain": "reuters.com",
                "language": "English",
                "sourcecountry": "United States",
                "tone": -3.5,
                "themes": ["TRADE", "ENV_MINING", "GEOPOLITICS"],
            },
            {
                "url": "https://example.com/article-b",
                "title": "Semiconductor stocks rally on supply concerns",
                "seendate": "20260518T160000Z",
                "domain": "wsj.com",
                "language": "English",
                "sourcecountry": "United States",
                "tone": 1.2,
                "themes": "ECON_STOCKMARKET;TECH_SEMICONDUCTORS",
            },
        ]
    }


@pytest.mark.asyncio
@respx.mock
async def test_fetch_gdelt_articles_parses_payload() -> None:
    from app.services.source_clients.gdelt import fetch_gdelt_articles

    respx.get(_GDELT_URL).mock(
        return_value=httpx.Response(200, json=_sample_payload())
    )

    async with httpx.AsyncClient() as client:
        result, content_hash = await fetch_gdelt_articles(
            client=client, query="rare earth", max_records=10
        )

    assert len(result.articles) == 2
    first = result.articles[0]
    assert first.title.startswith("China announces")
    assert first.seendate.year == 2026
    assert first.seendate.tzinfo is not None
    assert first.tone == pytest.approx(-3.5)
    assert first.themes == ["TRADE", "ENV_MINING", "GEOPOLITICS"]
    assert len(content_hash) == 64


@pytest.mark.asyncio
@respx.mock
async def test_fetch_gdelt_articles_coerces_themes_string_form() -> None:
    from app.services.source_clients.gdelt import fetch_gdelt_articles

    respx.get(_GDELT_URL).mock(
        return_value=httpx.Response(200, json=_sample_payload())
    )

    async with httpx.AsyncClient() as client:
        result, _ = await fetch_gdelt_articles(
            client=client, query="semiconductors", max_records=10
        )

    second = result.articles[1]
    assert second.themes == ["ECON_STOCKMARKET", "TECH_SEMICONDUCTORS"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_gdelt_articles_passes_filter_params() -> None:
    from app.services.source_clients.gdelt import fetch_gdelt_articles

    route = respx.get(_GDELT_URL).mock(
        return_value=httpx.Response(200, json={"articles": []})
    )

    async with httpx.AsyncClient() as client:
        await fetch_gdelt_articles(
            client=client,
            query="fed funds",
            max_records=42,
            start_datetime=datetime(2026, 5, 1, 0, 0, 0),
            end_datetime=datetime(2026, 5, 18, 0, 0, 0),
        )

    sent = route.calls.last.request
    assert sent.url.params["query"] == "fed funds"
    assert sent.url.params["mode"] == "ArtList"
    assert sent.url.params["format"] == "json"
    assert sent.url.params["maxrecords"] == "42"
    assert sent.url.params["startdatetime"] == "20260501000000"
    assert sent.url.params["enddatetime"] == "20260518000000"


@pytest.mark.asyncio
async def test_fetch_gdelt_articles_rejects_oversized_max_records() -> None:
    from app.services.source_clients.gdelt import fetch_gdelt_articles

    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="caps maxrecords at 250"):
            await fetch_gdelt_articles(
                client=client, query="x", max_records=251
            )


@pytest.mark.asyncio
@respx.mock
async def test_fetch_gdelt_articles_500_retries() -> None:
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.gdelt import fetch_gdelt_articles

    route = respx.get(_GDELT_URL).mock(return_value=httpx.Response(500))

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError):
            await fetch_gdelt_articles(client=client, query="x")

    assert route.call_count == 4


@pytest.mark.asyncio
@respx.mock
async def test_fetch_gdelt_articles_handles_array_only_payload() -> None:
    """Some GDELT responses (e.g. timeline mode used to return an array). We
    coerce non-dict responses to an empty article list rather than crash."""
    from app.services.source_clients.gdelt import fetch_gdelt_articles

    respx.get(_GDELT_URL).mock(return_value=httpx.Response(200, json=[]))

    async with httpx.AsyncClient() as client:
        result, _ = await fetch_gdelt_articles(client=client, query="x")

    assert result.articles == []


def test_gdelt_module_exposes_lazy_rate_limiter() -> None:
    from app.services.source_clients import gdelt
    from app.services.source_clients._rate_limit import LocalTokenBucket
    from app.services.source_clients._registry import reset_registry

    reset_registry()
    limiter = gdelt._rate_limiter()
    assert isinstance(limiter, LocalTokenBucket)
    assert gdelt._rate_limiter() is limiter
