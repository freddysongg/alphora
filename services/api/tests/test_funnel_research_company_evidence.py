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
from app.services.source_clients.finnhub import (
    FinnhubCompanyProfile,
    FinnhubInsiderTransactionsResponse,
    FinnhubPriceTarget,
    FinnhubRecommendation,
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
from app.services.strategies.funnel_research.congress_trading import (
    CongressTrade,
    CongressTradesResult,
)


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


def _congress_trades_result() -> CongressTradesResult:
    return CongressTradesResult(
        trades=[
            CongressTrade(
                ticker="AAPL",
                politician_name="Jane Doe",
                politician_party="D",
                politician_state="CA",
                politician_chamber=None,
                traded_at=date(2026, 4, 1),
                filed_at=date(2026, 4, 15),
                reporting_gap_days=14,
                transaction_type="purchase",
                amount_label="$1,001 - $15,000",
                owner=None,
                source_url=None,
                external_id=None,
            ),
        ],
        source="ainvest_congress",
        content_hash="c" * 64,
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
    congress_ok: bool = True,
    sec_ok: bool = True,
    finnhub_recommendation_ok: bool = True,
    finnhub_price_target_ok: bool = True,
    finnhub_insider_ok: bool = True,
    finnhub_peers_ok: bool = True,
    finnhub_profile_ok: bool = True,
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

    async def fetch_congress(*_: Any) -> CongressTradesResult:
        if not congress_ok:
            raise RuntimeError("congress trades down")
        return _congress_trades_result()

    async def fetch_sec(*_: Any) -> tuple[SecSubmissionsResponse, str]:
        if not sec_ok:
            raise RuntimeError("sec down")
        payload = _sec_payload()
        return payload, _hash(payload.model_dump(mode="json"))

    async def fetch_recommendation(
        *_: Any,
    ) -> tuple[list[FinnhubRecommendation], str]:
        if not finnhub_recommendation_ok:
            raise RuntimeError("finnhub recommendation down")
        return [], "a" * 64

    async def fetch_price_target(*_: Any) -> tuple[FinnhubPriceTarget, str]:
        if not finnhub_price_target_ok:
            raise RuntimeError("finnhub price target down")
        target = FinnhubPriceTarget(
            symbol="AAPL",
            lastUpdated=datetime(2026, 5, 18, tzinfo=UTC),
            targetHigh=0.0,
            targetLow=0.0,
            targetMean=0.0,
            targetMedian=0.0,
            numberOfAnalysts=0,
        )
        return target, "b" * 64

    async def fetch_insider(
        *_: Any,
    ) -> tuple[FinnhubInsiderTransactionsResponse, str]:
        if not finnhub_insider_ok:
            raise RuntimeError("finnhub insider down")
        return (
            FinnhubInsiderTransactionsResponse(symbol="AAPL", data=[]),
            "d" * 64,
        )

    async def fetch_peers(*_: Any) -> tuple[list[str], str]:
        if not finnhub_peers_ok:
            raise RuntimeError("finnhub peers down")
        return [], "e" * 64

    async def fetch_profile(*_: Any) -> tuple[FinnhubCompanyProfile, str]:
        if not finnhub_profile_ok:
            raise RuntimeError("finnhub profile down")
        return FinnhubCompanyProfile(ticker="AAPL"), "f" * 64

    return CompanySourceFetcher(
        polygon_aggregates=fetch_polygon,
        tiingo_news=fetch_tiingo,
        congress_trades=fetch_congress,
        sec_submissions=fetch_sec,
        finnhub_recommendation=fetch_recommendation,
        finnhub_price_target=fetch_price_target,
        finnhub_insider=fetch_insider,
        finnhub_peers=fetch_peers,
        finnhub_profile=fetch_profile,
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
        "finnhub_price_target",
        "finnhub_profile",
    }
    assert len(result.chunks) >= 6
    evidence_rows = (await db_session.execute(select(Evidence))).scalars().all()
    assert len(evidence_rows) == 6


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
    assert {"polygon_aggregates", "tiingo_news", "congress_trades"}.issubset(
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
                congress_ok=False,
                sec_ok=False,
                finnhub_recommendation_ok=False,
                finnhub_price_target_ok=False,
                finnhub_insider_ok=False,
                finnhub_peers_ok=False,
                finnhub_profile_ok=False,
            ),
        )

    assert result.evidence == []
    assert result.chunks == []
    warn_events = (
        await db_session.execute(
            select(RunEvent).where(RunEvent.level == RunEventLevel.warn)
        )
    ).scalars().all()
    assert len(warn_events) == 9
