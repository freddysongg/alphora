import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Evidence
from app.db.models_runs import (
    ResearchRun,
    RunEvent,
    RunEventLevel,
    RunStatus,
    Strategy,
)
from app.schemas.macro_brief import SectorCall, SectorCallDirection
from app.services.source_clients.polygon import (
    PolygonAggregateBar,
    PolygonAggregatesResponse,
)
from app.services.source_clients.tiingo_news import TiingoNewsItem
from app.services.strategies.funnel_research.sector.evidence import (
    SectorSourceFetcher,
    fetch_sector_evidence,
)
from app.services.strategies.funnel_research.sector_constituents import (
    SectorConstituents,
)


def _sector_call() -> SectorCall:
    return SectorCall(
        sector_entity_id=uuid.uuid4(),
        sector_name="Information Technology",
        direction=SectorCallDirection.overweight,
        conviction=0.8,
        evidence_ids=[],
    )


def _constituents() -> SectorConstituents:
    return SectorConstituents(
        proxy_ticker="XLK",
        representative_tickers=("AAPL", "MSFT"),
    )


def _aggs_payload() -> PolygonAggregatesResponse:
    return PolygonAggregatesResponse(
        ticker="XLK",
        queryCount=1,
        resultsCount=1,
        adjusted=True,
        status="OK",
        results=[
            PolygonAggregateBar(o=100.0, c=101.0, h=102.0, l=99.5, v=1000.0, t=1715040000000),
        ],
    )


def _news_items() -> list[TiingoNewsItem]:
    return [
        TiingoNewsItem(
            id=1,
            title="Big tech earnings",
            description="...",
            url="https://example.com/1",
            publishedDate=datetime(2026, 5, 18, tzinfo=UTC),
            source="news.example.com",
            tickers=["AAPL"],
            tags=["tech"],
        ),
    ]


async def _seed_run(session: AsyncSession) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 19),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.commit()
    return run.id


def _fake_fetcher(*, aggs_ok: bool = True, news_ok: bool = True) -> SectorSourceFetcher:
    async def fetch_aggs(*_: Any) -> tuple[PolygonAggregatesResponse, str]:
        if not aggs_ok:
            raise RuntimeError("polygon down")
        payload = _aggs_payload()
        body = json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode("utf-8")
        return payload, hashlib.sha256(body).hexdigest()

    async def fetch_news(*_: Any) -> tuple[list[TiingoNewsItem], str]:
        if not news_ok:
            raise RuntimeError("tiingo down")
        items = _news_items()
        body = json.dumps([i.model_dump(mode="json") for i in items], sort_keys=True).encode(
            "utf-8"
        )
        return items, hashlib.sha256(body).hexdigest()

    return SectorSourceFetcher(polygon_aggregates=fetch_aggs, tiingo_news=fetch_news)


@pytest.mark.asyncio
async def test_fetch_sector_evidence_ingests_both_sources(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    async with httpx.AsyncClient() as http_client:
        result = await fetch_sector_evidence(
            session=db_session,
            run_id=run_id,
            sector_call=_sector_call(),
            constituents=_constituents(),
            http_client=http_client,
            fetcher=_fake_fetcher(),
        )

    assert len(result.evidence) == 2
    assert {entry.source for entry in result.evidence} == {
        "polygon_aggregates",
        "tiingo_news",
    }
    assert len(result.chunks) >= 2
    evidence_rows = (await db_session.execute(select(Evidence))).scalars().all()
    assert len(evidence_rows) == 2


@pytest.mark.asyncio
async def test_fetch_sector_evidence_isolates_polygon_failure(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    async with httpx.AsyncClient() as http_client:
        result = await fetch_sector_evidence(
            session=db_session,
            run_id=run_id,
            sector_call=_sector_call(),
            constituents=_constituents(),
            http_client=http_client,
            fetcher=_fake_fetcher(aggs_ok=False),
        )

    assert len(result.evidence) == 1
    assert result.evidence[0].source == "tiingo_news"
    events = (
        await db_session.execute(
            select(RunEvent).where(RunEvent.level == RunEventLevel.warn)
        )
    ).scalars().all()
    assert any(
        isinstance(event.data, dict)
        and event.data.get("source") == "polygon_aggregates"
        for event in events
    )


@pytest.mark.asyncio
async def test_fetch_sector_evidence_all_failures_yields_empty(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    async with httpx.AsyncClient() as http_client:
        result = await fetch_sector_evidence(
            session=db_session,
            run_id=run_id,
            sector_call=_sector_call(),
            constituents=_constituents(),
            http_client=http_client,
            fetcher=_fake_fetcher(aggs_ok=False, news_ok=False),
        )

    assert result.evidence == []
    assert result.chunks == []
    warn_events = (
        await db_session.execute(
            select(RunEvent).where(RunEvent.level == RunEventLevel.warn)
        )
    ).scalars().all()
    assert len(warn_events) == 2
