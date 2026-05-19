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
from app.schemas.macro_brief import SectorCallDirection
from app.services.source_clients.ainvest import (
    AinvestCongressData,
    AinvestCongressResponse,
    AinvestCongressTransaction,
)
from app.services.source_clients.polygon import (
    PolygonAggregateBar,
    PolygonAggregatesResponse,
)
from app.services.source_clients.sec_edgar import (
    SecRecentSubmission,
    SecSubmissionsResponse,
)
from app.services.source_clients.tiingo_news import TiingoNewsItem
from app.services.strategies.funnel_research.company.evidence import (
    CompanySourceFetcher,
    fetch_company_evidence,
)
from app.services.strategies.funnel_research.company.selector import CompanyIdea


def _company_idea(ticker: str | None = "AAPL") -> CompanyIdea:
    return CompanyIdea(
        company_name="Apple Inc.",
        ticker=ticker,
        direction=SectorCallDirection.overweight,
        conviction=0.75,
        sector_entity_id=uuid.uuid4(),
        sector_name="Information Technology",
        evidence_ids=(),
        sector_company_index=0,
    )


def _polygon_payload() -> PolygonAggregatesResponse:
    return PolygonAggregatesResponse(
        ticker="AAPL",
        queryCount=1,
        resultsCount=1,
        adjusted=True,
        status="OK",
        results=[
            PolygonAggregateBar(
                o=190.0, c=192.0, h=193.0, l=189.0, v=10_000_000.0, t=1715040000000
            ),
        ],
    )


def _tiingo_news_items() -> list[TiingoNewsItem]:
    return [
        TiingoNewsItem(
            id=42,
            title="Apple earnings beat",
            description="Apple posted strong quarterly results.",
            url="https://example.com/apple",
            publishedDate=datetime(2026, 5, 18, tzinfo=UTC),
            source="news.example.com",
            tickers=["AAPL"],
            tags=["earnings"],
        ),
    ]


def _ainvest_payload() -> AinvestCongressResponse:
    return AinvestCongressResponse(
        data=AinvestCongressData(
            data=[
                AinvestCongressTransaction(
                    name="Jane Doe",
                    party="D",
                    state="CA",
                    trade_date=date(2026, 4, 1),
                    filing_date=date(2026, 4, 15),
                    reporting_gap="14 days",
                    trade_type="purchase",
                    size="$1,001 - $15,000",
                ),
            ]
        ),
        status_code=200,
        status_msg="ok",
    )


def _sec_payload() -> SecSubmissionsResponse:
    return SecSubmissionsResponse(
        cik="0000320193",
        name="Apple Inc.",
        sic="3571",
        tickers=["AAPL"],
        recent=[
            SecRecentSubmission(
                accession_number="0000320193-26-000001",
                filing_date=date(2026, 2, 1),
                report_date=date(2025, 12, 31),
                form="10-K",
                primary_document="aapl-20251231.htm",
                primary_doc_description="Annual report",
            ),
        ],
    )


def _hash(payload: object) -> str:
    body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


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


def _fake_fetcher(
    *,
    polygon_ok: bool = True,
    tiingo_ok: bool = True,
    ainvest_ok: bool = True,
    sec_ok: bool = True,
) -> CompanySourceFetcher:
    async def fetch_polygon(*_: Any) -> tuple[PolygonAggregatesResponse, str]:
        if not polygon_ok:
            raise RuntimeError("polygon down")
        payload = _polygon_payload()
        return payload, _hash(payload.model_dump(mode="json"))

    async def fetch_tiingo(*_: Any) -> tuple[list[TiingoNewsItem], str]:
        if not tiingo_ok:
            raise RuntimeError("tiingo down")
        items = _tiingo_news_items()
        return items, _hash([i.model_dump(mode="json") for i in items])

    async def fetch_ainvest(*_: Any) -> tuple[AinvestCongressResponse, str]:
        if not ainvest_ok:
            raise RuntimeError("ainvest down")
        payload = _ainvest_payload()
        return payload, _hash(payload.model_dump(mode="json"))

    async def fetch_sec(*_: Any) -> tuple[SecSubmissionsResponse, str]:
        if not sec_ok:
            raise RuntimeError("sec down")
        payload = _sec_payload()
        return payload, _hash(payload.model_dump(mode="json"))

    return CompanySourceFetcher(
        polygon_aggregates=fetch_polygon,
        tiingo_news=fetch_tiingo,
        ainvest_congress=fetch_ainvest,
        sec_submissions=fetch_sec,
    )


