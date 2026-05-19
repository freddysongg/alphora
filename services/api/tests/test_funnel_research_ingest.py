import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_runs import ResearchRun, RunEvent, RunStatus
from app.services.source_clients.congress_gov import CongressBill
from app.services.source_clients.fred import FredObservation, FredSeriesObservations
from app.services.source_clients.kalshi import KalshiMarket
from app.services.source_clients.polymarket import PolymarketEvent
from app.services.source_clients.tiingo_news import TiingoNewsItem


def _fred() -> tuple[FredSeriesObservations, str]:
    payload = FredSeriesObservations(
        series_id="CPIAUCSL",
        observation_start=date(2025, 1, 1),
        observation_end=date(2026, 1, 1),
        count=1,
        observations=[
            FredObservation(
                date=date(2026, 1, 1),
                value=Decimal("310.0"),
                realtime_start=date(2026, 1, 15),
                realtime_end=date(2026, 12, 31),
            )
        ],
    )
    return payload, "a" * 64


def _polymarket() -> tuple[list[PolymarketEvent], str]:
    return [
        PolymarketEvent(id="e", slug="x", title="X", active=True, closed=False, category=None)
    ], "b" * 64


def _kalshi() -> tuple[list[KalshiMarket], str]:
    return [
        KalshiMarket(
            ticker="K",
            event_ticker="K",
            title="K",
            status="open",
            yes_bid=10,
            yes_ask=20,
            open_time=datetime(2025, 1, 1, tzinfo=UTC),
            close_time=datetime(2025, 12, 31, tzinfo=UTC),
            volume=0,
        )
    ], "c" * 64


def _congress() -> tuple[list[CongressBill], str]:
    return [
        CongressBill(
            congress=119,
            type="HR",
            number="1",
            title="B",
            updateDate=datetime(2026, 1, 2, tzinfo=UTC),
        )
    ], "d" * 64


async def _seed_run(session: AsyncSession) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker="AAPL",
        trade_date=date(2026, 5, 18),
        status=RunStatus.running,
        config={},
    )
    session.add(run)
    await session.commit()
    return run.id


def _news() -> tuple[list[TiingoNewsItem], str]:
    return [
        TiingoNewsItem(
            id=1,
            title="N",
            description=None,
            url="https://x",
            publishedDate=datetime(2026, 5, 18, tzinfo=UTC),
            source="Reuters",
            tickers=[],
            tags=[],
        )
    ], "e" * 64


@pytest.mark.asyncio
async def test_ingest_happy_path_returns_all_payloads_and_chunks(
    db_session: AsyncSession,
) -> None:
    from app.services.strategies.funnel_research._ingest import SourceFetcher, run_ingest

    fetcher = SourceFetcher(
        fred=lambda client, series_id: _fred(),
        polymarket=lambda client, limit: _polymarket(),
        kalshi=lambda client, limit: _kalshi(),
        congress=lambda client, limit: _congress(),
        tiingo_news=lambda client, limit: _news(),
    )
    run_id = await _seed_run(db_session)

    async with httpx.AsyncClient() as http_client:
        result = await run_ingest(
            session=db_session,
            run_id=run_id,
            http_client=http_client,
            fetcher=fetcher,
        )

    from app.services.strategies.funnel_research.config import FRED_SERIES

    assert len(result.evidence) == len(FRED_SERIES) + 4
    assert len(result.chunks) >= 5
    assert result.payloads.fred and result.payloads.tiingo_news


@pytest.mark.asyncio
async def test_ingest_partial_failure_warns_but_continues(
    db_session: AsyncSession,
) -> None:
    from app.services.strategies.funnel_research._ingest import SourceFetcher, run_ingest

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("upstream 502")

    fetcher = SourceFetcher(
        fred=lambda client, series_id: _fred(),
        polymarket=boom,
        kalshi=lambda client, limit: _kalshi(),
        congress=lambda client, limit: _congress(),
        tiingo_news=lambda client, limit: _news(),
    )
    run_id = await _seed_run(db_session)

    async with httpx.AsyncClient() as http_client:
        result = await run_ingest(
            session=db_session,
            run_id=run_id,
            http_client=http_client,
            fetcher=fetcher,
        )

    assert not result.payloads.polymarket_events
    assert result.payloads.fred
    events = (
        await db_session.execute(select(RunEvent).where(RunEvent.run_id == run_id))
    ).scalars().all()
    assert any("polymarket" in (e.message or "").lower() for e in events)


@pytest.mark.asyncio
async def test_ingest_total_failure_raises(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research import FunnelResearchError
    from app.services.strategies.funnel_research._ingest import SourceFetcher, run_ingest

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("network")

    fetcher = SourceFetcher(
        fred=boom,
        polymarket=boom,
        kalshi=boom,
        congress=boom,
        tiingo_news=boom,
    )
    run_id = await _seed_run(db_session)

    async with httpx.AsyncClient() as http_client:
        with pytest.raises(FunnelResearchError):
            await run_ingest(
                session=db_session,
                run_id=run_id,
                http_client=http_client,
                fetcher=fetcher,
            )
