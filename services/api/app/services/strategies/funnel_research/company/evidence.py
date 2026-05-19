"""Company evidence fetch + ingest for Stage 3 fan-out.

For a single company deep-dive, fetches:
- Polygon daily aggregates for the company ticker.
- Tiingo news scoped to the company ticker.
- Ainvest congressional trading activity scoped to the ticker.
- SEC EDGAR submissions for the company CIK (when resolved upstream).

Per-source failures are isolated to warn-level run events. Returns the
combined `IngestedEvidence` list plus the chunk refs used by downstream
synthesis/verifier. If all sources fail or yield zero chunks, returns an
empty result (caller decides whether to skip the company).
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
from app.services.ingestion.ainvest_congress import (
    ingest_ainvest_congress_transactions,
)
from app.services.ingestion.polygon_aggregates import ingest_polygon_aggregates
from app.services.ingestion.sec_filings import ingest_sec_submissions
from app.services.ingestion.tiingo_news_items import ingest_tiingo_news_items
from app.services.run_events import emit_run_event
from app.services.source_clients.ainvest import (
    AinvestCongressResponse,
    fetch_ainvest_congress_transactions,
)
from app.services.source_clients.polygon import (
    PolygonAggregatesResponse,
    fetch_polygon_aggregates,
)
from app.services.source_clients.sec_edgar import (
    SecSubmissionsResponse,
    fetch_submissions,
)
from app.services.source_clients.tiingo_news import (
    TiingoNewsItem,
    fetch_tiingo_news,
)
from app.services.strategies.funnel_research.company.selector import CompanyIdea
from app.services.strategies.funnel_research.config import TIINGO_NEWS_FETCH_LIMIT

_AGGREGATE_LOOKBACK_DAYS = 30


@dataclass(frozen=True)
class CompanyEvidenceResult:
    evidence: list[IngestedEvidence]
    chunks: list[EvidenceChunkRef]


PolygonAggregatesCallable = Callable[
    [httpx.AsyncClient, str, date, date], Awaitable[tuple[PolygonAggregatesResponse, str]]
]
TiingoNewsCallable = Callable[
    [httpx.AsyncClient, list[str], int], Awaitable[tuple[list[TiingoNewsItem], str]]
]
AinvestCongressCallable = Callable[
    [httpx.AsyncClient, str], Awaitable[tuple[AinvestCongressResponse, str]]
]
SecSubmissionsCallable = Callable[
    [httpx.AsyncClient, str], Awaitable[tuple[SecSubmissionsResponse, str]]
]


@dataclass(frozen=True)
class CompanySourceFetcher:
    polygon_aggregates: PolygonAggregatesCallable
    tiingo_news: TiingoNewsCallable
    ainvest_congress: AinvestCongressCallable
    sec_submissions: SecSubmissionsCallable


def default_company_fetcher() -> CompanySourceFetcher:
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

    async def fetch_ainvest(
        client: httpx.AsyncClient,
        ticker: str,
    ) -> tuple[AinvestCongressResponse, str]:
        return await fetch_ainvest_congress_transactions(
            client=client, ticker=ticker
        )

    async def fetch_sec(
        client: httpx.AsyncClient,
        cik: str,
    ) -> tuple[SecSubmissionsResponse, str]:
        return await fetch_submissions(client=client, cik=cik)

    return CompanySourceFetcher(
        polygon_aggregates=fetch_aggs,
        tiingo_news=fetch_news,
        ainvest_congress=fetch_ainvest,
        sec_submissions=fetch_sec,
    )


async def fetch_company_evidence(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    company_idea: CompanyIdea,
    cik: str | None,
    http_client: httpx.AsyncClient,
    fetcher: CompanySourceFetcher | None = None,
    today: date | None = None,
) -> CompanyEvidenceResult:
    """Fetch + ingest company evidence. Per-source failures isolated to warn events."""
    active_fetcher = fetcher or default_company_fetcher()
    end = today or datetime.now(UTC).date()
    start = end - timedelta(days=_AGGREGATE_LOOKBACK_DAYS)

    ingested: list[IngestedEvidence] = []

    aggs = await _fetch_aggregates(
        session=session,
        run_id=run_id,
        company_name=company_idea.company_name,
        ticker=company_idea.ticker,
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
        company_name=company_idea.company_name,
        ticker=company_idea.ticker,
        http_client=http_client,
        fetcher=active_fetcher,
    )
    if news is not None:
        ingested.append(news)
    await session.commit()

    ainvest = await _fetch_ainvest(
        session=session,
        run_id=run_id,
        company_name=company_idea.company_name,
        ticker=company_idea.ticker,
        http_client=http_client,
        fetcher=active_fetcher,
    )
    if ainvest is not None:
        ingested.append(ainvest)
    await session.commit()

    sec = await _fetch_sec(
        session=session,
        run_id=run_id,
        company_name=company_idea.company_name,
        cik=cik,
        http_client=http_client,
        fetcher=active_fetcher,
    )
    if sec is not None:
        ingested.append(sec)
    await session.commit()

    chunk_refs = await _load_chunk_refs(
        session=session,
        evidence_ids=[entry.evidence_id for entry in ingested],
    )
    return CompanyEvidenceResult(evidence=ingested, chunks=chunk_refs)


async def _fetch_aggregates(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    company_name: str,
    ticker: str | None,
    http_client: httpx.AsyncClient,
    fetcher: CompanySourceFetcher,
    from_date: date,
    to_date: date,
) -> IngestedEvidence | None:
    if ticker is None:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="polygon_aggregates",
            reason="no ticker available",
        )
        return None
    try:
        payload, content_hash = await fetcher.polygon_aggregates(
            http_client, ticker, from_date, to_date
        )
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="polygon_aggregates",
            reason=str(exc),
        )
        return None
    if not payload.results:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
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
            company=company_name,
            source="polygon_aggregates",
            reason=f"ingest failed: {exc}",
        )
        return None


async def _fetch_news(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    company_name: str,
    ticker: str | None,
    http_client: httpx.AsyncClient,
    fetcher: CompanySourceFetcher,
) -> IngestedEvidence | None:
    if ticker is None:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="tiingo_news",
            reason="no ticker available",
        )
        return None
    try:
        items, content_hash = await fetcher.tiingo_news(
            http_client, [ticker], TIINGO_NEWS_FETCH_LIMIT
        )
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="tiingo_news",
            reason=str(exc),
        )
        return None
    if not items:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
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
            company=company_name,
            source="tiingo_news",
            reason=f"ingest failed: {exc}",
        )
        return None


async def _fetch_ainvest(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    company_name: str,
    ticker: str | None,
    http_client: httpx.AsyncClient,
    fetcher: CompanySourceFetcher,
) -> IngestedEvidence | None:
    if ticker is None:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="ainvest_congress",
            reason="no ticker available",
        )
        return None
    try:
        payload, content_hash = await fetcher.ainvest_congress(http_client, ticker)
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="ainvest_congress",
            reason=str(exc),
        )
        return None
    if not payload.data.data:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="ainvest_congress",
            reason="no transactions returned",
        )
        return None
    try:
        return await ingest_ainvest_congress_transactions(
            session=session,
            ticker=ticker,
            payload=payload,
            content_hash=content_hash,
            raw_url=None,
        )
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="ainvest_congress",
            reason=f"ingest failed: {exc}",
        )
        return None


async def _fetch_sec(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    company_name: str,
    cik: str | None,
    http_client: httpx.AsyncClient,
    fetcher: CompanySourceFetcher,
) -> IngestedEvidence | None:
    if cik is None:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="sec_edgar",
            reason="no cik available",
        )
        return None
    try:
        payload, content_hash = await fetcher.sec_submissions(http_client, cik)
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="sec_edgar",
            reason=str(exc),
        )
        return None
    if not payload.recent:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="sec_edgar",
            reason="no submissions returned",
        )
        return None
    try:
        return await ingest_sec_submissions(
            session=session,
            payload=payload,
            content_hash=content_hash,
            raw_url=None,
        )
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="sec_edgar",
            reason=f"ingest failed: {exc}",
        )
        return None


def _warn(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    company: str,
    source: str,
    reason: str,
) -> None:
    data: dict[str, Any] = {
        "event": "company_source_failure",
        "company": company,
        "source": source,
        "reason": reason,
    }
    emit_run_event(
        session,
        run_id=run_id,
        level=RunEventLevel.warn,
        message=f"company {company!r} source {source!r} failed: {reason}",
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
    "CompanyEvidenceResult",
    "CompanySourceFetcher",
    "default_company_fetcher",
    "fetch_company_evidence",
]
