from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.services.source_clients.congress_gov import CongressBill
from app.services.source_clients.fred import FredSeriesObservations
from app.services.source_clients.kalshi import KalshiMarket
from app.services.source_clients.polymarket import PolymarketEvent
from app.services.source_clients.tiingo_news import TiingoNewsItem


@dataclass(frozen=True)
class SourcePayloads:
    fred: list[FredSeriesObservations]
    polymarket_events: list[PolymarketEvent]
    kalshi_markets: list[KalshiMarket]
    congress_bills: list[CongressBill]
    tiingo_news: list[TiingoNewsItem]


class FredDigestRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    series_id: str
    latest_value: Decimal | None
    previous_value: Decimal | None
    delta_pct: float | None


class MarketDigestRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    title: str
    identifier: str
    status: str
    close_time: str | None
    yes_bid: int | None = None
    yes_ask: int | None = None
    volume: int | None = None


class CongressDigestRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    bill_number: str
    title: str | None
    update_date: str | None


class NewsDigestRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    title: str
    source: str
    published_date: str
    tickers: list[str]


class Digest(BaseModel):
    model_config = ConfigDict(frozen=True)
    fred: list[FredDigestRow]
    polymarket: list[MarketDigestRow]
    kalshi: list[MarketDigestRow]
    congress: list[CongressDigestRow]
    tiingo_news: list[NewsDigestRow]


def _fred_rows(payloads: list[FredSeriesObservations]) -> list[FredDigestRow]:
    rows: list[FredDigestRow] = []
    for series in sorted(payloads, key=lambda s: s.series_id):
        obs_sorted = sorted(series.observations, key=lambda o: o.date)
        latest = obs_sorted[-1].value if obs_sorted else None
        previous = obs_sorted[-2].value if len(obs_sorted) >= 2 else None
        delta_pct: float | None = None
        if latest is not None and previous is not None and previous != 0:
            delta_pct = float((latest - previous) / previous)
        rows.append(
            FredDigestRow(
                series_id=series.series_id,
                latest_value=latest,
                previous_value=previous,
                delta_pct=delta_pct,
            )
        )
    return rows


def _polymarket_rows(events: list[PolymarketEvent]) -> list[MarketDigestRow]:
    return [
        MarketDigestRow(
            title=event.title,
            identifier=event.id,
            status="closed" if event.closed else "active" if event.active else "unknown",
            close_time=None,
        )
        for event in sorted(events, key=lambda e: e.id)
    ]


def _kalshi_rows(markets: list[KalshiMarket]) -> list[MarketDigestRow]:
    return [
        MarketDigestRow(
            title=m.title,
            identifier=m.ticker,
            status=m.status,
            close_time=m.close_time.isoformat() if m.close_time else None,
            yes_bid=m.yes_bid,
            yes_ask=m.yes_ask,
            volume=m.volume,
        )
        for m in sorted(markets, key=lambda x: x.ticker)
    ]


def _congress_rows(bills: list[CongressBill]) -> list[CongressDigestRow]:
    return [
        CongressDigestRow(
            bill_number=f"{b.type}-{b.number} ({b.congress})",
            title=b.title,
            update_date=b.updateDate.isoformat() if b.updateDate else None,
        )
        for b in sorted(bills, key=lambda x: (x.congress, x.type, x.number))
    ]


def _news_rows(items: list[TiingoNewsItem]) -> list[NewsDigestRow]:
    return [
        NewsDigestRow(
            title=i.title,
            source=i.source,
            published_date=i.publishedDate.isoformat(),
            tickers=list(i.tickers),
        )
        for i in sorted(items, key=lambda x: x.id)
    ]


def build_digest(payloads: SourcePayloads) -> Digest:
    return Digest(
        fred=_fred_rows(payloads.fred),
        polymarket=_polymarket_rows(payloads.polymarket_events),
        kalshi=_kalshi_rows(payloads.kalshi_markets),
        congress=_congress_rows(payloads.congress_bills),
        tiingo_news=_news_rows(payloads.tiingo_news),
    )


def render_markdown(digest: Digest) -> str:
    lines: list[str] = []
    lines.append("## FRED")
    if digest.fred:
        lines.append("| series_id | latest | previous | delta_pct |")
        lines.append("|---|---|---|---|")
        for fred_row in digest.fred:
            if fred_row.delta_pct is not None:
                lines.append(
                    f"| {fred_row.series_id} | {fred_row.latest_value} | "
                    f"{fred_row.previous_value} | {fred_row.delta_pct:.4f} |"
                )
            else:
                lines.append(
                    f"| {fred_row.series_id} | {fred_row.latest_value} | "
                    f"{fred_row.previous_value} | n/a |"
                )
    else:
        lines.append("(no data)")
    lines.append("")
    lines.append("## Polymarket")
    if digest.polymarket:
        for poly_row in digest.polymarket:
            lines.append(
                f"- {poly_row.title} (id={poly_row.identifier}, status={poly_row.status})"
            )
    else:
        lines.append("(no data)")
    lines.append("")
    lines.append("## Kalshi")
    if digest.kalshi:
        for kalshi_row in digest.kalshi:
            lines.append(
                f"- {kalshi_row.title} (ticker={kalshi_row.identifier}, "
                f"yes_bid={kalshi_row.yes_bid}, yes_ask={kalshi_row.yes_ask}, "
                f"volume={kalshi_row.volume}, status={kalshi_row.status})"
            )
    else:
        lines.append("(no data)")
    lines.append("")
    lines.append("## Congress")
    if digest.congress:
        for congress_row in digest.congress:
            lines.append(
                f"- {congress_row.bill_number}: {congress_row.title or ''} "
                f"({congress_row.update_date or ''})"
            )
    else:
        lines.append("(no data)")
    lines.append("")
    lines.append("## Tiingo News")
    if digest.tiingo_news:
        for news_row in digest.tiingo_news:
            tickers = ",".join(news_row.tickers) if news_row.tickers else "(none)"
            lines.append(
                f"- [{news_row.source}] {news_row.title} "
                f"({news_row.published_date}, tickers={tickers})"
            )
    else:
        lines.append("(no data)")
    return "\n".join(lines)


__all__ = [
    "CongressDigestRow",
    "Digest",
    "FredDigestRow",
    "MarketDigestRow",
    "NewsDigestRow",
    "SourcePayloads",
    "build_digest",
    "render_markdown",
]
