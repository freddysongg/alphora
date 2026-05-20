import httpx
import pytest
import respx

_RELEASES_URL = "https://www.federalreserve.gov/feeds/press_all.xml"
_SPEECHES_URL = "https://www.federalreserve.gov/feeds/speeches.xml"


_RELEASES_RSS = (
    b"<?xml version='1.0'?>"
    b"<rss><channel>"
    b"<item>"
    b"<title>Federal Reserve issues FOMC statement</title>"
    b"<link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260507a.htm</link>"
    b"<category>monetary</category>"
    b"<description>The FOMC decided to maintain the target range at 4-1/4 to 4-1/2 percent.</description>"
    b"<pubDate>Wed, 07 May 2026 18:00:00 GMT</pubDate>"
    b"</item>"
    b"<item>"
    b"<title>Board issues enforcement action</title>"
    b"<link>https://www.federalreserve.gov/newsevents/pressreleases/enforcement20260512a.htm</link>"
    b"<category>enforcement</category>"
    b"<pubDate>Mon, 12 May 2026 13:00:00 GMT</pubDate>"
    b"</item>"
    b"<item>"
    b"<title>Board issues other release</title>"
    b"<link>https://www.federalreserve.gov/newsevents/pressreleases/other20260514a.htm</link>"
    b"<category>brand-new-uncategorised</category>"
    b"<pubDate>Wed, 14 May 2026 13:00:00 GMT</pubDate>"
    b"</item>"
    b"</channel></rss>"
)


_SPEECHES_RSS = (
    b"<?xml version='1.0'?>"
    b"<rss xmlns:dc='http://purl.org/dc/elements/1.1/'>"
    b"<channel>"
    b"<item>"
    b"<title>Chair Powell - Outlook for Inflation and Employment</title>"
    b"<link>https://www.federalreserve.gov/newsevents/speech/powell20260512a.htm</link>"
    b"<description>Recent data suggest inflation is moving sustainably toward 2 percent.</description>"
    b"<pubDate>Mon, 12 May 2026 13:00:00 GMT</pubDate>"
    b"<dc:creator>Jerome H. Powell</dc:creator>"
    b"<venue>Council on Foreign Relations, New York</venue>"
    b"</item>"
    b"</channel></rss>"
)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_fed_press_releases_parses_rss() -> None:
    from app.services.source_clients.fed_press import fetch_fed_press_releases

    respx.get(_RELEASES_URL).mock(
        return_value=httpx.Response(
            200,
            content=_RELEASES_RSS,
            headers={"Content-Type": "application/rss+xml"},
        )
    )

    async with httpx.AsyncClient() as client:
        items, content_hash = await fetch_fed_press_releases(client=client)

    assert len(items) == 3
    assert items[0].id == "monetary20260507a"
    assert items[0].kind == "monetary"
    assert items[0].title == "Federal Reserve issues FOMC statement"
    assert items[0].summary is not None
    assert "2 percent" in (items[0].summary or "")
    assert items[1].kind == "enforcement"
    assert items[2].kind == "other"
    assert len(content_hash) == 64


@pytest.mark.asyncio
@respx.mock
async def test_fetch_fed_speeches_parses_speaker_and_venue() -> None:
    from app.services.source_clients.fed_press import fetch_fed_speeches

    respx.get(_SPEECHES_URL).mock(
        return_value=httpx.Response(
            200,
            content=_SPEECHES_RSS,
            headers={"Content-Type": "application/rss+xml"},
        )
    )

    async with httpx.AsyncClient() as client:
        items, _ = await fetch_fed_speeches(client=client)

    assert len(items) == 1
    item = items[0]
    assert item.kind == "speech"
    assert item.speaker == "Jerome H. Powell"
    assert item.venue == "Council on Foreign Relations, New York"
    assert item.id == "powell20260512a"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_fed_press_releases_500_retries() -> None:
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.fed_press import fetch_fed_press_releases

    route = respx.get(_RELEASES_URL).mock(return_value=httpx.Response(500))

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError):
            await fetch_fed_press_releases(client=client)

    assert route.call_count == 4


