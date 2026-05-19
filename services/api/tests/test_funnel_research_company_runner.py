import uuid
from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_runs import ResearchRun, RunEvent, RunStatus, Strategy
from app.db.session import session_factory
from app.schemas.macro_brief import SectorCallDirection, VerifierStatus
from app.schemas.sector_brief import (
    JudgePublic,
    JudgeStatus,
    SectorBrief,
    SectorBriefPublic,
    SectorCompanyIdea,
)
from app.services.llm.client import LlmCompletionResult
from app.services.source_clients.ainvest import AinvestCongressResponse
from app.services.source_clients.polygon import PolygonAggregatesResponse
from app.services.source_clients.sec_edgar import SecSubmissionsResponse
from app.services.source_clients.tiingo_news import TiingoNewsItem
from app.services.strategies.funnel_research.company.evidence import (
    CompanySourceFetcher,
)
from app.services.strategies.funnel_research.company.runner import (
    CompanyResolution,
    run_company_fanout,
)


def _sector_brief_public(
    *,
    sector_entity_id: uuid.UUID,
    sector_name: str,
    companies: list[SectorCompanyIdea],
) -> SectorBriefPublic:
    return SectorBriefPublic(
        brief=SectorBrief(
            sector_entity_id=sector_entity_id,
            sector_name=sector_name,
            direction=SectorCallDirection.overweight,
            themes=[],
            companies=companies,
            watch_items=[],
            cited_claims=[],
            confidence=0.7,
            verifier_status=VerifierStatus.verified,
            regeneration_count=0,
        ),
        judge=JudgePublic(status=JudgeStatus.not_run, reasons=[], call_id=None),
    )


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


def _empty_company_fetcher() -> CompanySourceFetcher:
    async def fetch_polygon(*_: Any) -> tuple[PolygonAggregatesResponse, str]:
        return (
            PolygonAggregatesResponse(
                ticker="AAPL",
                queryCount=0,
                resultsCount=0,
                adjusted=True,
                status="OK",
                results=[],
            ),
            "0" * 64,
        )

    async def fetch_tiingo(*_: Any) -> tuple[list[TiingoNewsItem], str]:
        return ([], "0" * 64)

    async def fetch_ainvest(*_: Any) -> tuple[AinvestCongressResponse, str]:
        from app.services.source_clients.ainvest import AinvestCongressData

        return (
            AinvestCongressResponse(
                data=AinvestCongressData(data=[]),
                status_code=200,
                status_msg="ok",
            ),
            "0" * 64,
        )

    async def fetch_sec(*_: Any) -> tuple[SecSubmissionsResponse, str]:
        return (
            SecSubmissionsResponse(
                cik="0000320193",
                name="Apple Inc.",
                sic=None,
                tickers=["AAPL"],
                recent=[],
            ),
            "0" * 64,
        )

    return CompanySourceFetcher(
        polygon_aggregates=fetch_polygon,
        tiingo_news=fetch_tiingo,
        ainvest_congress=fetch_ainvest,
        sec_submissions=fetch_sec,
    )


class _UnusedLlm:
    async def complete(self, **kwargs: Any) -> LlmCompletionResult:
        raise AssertionError("llm should not be invoked when no companies persist")


@pytest.mark.asyncio
async def test_run_company_fanout_returns_zero_when_no_non_neutral_companies(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)

    sector_briefs = [
        _sector_brief_public(
            sector_entity_id=uuid.uuid4(),
            sector_name="Energy",
            companies=[
                SectorCompanyIdea(
                    name="ExxonMobil",
                    ticker="XOM",
                    direction=SectorCallDirection.neutral,
                    conviction=0.5,
                    evidence_ids=[],
                ),
            ],
        )
    ]

    orchestrator = AsyncMock()

    async with httpx.AsyncClient() as http_client:
        outcome = await run_company_fanout(
            session_factory=session_factory,
            run_id=run_id,
            sector_briefs=sector_briefs,
            digest_markdown="",
            company_resolutions={},
            llm_client=_UnusedLlm(),
            orchestrator=orchestrator,
            http_client=http_client,
        )

    assert outcome.selected_count == 0
    assert outcome.persisted_count == 0
    assert outcome.skipped_count == 0
    assert outcome.failed_count == 0
    orchestrator.pause.assert_not_called()
    orchestrator.fail.assert_not_called()


