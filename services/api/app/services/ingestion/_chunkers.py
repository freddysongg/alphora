import hashlib
from dataclasses import dataclass
from typing import Any

from app.services.source_clients.congress_gov import CongressBill
from app.services.source_clients.fred import FredSeriesObservations
from app.services.source_clients.kalshi import KalshiMarket
from app.services.source_clients.polygon import PolygonAggregatesResponse
from app.services.source_clients.polymarket import PolymarketEvent
from app.services.source_clients.sec_edgar import (
    SecCompanyTickersResponse,
    SecSubmissionsResponse,
)
from app.services.source_clients.tiingo_news import TiingoNewsItem


@dataclass(frozen=True)
class ChunkDraft:
    chunk_index: int
    text: str
    start_offset: int | None
    end_offset: int | None
    attributes: dict[str, Any]
    content_hash: str


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_fred_observations(payload: FredSeriesObservations) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, observation in enumerate(payload.observations):
        value_text = "null" if observation.value is None else str(observation.value)
        text = (
            f"FRED series {payload.series_id} "
            f"observation date={observation.date.isoformat()} "
            f"value={value_text}"
        )
        attributes: dict[str, Any] = {
            "source": "fred",
            "series_id": payload.series_id,
            "date": observation.date.isoformat(),
            "value": value_text if observation.value is not None else None,
            "realtime_start": observation.realtime_start.isoformat(),
            "realtime_end": observation.realtime_end.isoformat(),
        }
        drafts.append(
            ChunkDraft(
                chunk_index=index,
                text=text,
                start_offset=None,
                end_offset=None,
                attributes=attributes,
                content_hash=_hash_text(text),
            )
        )
    return drafts


def chunk_sec_tickers(payload: SecCompanyTickersResponse) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, company in enumerate(payload.companies):
        padded_cik = str(company.cik_str).zfill(10)
        text = (
            f"SEC company ticker={company.ticker} "
            f"title={company.title} cik={padded_cik}"
        )
        attributes: dict[str, Any] = {
            "source": "sec_edgar",
            "cik": padded_cik,
            "ticker": company.ticker,
            "title": company.title,
        }
        drafts.append(
            ChunkDraft(
                chunk_index=index,
                text=text,
                start_offset=None,
                end_offset=None,
                attributes=attributes,
                content_hash=_hash_text(text),
            )
        )
    return drafts


def chunk_sec_submissions(payload: SecSubmissionsResponse) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, submission in enumerate(payload.recent):
        report_date_text = (
            submission.report_date.isoformat() if submission.report_date else "null"
        )
        text = (
            f"SEC filing cik={payload.cik} name={payload.name} "
            f"form={submission.form} accession={submission.accession_number} "
            f"filed={submission.filing_date.isoformat()} "
            f"report_period={report_date_text} "
            f"primary_document={submission.primary_document}"
        )
        attributes: dict[str, Any] = {
            "source": "sec_edgar",
            "cik": payload.cik,
            "name": payload.name,
            "form": submission.form,
            "accession_number": submission.accession_number,
            "filing_date": submission.filing_date.isoformat(),
            "report_date": (
                submission.report_date.isoformat() if submission.report_date else None
            ),
            "primary_document": submission.primary_document,
            "primary_doc_description": submission.primary_doc_description,
        }
        drafts.append(
            ChunkDraft(
                chunk_index=index,
                text=text,
                start_offset=None,
                end_offset=None,
                attributes=attributes,
                content_hash=_hash_text(text),
            )
        )
    return drafts


def chunk_polymarket_events(events: list[PolymarketEvent]) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, event in enumerate(events):
        category_text = event.category if event.category is not None else "unknown"
        text = (
            f"Polymarket event id={event.id} title={event.title} "
            f"slug={event.slug} category={category_text} "
            f"active={event.active} closed={event.closed}"
        )
        attributes: dict[str, Any] = {
            "source": "polymarket_events",
            "event_id": event.id,
            "slug": event.slug,
            "title": event.title,
            "category": event.category,
            "active": event.active,
            "closed": event.closed,
        }
        drafts.append(
            ChunkDraft(
                chunk_index=index,
                text=text,
                start_offset=None,
                end_offset=None,
                attributes=attributes,
                content_hash=_hash_text(text),
            )
        )
    return drafts


