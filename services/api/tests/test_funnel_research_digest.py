from datetime import UTC, date, datetime
from decimal import Decimal

from app.services.source_clients.congress_gov import CongressBill
from app.services.source_clients.fred import FredObservation, FredSeriesObservations
from app.services.source_clients.kalshi import KalshiMarket
from app.services.source_clients.polymarket import PolymarketEvent
from app.services.source_clients.tiingo_news import TiingoNewsItem


def _payloads():
    from app.services.strategies.funnel_research._digest import SourcePayloads

    return SourcePayloads(
        fred=[
            FredSeriesObservations(
                series_id="CPIAUCSL",
                observation_start=date(2025, 1, 1),
                observation_end=date(2026, 5, 1),
                count=2,
                observations=[
                    FredObservation(
                        date=date(2025, 5, 1),
                        value=Decimal("310.0"),
                        realtime_start=date(2025, 5, 15),
                        realtime_end=date(2026, 1, 1),
                    ),
                    FredObservation(
                        date=date(2026, 5, 1),
                        value=Decimal("320.0"),
                        realtime_start=date(2026, 5, 15),
                        realtime_end=date(2026, 12, 31),
                    ),
                ],
            )
        ],
        polymarket_events=[
            PolymarketEvent(id="e1", slug="x", title="Fed cuts", active=True, closed=False, category="economics"),
        ],
        kalshi_markets=[
            KalshiMarket(
                ticker="FED-25",
                event_ticker="FED",
                title="Fed in 2025",
                status="open",
                yes_bid=10,
                yes_ask=20,
                open_time=datetime(2025, 1, 1, tzinfo=UTC),
                close_time=datetime(2025, 12, 31, tzinfo=UTC),
                volume=42,
            ),
        ],
        congress_bills=[
            CongressBill(
                congress=119,
                type="HR",
                number="1",
                title="Bill",
                updateDate=datetime(2026, 1, 2, tzinfo=UTC),
            ),
        ],
        tiingo_news=[
            TiingoNewsItem(
                id=1, title="Headline", description=None, url="https://x",
                publishedDate=datetime(2026, 5, 18, tzinfo=UTC),
                source="Reuters", tickers=["spy"], tags=[],
            ),
        ],
    )


def test_digest_is_deterministic_for_fixed_inputs() -> None:
    from app.services.strategies.funnel_research._digest import build_digest

    a = build_digest(_payloads())
    b = build_digest(_payloads())
    assert a == b


def test_render_markdown_contains_section_headers() -> None:
    from app.services.strategies.funnel_research._digest import build_digest, render_markdown

    digest = build_digest(_payloads())
    md = render_markdown(digest)
    assert "## FRED" in md
    assert "## Polymarket" in md
    assert "## Kalshi" in md
    assert "## Congress" in md
    assert "## Tiingo News" in md
    assert "CPIAUCSL" in md
    assert "Fed cuts" in md
