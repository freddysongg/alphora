"""Federal Reserve press releases and speeches client.

The Fed exposes RSS feeds for chronological access:
- `/feeds/press_all.xml` — all press releases (FOMC, supervisory, board actions)
- `/feeds/speeches.xml` — speeches by board members and reserve-bank presidents

Both feeds are XML; we parse them through `xml.etree.ElementTree` and surface a
flat `FedPressItem` list. The `kind` field collapses press release sub-types
(`monetary`, `enforcement`, `bcreg`, `other`) and adds `speech` for speech
items. The Fed adds new <category> values periodically; unknown categories
fall back to `"other"` rather than failing.

Speech detail pages additionally carry the speaker name and venue in the
description (and in the `<dc:creator>` element); we surface what the feed
gives us — the production scraper can enrich by following `url` if needed.
"""
from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Literal
from xml.etree.ElementTree import Element, fromstring

import httpx
from pydantic import BaseModel, ConfigDict

from app.services.source_clients._http import HttpRequestConfig, request
from app.services.source_clients._rate_limit import RateLimiterProtocol
from app.services.source_clients._registry import get_rate_limiter

_FED_RELEASES_URL = "https://www.federalreserve.gov/feeds/press_all.xml"
_FED_SPEECHES_URL = "https://www.federalreserve.gov/feeds/speeches.xml"

_USER_AGENT = "Mozilla/5.0 (compatible; AlphoraResearchBot/1.0)"

FedPressKind = Literal[
    "monetary", "enforcement", "bcreg", "other", "speech"
]


def _rate_limiter() -> RateLimiterProtocol:
    return get_rate_limiter(name="fed_press", rate_per_second=1.0, burst=3)


class FedPressItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    kind: FedPressKind
    title: str
    url: str
    published_at: datetime
    summary: str | None = None
    speaker: str | None = None
    venue: str | None = None


def _norm_kind(raw: str | None, *, is_speech: bool) -> FedPressKind:
    """Map the live Fed RSS category label to one of the normalized kinds.

    The Fed feed emits human-prose labels: `Monetary Policy`,
    `Enforcement Actions`, `Banking and Consumer Regulatory Policy`,
    `Other Announcements`. We also accept the already-normalized lowercase
    forms (`monetary`, `enforcement`, `bcreg`) for callers that pre-massage
    the payload. Substring matching keeps the mapping resilient to minor
    label drift ("Monetary Policy Releases", "Enforcement Actions and
    Investigations", etc.).
    """
    if is_speech:
        return "speech"
    if raw is None:
        return "other"
    lowered = raw.strip().lower()
    if not lowered:
        return "other"
    if "monetary" in lowered:
        return "monetary"
    if "enforcement" in lowered:
        return "enforcement"
    if "banking" in lowered or "regulatory" in lowered or lowered == "bcreg":
        return "bcreg"
    return "other"


def _text(element: Element | None) -> str | None:
    if element is None:
        return None
    text = element.text
    if text is None:
        return None
    stripped = text.strip()
    return stripped or None


def _id_from_url(url: str | None) -> str:
    if url is None:
        return ""
    stem = url.rsplit("/", 1)[-1]
    if stem.endswith(".htm") or stem.endswith(".html"):
        stem = stem.rsplit(".", 1)[0]
    return stem


def _parse_pub_date(raw: str | None) -> datetime:
    if raw is None:
        raise ValueError("Fed press feed item missing pubDate")
    return parsedate_to_datetime(raw)


def _parse_items(xml_bytes: bytes, *, is_speech: bool) -> list[FedPressItem]:
    root = fromstring(xml_bytes)
    items: list[FedPressItem] = []
    for item in root.iter("item"):
        url = _text(item.find("link")) or ""
        title = _text(item.find("title")) or ""
        category_raw = _text(item.find("category"))
        summary = _text(item.find("description"))
        speaker = _text(item.find("{http://purl.org/dc/elements/1.1/}creator"))
        venue = _text(item.find("venue"))
        published_at = _parse_pub_date(_text(item.find("pubDate")))
        items.append(
            FedPressItem(
                id=_id_from_url(url),
                kind=_norm_kind(category_raw, is_speech=is_speech),
                title=title,
                url=url,
                published_at=published_at,
                summary=summary,
                speaker=speaker,
                venue=venue,
            )
        )
    return items


async def fetch_fed_press_releases(
    *,
    client: httpx.AsyncClient,
    feed_url: str = _FED_RELEASES_URL,
) -> tuple[list[FedPressItem], str]:
    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=feed_url,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/rss+xml"},
        ),
        rate_limiter=_rate_limiter(),
    )
    items = _parse_items(response.body_bytes, is_speech=False)
    return items, response.content_hash


async def fetch_fed_speeches(
    *,
    client: httpx.AsyncClient,
    feed_url: str = _FED_SPEECHES_URL,
) -> tuple[list[FedPressItem], str]:
    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=feed_url,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/rss+xml"},
        ),
        rate_limiter=_rate_limiter(),
    )
    items = _parse_items(response.body_bytes, is_speech=True)
    return items, response.content_hash


__all__ = [
    "FedPressItem",
    "FedPressKind",
    "fetch_fed_press_releases",
    "fetch_fed_speeches",
]