def chunk_kalshi_markets(markets: list[KalshiMarket]) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, market in enumerate(markets):
        text = (
            f"Kalshi market ticker={market.ticker} "
            f"event_ticker={market.event_ticker} "
            f"title={market.title} status={market.status} "
            f"open={market.open_time.isoformat()} "
            f"close={market.close_time.isoformat()} "
            f"yes_bid={market.yes_bid} yes_ask={market.yes_ask}"
        )
        attributes: dict[str, Any] = {
            "source": "kalshi_markets",
            "ticker": market.ticker,
            "event_ticker": market.event_ticker,
            "title": market.title,
            "status": market.status,
            "open_time": market.open_time.isoformat(),
            "close_time": market.close_time.isoformat(),
            "yes_bid": market.yes_bid,
            "yes_ask": market.yes_ask,
            "volume": market.volume,
        }
        drafts.append(
            ChunkDraft(
                chunk_index=index,
                text=text,
                start_offset=None,
                end_offset=None,
                attributes=attributes,
                content_hash=_hash_text(text),
            )
        )
    return drafts


def chunk_congress_bills(bills: list[CongressBill]) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, bill in enumerate(bills):
        title_text = bill.title if bill.title is not None else "untitled"
        update_text = (
            bill.updateDate.isoformat() if bill.updateDate is not None else "null"
        )
        text = (
            f"Congress bill {bill.type}-{bill.number} (congress {bill.congress}) "
            f"title={title_text} update_date={update_text}"
        )
        attributes: dict[str, Any] = {
            "source": "congress_bills",
            "congress": bill.congress,
            "type": bill.type,
            "number": bill.number,
            "title": bill.title,
            "update_date": (
                bill.updateDate.isoformat() if bill.updateDate is not None else None
            ),
        }
        drafts.append(
            ChunkDraft(
                chunk_index=index,
                text=text,
                start_offset=None,
                end_offset=None,
                attributes=attributes,
                content_hash=_hash_text(text),
            )
        )
    return drafts


def chunk_polygon_aggregates(payload: PolygonAggregatesResponse) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, bar in enumerate(payload.results):
        text = (
            f"Polygon aggregate ticker={payload.ticker} "
            f"timestamp_ms={bar.timestamp_ms} "
            f"open={bar.open} high={bar.high} low={bar.low} "
            f"close={bar.close} volume={bar.volume}"
        )
        attributes: dict[str, Any] = {
            "source": "polygon_aggregates",
            "ticker": payload.ticker,
            "timestamp_ms": bar.timestamp_ms,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        drafts.append(
            ChunkDraft(
                chunk_index=index,
                text=text,
                start_offset=None,
                end_offset=None,
                attributes=attributes,
                content_hash=_hash_text(text),
            )
        )
    return drafts


def chunk_tiingo_news_items(items: list[TiingoNewsItem]) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, item in enumerate(items):
        tickers_text = ",".join(item.tickers) if item.tickers else "none"
        text = (
            f"Tiingo news id={item.id} title={item.title} "
            f"source={item.source} published={item.publishedDate.isoformat()} "
            f"tickers={tickers_text}"
        )
        attributes: dict[str, Any] = {
            "source": "tiingo_news",
            "news_id": item.id,
            "title": item.title,
            "outlet": item.source,
            "published_date": item.publishedDate.isoformat(),
            "url": item.url,
            "tickers": list(item.tickers),
            "tags": list(item.tags),
        }
        drafts.append(
            ChunkDraft(
                chunk_index=index,
                text=text,
                start_offset=None,
                end_offset=None,
                attributes=attributes,
                content_hash=_hash_text(text),
            )
        )
    return drafts


__all__ = [
    "ChunkDraft",
    "chunk_congress_bills",
    "chunk_fred_observations",
    "chunk_kalshi_markets",
    "chunk_polygon_aggregates",
    "chunk_polymarket_events",
    "chunk_sec_submissions",
    "chunk_sec_tickers",
    "chunk_tiingo_news_items",
]