@pytest.mark.asyncio
async def test_run_company_fanout_skips_company_with_no_resolution(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)

    sector_briefs = [
        _sector_brief_public(
            sector_entity_id=uuid.uuid4(),
            sector_name="Information Technology",
            companies=[
                SectorCompanyIdea(
                    name="Apple Inc.",
                    ticker="AAPL",
                    direction=SectorCallDirection.overweight,
                    conviction=0.85,
                    evidence_ids=[],
                ),
            ],
        )
    ]

    orchestrator = AsyncMock()

    async with httpx.AsyncClient() as http_client:
        outcome = await run_company_fanout(
            session_factory=session_factory,
            run_id=run_id,
            sector_briefs=sector_briefs,
            digest_markdown="",
            company_resolutions={},
            llm_client=_UnusedLlm(),
            orchestrator=orchestrator,
            http_client=http_client,
        )

    assert outcome.selected_count == 1
    assert outcome.skipped_count == 1
    assert outcome.persisted_count == 0
    assert outcome.failed_count == 0

    async with session_factory() as session:
        events = (
            await session.execute(
                select(RunEvent).where(RunEvent.run_id == run_id)
            )
        ).scalars().all()
    assert any(
        isinstance(event.data, dict)
        and event.data.get("event") == "company_skipped"
        and event.data.get("reason") == "no resolution available"
        for event in events
    )


@pytest.mark.asyncio
async def test_run_company_fanout_skips_company_with_empty_evidence(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)

    sector_briefs = [
        _sector_brief_public(
            sector_entity_id=uuid.uuid4(),
            sector_name="Information Technology",
            companies=[
                SectorCompanyIdea(
                    name="Apple Inc.",
                    ticker="AAPL",
                    direction=SectorCallDirection.overweight,
                    conviction=0.85,
                    evidence_ids=[],
                ),
            ],
        )
    ]

    orchestrator = AsyncMock()
    resolutions = {
        "ticker:AAPL": CompanyResolution(
            company_entity_id=uuid.uuid4(),
            cik="0000320193",
        )
    }

    async with httpx.AsyncClient() as http_client:
        outcome = await run_company_fanout(
            session_factory=session_factory,
            run_id=run_id,
            sector_briefs=sector_briefs,
            digest_markdown="",
            company_resolutions=resolutions,
            llm_client=_UnusedLlm(),
            orchestrator=orchestrator,
            http_client=http_client,
            company_fetcher=_empty_company_fetcher(),
        )

    assert outcome.selected_count == 1
    assert outcome.skipped_count == 1
    assert outcome.persisted_count == 0
    assert outcome.failed_count == 0


@pytest.mark.asyncio
async def test_run_company_fanout_respects_max_companies_cap(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)

    sector_briefs = [
        _sector_brief_public(
            sector_entity_id=uuid.uuid4(),
            sector_name=name,
            companies=[
                SectorCompanyIdea(
                    name=f"Company {name}",
                    ticker=ticker,
                    direction=SectorCallDirection.overweight,
                    conviction=conv,
                    evidence_ids=[],
                )
            ],
        )
        for name, ticker, conv in [
            ("Energy", "AAA", 0.9),
            ("Materials", "BBB", 0.85),
            ("Information Technology", "CCC", 0.8),
            ("Health Care", "DDD", 0.75),
            ("Financials", "EEE", 0.7),
            ("Utilities", "FFF", 0.65),
        ]
    ]
    orchestrator = AsyncMock()

    async with httpx.AsyncClient() as http_client:
        outcome = await run_company_fanout(
            session_factory=session_factory,
            run_id=run_id,
            sector_briefs=sector_briefs,
            digest_markdown="",
            company_resolutions={},
            llm_client=_UnusedLlm(),
            orchestrator=orchestrator,
            http_client=http_client,
        )

    assert outcome.selected_count == 5
    assert outcome.skipped_count == 5