@pytest.mark.asyncio
@respx.mock
async def test_fetch_fed_press_releases_empty_feed_yields_empty_list() -> None:
    from app.services.source_clients.fed_press import fetch_fed_press_releases

    respx.get(_RELEASES_URL).mock(
        return_value=httpx.Response(
            200,
            content=b"<rss><channel></channel></rss>",
            headers={"Content-Type": "application/rss+xml"},
        )
    )

    async with httpx.AsyncClient() as client:
        items, _ = await fetch_fed_press_releases(client=client)

    assert items == []


def test_fed_press_module_exposes_lazy_rate_limiter() -> None:
    from app.services.source_clients import fed_press
    from app.services.source_clients._rate_limit import LocalTokenBucket
    from app.services.source_clients._registry import reset_registry

    reset_registry()
    limiter = fed_press._rate_limiter()
    assert isinstance(limiter, LocalTokenBucket)
    assert fed_press._rate_limiter() is limiter


_LIVE_RSS = (
    b"<?xml version='1.0'?>"
    b"<rss><channel>"
    b"<item>"
    b"<title>FOMC statement</title>"
    b"<link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260507a.htm</link>"
    b"<category>Monetary Policy</category>"
    b"<pubDate>Wed, 07 May 2026 18:00:00 GMT</pubDate>"
    b"</item>"
    b"<item>"
    b"<title>Enforcement action against First Republic</title>"
    b"<link>https://www.federalreserve.gov/newsevents/pressreleases/enforcement20260512a.htm</link>"
    b"<category>Enforcement Actions</category>"
    b"<pubDate>Mon, 12 May 2026 13:00:00 GMT</pubDate>"
    b"</item>"
    b"<item>"
    b"<title>Capital ratios proposal</title>"
    b"<link>https://www.federalreserve.gov/newsevents/pressreleases/bcreg20260514a.htm</link>"
    b"<category>Banking and Consumer Regulatory Policy</category>"
    b"<pubDate>Wed, 14 May 2026 13:00:00 GMT</pubDate>"
    b"</item>"
    b"<item>"
    b"<title>Other announcement</title>"
    b"<link>https://www.federalreserve.gov/newsevents/pressreleases/other20260515a.htm</link>"
    b"<category>Other Announcements</category>"
    b"<pubDate>Thu, 15 May 2026 13:00:00 GMT</pubDate>"
    b"</item>"
    b"</channel></rss>"
)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_fed_press_releases_maps_live_category_labels() -> None:
    """The live Fed RSS feed emits human-prose category labels — not the
    normalized lowercase forms. Regression for the bug where every live
    release fell through to `other`."""
    from app.services.source_clients.fed_press import fetch_fed_press_releases

    respx.get(_RELEASES_URL).mock(
        return_value=httpx.Response(
            200,
            content=_LIVE_RSS,
            headers={"Content-Type": "application/rss+xml"},
        )
    )

    async with httpx.AsyncClient() as client:
        items, _ = await fetch_fed_press_releases(client=client)

    assert [item.kind for item in items] == [
        "monetary",
        "enforcement",
        "bcreg",
        "other",
    ]


def test_norm_kind_substring_mapping_covers_label_drift() -> None:
    """Substring matching keeps the mapping resilient to minor Fed feed
    label edits without requiring the adapter to track an exact-string
    allowlist."""
    from app.services.source_clients.fed_press import _norm_kind

    assert _norm_kind("Monetary Policy Releases", is_speech=False) == "monetary"
    assert _norm_kind("Enforcement Actions and Investigations", is_speech=False) == "enforcement"
    assert _norm_kind("Banking Regulation Update", is_speech=False) == "bcreg"
    assert _norm_kind("Consumer Regulatory Notice", is_speech=False) == "bcreg"
    assert _norm_kind("bcreg", is_speech=False) == "bcreg"
    assert _norm_kind("monetary", is_speech=False) == "monetary"
    assert _norm_kind("Other Announcements", is_speech=False) == "other"
    assert _norm_kind("", is_speech=False) == "other"
    assert _norm_kind(None, is_speech=False) == "other"
    assert _norm_kind("anything", is_speech=True) == "speech"
