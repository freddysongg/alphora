"""Sector evidence fetch + ingest for Stage 2 fan-out.

For a single sector call, fetches:
- Tiingo news scoped to the sector's representative tickers.
- Polygon daily aggregates for the sector's proxy ETF.

Per-source failures are isolated (warn-level run events). Returns the
combined `IngestedEvidence` list plus the chunk refs used by downstream
synthesis/verifier. If all sources fail or yield zero chunks, returns an
empty result (caller decides whether to skip the sector).
"""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.db.models_runs import RunEventLevel
from app.schemas.extraction import EvidenceChunkRef, IngestedEvidence
from app.schemas.macro_brief import SectorCall
from app.services.ingestion.polygon_aggregates import ingest_polygon_aggregates
from app.services.ingestion.tiingo_news_items import ingest_tiingo_news_items
from app.services.run_events import emit_run_event
from app.services.source_clients.polygon import (
    PolygonAggregatesResponse,
    fetch_polygon_aggregates,
)
from app.services.source_clients.tiingo_news import (
    TiingoNewsItem,
    fetch_tiingo_news,
)
from app.services.strategies.funnel_research.config import TIINGO_NEWS_FETCH_LIMIT
from app.services.strategies.funnel_research.sector_constituents import (
    SectorConstituents,
)

_AGGREGATE_LOOKBACK_DAYS = 30


@dataclass(frozen=True)
class SectorEvidenceResult:
    evidence: list[IngestedEvidence]
    chunks: list[EvidenceChunkRef]


PolygonAggregatesCallable = Callable[
    [httpx.AsyncClient, str, date, date], Awaitable[tuple[PolygonAggregatesResponse, str]]
]
TiingoNewsCallable = Callable[
    [httpx.AsyncClient, list[str], int], Awaitable[tuple[list[TiingoNewsItem], str]]
]


@dataclass(frozen=True)
class SectorSourceFetcher:
    polygon_aggregates: PolygonAggregatesCallable
    tiingo_news: TiingoNewsCallable


def default_sector_fetcher() -> SectorSourceFetcher:
    async def fetch_aggs(
        client: httpx.AsyncClient,
        ticker: str,
        from_date: date,
        to_date: date,
    ) -> tuple[PolygonAggregatesResponse, str]:
        return await fetch_polygon_aggregates(
            client=client,
            ticker=ticker,
            multiplier=1,
            timespan="day",
            from_date=from_date,
            to_date=to_date,
        )

    async def fetch_news(
        client: httpx.AsyncClient,
        tickers: list[str],
        limit: int,
    ) -> tuple[list[TiingoNewsItem], str]:
        return await fetch_tiingo_news(client=client, tickers=tickers, limit=limit)

    return SectorSourceFetcher(
        polygon_aggregates=fetch_aggs,
        tiingo_news=fetch_news,
    )


async def fetch_sector_evidence(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    sector_call: SectorCall,
    constituents: SectorConstituents,
    http_client: httpx.AsyncClient,
    fetcher: SectorSourceFetcher | None = None,
    today: date | None = None,
) -> SectorEvidenceResult:
    """Fetch + ingest sector evidence. Per-source failures isolated to warn events."""
    active_fetcher = fetcher or default_sector_fetcher()
    end = today or datetime.now(UTC).date()
    start = end - timedelta(days=_AGGREGATE_LOOKBACK_DAYS)

    ingested: list[IngestedEvidence] = []

    aggs = await _fetch_aggregates(
        session=session,
        run_id=run_id,
        sector_name=sector_call.sector_name,
        proxy_ticker=constituents.proxy_ticker,
        http_client=http_client,
        fetcher=active_fetcher,
        from_date=start,
        to_date=end,
    )
    if aggs is not None:
        ingested.append(aggs)
    await session.commit()

    news = await _fetch_news(
        session=session,
        run_id=run_id,
        sector_name=sector_call.sector_name,
        representative_tickers=list(constituents.representative_tickers),
        http_client=http_client,
        fetcher=active_fetcher,
    )
    if news is not None:
        ingested.append(news)
    await session.commit()

    chunk_refs = await _load_chunk_refs(
        session=session,
        evidence_ids=[entry.evidence_id for entry in ingested],
    )
    return SectorEvidenceResult(evidence=ingested, chunks=chunk_refs)


async def _fetch_aggregates(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    sector_name: str,
    proxy_ticker: str,
    http_client: httpx.AsyncClient,
    fetcher: SectorSourceFetcher,
    from_date: date,
    to_date: date,
) -> IngestedEvidence | None:
    try:
        payload, content_hash = await fetcher.polygon_aggregates(
            http_client, proxy_ticker, from_date, to_date
        )
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            sector=sector_name,
            source="polygon_aggregates",
            reason=str(exc),
        )
        return None
    if not payload.results:
        _warn(
            session,
            run_id=run_id,
            sector=sector_name,
            source="polygon_aggregates",
            reason="no aggregates returned",
        )
        return None
    try:
        return await ingest_polygon_aggregates(
            session=session,
            payload=payload,
            from_date=from_date,
            to_date=to_date,
            multiplier=1,
            timespan="day",
            content_hash=content_hash,
        )
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            sector=sector_name,
            source="polygon_aggregates",
            reason=f"ingest failed: {exc}",
        )
        return None


async def _fetch_news(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    sector_name: str,
    representative_tickers: list[str],
    http_client: httpx.AsyncClient,
    fetcher: SectorSourceFetcher,
) -> IngestedEvidence | None:
    try:
        items, content_hash = await fetcher.tiingo_news(
            http_client, representative_tickers, TIINGO_NEWS_FETCH_LIMIT
        )
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            sector=sector_name,
            source="tiingo_news",
            reason=str(exc),
        )
        return None
    if not items:
        _warn(
            session,
            run_id=run_id,
            sector=sector_name,
            source="tiingo_news",
            reason="no news returned",
        )
        return None
    try:
        return await ingest_tiingo_news_items(
            session=session,
            items=items,
            content_hash=content_hash,
            raw_url=None,
        )
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            sector=sector_name,
            source="tiingo_news",
            reason=f"ingest failed: {exc}",
        )
        return None


def _warn(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    sector: str,
    source: str,
    reason: str,
) -> None:
    data: dict[str, Any] = {
        "event": "sector_source_failure",
        "sector": sector,
        "source": source,
        "reason": reason,
    }
    emit_run_event(
        session,
        run_id=run_id,
        level=RunEventLevel.warn,
        message=f"sector {sector!r} source {source!r} failed: {reason}",
        data=data,
    )


async def _load_chunk_refs(
    *,
    session: AsyncSession,
    evidence_ids: list[uuid.UUID],
) -> list[EvidenceChunkRef]:
    if not evidence_ids:
        return []
    rows = (
        await session.execute(
            select(EvidenceChunk).where(EvidenceChunk.evidence_id.in_(evidence_ids))
        )
    ).scalars().all()
    return [
        EvidenceChunkRef(
            evidence_id=row.evidence_id,
            chunk_id=row.id,
            chunk_index=row.chunk_index,
            text=row.text,
            attributes=row.attributes or {},
        )
        for row in rows
    ]


__all__ = [
    "SectorEvidenceResult",
    "SectorSourceFetcher",
    "default_sector_fetcher",
    "fetch_sector_evidence",
]
