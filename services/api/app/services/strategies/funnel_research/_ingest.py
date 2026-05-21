import asyncio
import inspect
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.db.models_runs import RunEventLevel
from app.schemas.extraction import EvidenceChunkRef, IngestedEvidence
from app.services.ingestion import (
    ingest_congress_bills,
    ingest_fred_series_observations,
    ingest_kalshi_markets,
    ingest_polymarket_events,
    ingest_tiingo_news_items,
)
from app.services.run_events import emit_run_event
from app.services.source_clients.congress_gov import (
    CongressBill,
    fetch_congress_bills,
)
from app.services.source_clients.fred import (
    FredSeriesObservations,
    fetch_series_observations,
)
from app.services.source_clients.kalshi import KalshiMarket, fetch_kalshi_markets
from app.services.source_clients.polymarket import (
    PolymarketEvent,
    fetch_polymarket_events,
)
from app.services.source_clients.tiingo_news import (
    TiingoNewsItem,
    fetch_tiingo_news,
)
from app.services.strategies.funnel_research._digest import SourcePayloads
from app.services.strategies.funnel_research._errors import FunnelResearchError
from app.services.strategies.funnel_research.config import (
    CONGRESS_BILLS_FETCH_LIMIT,
    FRED_SERIES,
    KALSHI_FETCH_LIMIT,
    POLYMARKET_FETCH_LIMIT,
    TIINGO_NEWS_FETCH_LIMIT,
)


@dataclass(frozen=True)
class IngestStageResult:
    evidence: list[IngestedEvidence]
    chunks: list[EvidenceChunkRef]
    payloads: SourcePayloads


FredCallable = Callable[[httpx.AsyncClient, str], Any]
PolymarketCallable = Callable[[httpx.AsyncClient, int], Any]
KalshiCallable = Callable[[httpx.AsyncClient, int], Any]
CongressCallable = Callable[[httpx.AsyncClient, int], Any]
TiingoNewsCallable = Callable[[httpx.AsyncClient, int], Any]


@dataclass(frozen=True)
class SourceFetcher:
    fred: FredCallable
    polymarket: PolymarketCallable
    kalshi: KalshiCallable
    congress: CongressCallable
    tiingo_news: TiingoNewsCallable


def default_fetcher() -> SourceFetcher:
    async def fetch_fred(
        client: httpx.AsyncClient, series_id: str
    ) -> tuple[FredSeriesObservations, str]:
        return await fetch_series_observations(client=client, series_id=series_id)

    async def fetch_pm(
        client: httpx.AsyncClient, limit: int
    ) -> tuple[list[PolymarketEvent], str]:
        return await fetch_polymarket_events(
            client=client, limit=limit, active=True, closed=False
        )

    async def fetch_kx(
        client: httpx.AsyncClient, limit: int
    ) -> tuple[list[KalshiMarket], str]:
        response, content_hash = await fetch_kalshi_markets(client=client, limit=limit)
        return list(response.markets), content_hash

    async def fetch_cg(
        client: httpx.AsyncClient, limit: int
    ) -> tuple[list[CongressBill], str]:
        response, content_hash = await fetch_congress_bills(client=client, limit=limit)
        return list(response.bills), content_hash

    async def fetch_news(
        client: httpx.AsyncClient, limit: int
    ) -> tuple[list[TiingoNewsItem], str]:
        return await fetch_tiingo_news(client=client, limit=limit)

    return SourceFetcher(
        fred=fetch_fred,
        polymarket=fetch_pm,
        kalshi=fetch_kx,
        congress=fetch_cg,
        tiingo_news=fetch_news,
    )


async def _await_or_call(fn: Callable[..., Any], *args: Any) -> Any:
    result = fn(*args)
    if inspect.isawaitable(result):
        return await result
    return result


async def _materialize_chunks(
    session: AsyncSession, evidence: list[IngestedEvidence]
) -> list[EvidenceChunkRef]:
    if not evidence:
        return []
    evidence_ids = [item.evidence_id for item in evidence]
    rows = (
        await session.execute(
            select(EvidenceChunk)
            .where(EvidenceChunk.evidence_id.in_(evidence_ids))
            .order_by(EvidenceChunk.evidence_id, EvidenceChunk.chunk_index)
        )
    ).scalars().all()
    return [
        EvidenceChunkRef(
            chunk_id=row.id,
            evidence_id=row.evidence_id,
            chunk_index=row.chunk_index,
            text=row.text,
            attributes=row.attributes or {},
        )
        for row in rows
    ]