@pytest.mark.asyncio
async def test_fetch_company_evidence_ingests_all_sources(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    async with httpx.AsyncClient() as http_client:
        result = await fetch_company_evidence(
            session=db_session,
            run_id=run_id,
            company_idea=_company_idea(),
            cik="0000320193",
            http_client=http_client,
            fetcher=_fake_fetcher(),
        )

    assert {entry.source for entry in result.evidence} == {
        "polygon_aggregates",
        "tiingo_news",
        "ainvest_congress",
        "sec_edgar",
    }
    assert len(result.chunks) >= 4
    evidence_rows = (await db_session.execute(select(Evidence))).scalars().all()
    assert len(evidence_rows) == 4


@pytest.mark.asyncio
async def test_fetch_company_evidence_isolates_polygon_failure(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    async with httpx.AsyncClient() as http_client:
        result = await fetch_company_evidence(
            session=db_session,
            run_id=run_id,
            company_idea=_company_idea(),
            cik="0000320193",
            http_client=http_client,
            fetcher=_fake_fetcher(polygon_ok=False),
        )

    sources = {entry.source for entry in result.evidence}
    assert "polygon_aggregates" not in sources
    assert "tiingo_news" in sources
    warn_events = (
        await db_session.execute(
            select(RunEvent).where(RunEvent.level == RunEventLevel.warn)
        )
    ).scalars().all()
    assert any(
        isinstance(event.data, dict)
        and event.data.get("source") == "polygon_aggregates"
        for event in warn_events
    )


@pytest.mark.asyncio
async def test_fetch_company_evidence_isolates_sec_failure(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    async with httpx.AsyncClient() as http_client:
        result = await fetch_company_evidence(
            session=db_session,
            run_id=run_id,
            company_idea=_company_idea(),
            cik="0000320193",
            http_client=http_client,
            fetcher=_fake_fetcher(sec_ok=False),
        )

    sources = {entry.source for entry in result.evidence}
    assert "sec_edgar" not in sources
    warn_events = (
        await db_session.execute(
            select(RunEvent).where(RunEvent.level == RunEventLevel.warn)
        )
    ).scalars().all()
    assert any(
        isinstance(event.data, dict)
        and event.data.get("source") == "sec_edgar"
        for event in warn_events
    )


@pytest.mark.asyncio
async def test_fetch_company_evidence_skips_sources_without_ticker(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    async with httpx.AsyncClient() as http_client:
        result = await fetch_company_evidence(
            session=db_session,
            run_id=run_id,
            company_idea=_company_idea(ticker=None),
            cik="0000320193",
            http_client=http_client,
            fetcher=_fake_fetcher(),
        )

    sources = {entry.source for entry in result.evidence}
    assert sources == {"sec_edgar"}
    warn_events = (
        await db_session.execute(
            select(RunEvent).where(RunEvent.level == RunEventLevel.warn)
        )
    ).scalars().all()
    warn_sources = {
        event.data.get("source")
        for event in warn_events
        if isinstance(event.data, dict)
    }
    assert {"polygon_aggregates", "tiingo_news", "ainvest_congress"}.issubset(
        warn_sources
    )


@pytest.mark.asyncio
async def test_fetch_company_evidence_skips_sec_without_cik(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    async with httpx.AsyncClient() as http_client:
        result = await fetch_company_evidence(
            session=db_session,
            run_id=run_id,
            company_idea=_company_idea(),
            cik=None,
            http_client=http_client,
            fetcher=_fake_fetcher(),
        )

    sources = {entry.source for entry in result.evidence}
    assert "sec_edgar" not in sources
    assert "polygon_aggregates" in sources
    warn_events = (
        await db_session.execute(
            select(RunEvent).where(RunEvent.level == RunEventLevel.warn)
        )
    ).scalars().all()
    assert any(
        isinstance(event.data, dict)
        and event.data.get("source") == "sec_edgar"
        and event.data.get("reason") == "no cik available"
        for event in warn_events
    )


@pytest.mark.asyncio
async def test_fetch_company_evidence_all_failures_yields_empty(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    async with httpx.AsyncClient() as http_client:
        result = await fetch_company_evidence(
            session=db_session,
            run_id=run_id,
            company_idea=_company_idea(),
            cik="0000320193",
            http_client=http_client,
            fetcher=_fake_fetcher(
                polygon_ok=False,
                tiingo_ok=False,
                ainvest_ok=False,
                sec_ok=False,
            ),
        )

    assert result.evidence == []
    assert result.chunks == []
    warn_events = (
        await db_session.execute(
            select(RunEvent).where(RunEvent.level == RunEventLevel.warn)
        )
    ).scalars().all()
    assert len(warn_events) == 4