async def _ingest_fred(
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    fetcher: SourceFetcher,
    run_id: uuid.UUID,
) -> tuple[list[FredSeriesObservations], list[IngestedEvidence]]:
    payloads: list[FredSeriesObservations] = []
    evidence: list[IngestedEvidence] = []
    for series_id in FRED_SERIES:
        try:
            payload, content_hash = await _await_or_call(
                fetcher.fred, http_client, series_id
            )
        except Exception as exc:
            emit_run_event(
                session,
                run_id=run_id,
                level=RunEventLevel.warn,
                message=f"fred {series_id} fetch failed: {exc}",
                data={
                    "event": "source_fetch_failure",
                    "source": "fred",
                    "series_id": series_id,
                },
            )
            await session.commit()
            continue
        payloads.append(payload)
        ingested = await ingest_fred_series_observations(
            session=session,
            payload=payload,
            content_hash=content_hash,
            raw_url=None,
        )
        evidence.append(ingested)
    return payloads, evidence


@dataclass(frozen=True)
class _FetchOutcome:
    source_name: str
    payload: Any
    content_hash: str | None
    error: str | None


async def _safe_fetch(
    source_name: str,
    fetch_fn: Callable[..., Any],
    *args: Any,
) -> _FetchOutcome:
    try:
        payload, content_hash = await _await_or_call(fetch_fn, *args)
    except Exception as exc:
        return _FetchOutcome(
            source_name=source_name, payload=None, content_hash=None, error=str(exc)
        )
    return _FetchOutcome(
        source_name=source_name,
        payload=payload,
        content_hash=content_hash,
        error=None,
    )


async def run_ingest(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    fetcher: SourceFetcher,
) -> IngestStageResult:
    pm_outcome, kx_outcome, cg_outcome, news_outcome = await asyncio.gather(
        _safe_fetch(
            "polymarket_events",
            fetcher.polymarket,
            http_client,
            POLYMARKET_FETCH_LIMIT,
        ),
        _safe_fetch(
            "kalshi_markets",
            fetcher.kalshi,
            http_client,
            KALSHI_FETCH_LIMIT,
        ),
        _safe_fetch(
            "congress_bills",
            fetcher.congress,
            http_client,
            CONGRESS_BILLS_FETCH_LIMIT,
        ),
        _safe_fetch(
            "tiingo_news",
            fetcher.tiingo_news,
            http_client,
            TIINGO_NEWS_FETCH_LIMIT,
        ),
    )

    parallel_outcomes = (pm_outcome, kx_outcome, cg_outcome, news_outcome)
    for outcome in parallel_outcomes:
        if outcome.error is not None:
            emit_run_event(
                session,
                run_id=run_id,
                level=RunEventLevel.warn,
                message=f"{outcome.source_name} fetch failed: {outcome.error}",
                data={
                    "event": "source_fetch_failure",
                    "source": outcome.source_name,
                },
            )
    if any(outcome.error is not None for outcome in parallel_outcomes):
        await session.commit()

    fred_payloads, fred_evidence = await _ingest_fred(
        session, http_client, fetcher, run_id
    )

    polymarket_events: list[PolymarketEvent] = []
    kalshi_markets: list[KalshiMarket] = []
    congress_bills: list[CongressBill] = []
    tiingo_news: list[TiingoNewsItem] = []
    evidence: list[IngestedEvidence] = list(fred_evidence)

    if pm_outcome.error is None and pm_outcome.payload is not None:
        events = pm_outcome.payload
        polymarket_events = events
        if events:
            evidence.append(
                await ingest_polymarket_events(
                    session=session,
                    events=events,
                    content_hash=pm_outcome.content_hash or "",
                    raw_url=None,
                )
            )
    if kx_outcome.error is None and kx_outcome.payload is not None:
        markets = kx_outcome.payload
        kalshi_markets = markets
        if markets:
            evidence.append(
                await ingest_kalshi_markets(
                    session=session,
                    markets=markets,
                    content_hash=kx_outcome.content_hash or "",
                    raw_url=None,
                )
            )
    if cg_outcome.error is None and cg_outcome.payload is not None:
        bills = cg_outcome.payload
        congress_bills = bills
        if bills:
            evidence.append(
                await ingest_congress_bills(
                    session=session,
                    bills=bills,
                    content_hash=cg_outcome.content_hash or "",
                    raw_url=None,
                )
            )
    if news_outcome.error is None and news_outcome.payload is not None:
        items = news_outcome.payload
        tiingo_news = items
        if items:
            evidence.append(
                await ingest_tiingo_news_items(
                    session=session,
                    items=items,
                    content_hash=news_outcome.content_hash or "",
                    raw_url=None,
                )
            )

    if not evidence:
        raise FunnelResearchError("no sources returned data")

    chunks = await _materialize_chunks(session, evidence)

    return IngestStageResult(
        evidence=evidence,
        chunks=chunks,
        payloads=SourcePayloads(
            fred=fred_payloads,
            polymarket_events=polymarket_events,
            kalshi_markets=kalshi_markets,
            congress_bills=congress_bills,
            tiingo_news=tiingo_news,
        ),
    )


__all__ = [
    "IngestStageResult",
    "SourceFetcher",
    "default_fetcher",
    "run_ingest",
]
