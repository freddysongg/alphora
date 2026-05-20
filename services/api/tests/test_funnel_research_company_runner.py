import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_company import CompanyThesis as CompanyThesisRow
from app.db.models_graph import Entity, EntityType, Evidence
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
from app.services.source_clients.polygon import (
    PolygonAggregateBar,
    PolygonAggregatesResponse,
)
from app.services.source_clients.sec_edgar import SecSubmissionsResponse
from app.services.source_clients.tiingo_news import TiingoNewsItem
from app.services.strategies.funnel_research.company.evidence import (
    CompanySourceFetcher,
)
from app.services.strategies.funnel_research.company.runner import (
    CompanyResolution,
    run_company_fanout,
)
from app.services.strategies.funnel_research.congress_trading import (
    CongressTradesResult,
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
        chunks=[],
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

    async def fetch_congress(*_: Any) -> CongressTradesResult:
        return CongressTradesResult(
            trades=[], source="ainvest_congress", content_hash="0" * 64
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
        congress_trades=fetch_congress,
        sec_submissions=fetch_sec,
    )


class _UnusedLlm:
    async def complete(self, **kwargs: Any) -> LlmCompletionResult:
        raise AssertionError("llm should not be invoked when no companies persist")


@pytest.mark.asyncio
async def test_run_company_fanout_short_circuits_when_company_thesis_already_persisted(
    initialized_schema: None,
) -> None:
    """A resumed funnel run with a company_thesis row already persisted must
    skip evidence fetch, extraction, synthesis, and judge for that company.
    """
    from app.schemas.company_thesis import (
        CompanyCatalyst,
        CompanyRisk,
        CompanyThesis,
    )
    from app.services.strategies.funnel_research.company.runner import (
        CompanyResolution,
    )

    sector_entity_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    async with session_factory() as session:
        run_id = await _seed_run(session)
        session.add_all(
            [
                Entity(
                    id=sector_entity_id,
                    type=EntityType.sector.value,
                    canonical_name="Information Technology",
                    aliases=[],
                    external_ids={},
                    attributes={},
                ),
                Entity(
                    id=company_entity_id,
                    type=EntityType.company.value,
                    canonical_name="Apple Inc.",
                    aliases=[],
                    external_ids={},
                    attributes={},
                ),
            ]
        )
        await session.flush()

        prior_thesis = CompanyThesis(
            company_entity_id=company_entity_id,
            company_name="Apple Inc.",
            sector_entity_id=sector_entity_id,
            sector_name="Information Technology",
            ticker="AAPL",
            direction=SectorCallDirection.overweight,
            conviction=0.85,
            bull_case="Strong fundamentals.",
            bear_case="Demand risks.",
            catalysts=[
                CompanyCatalyst(
                    name="earnings",
                    expected_timing=None,
                    evidence_ids=[uuid.uuid4()],
                )
            ],
            risks=[
                CompanyRisk(
                    name="competition",
                    severity=0.3,
                    evidence_ids=[uuid.uuid4()],
                )
            ],
            cited_claims=[],
            confidence=0.85,
            evidence_ids=[uuid.uuid4()],
            verifier_status=VerifierStatus.verified,
            regeneration_count=0,
        )
        session.add(
            CompanyThesisRow(
                run_id=run_id,
                company_entity_id=company_entity_id,
                sector_entity_id=sector_entity_id,
                ticker="AAPL",
                direction="overweight",
                payload=prior_thesis.model_dump(mode="json"),
                verifier_status="verified",
                regeneration_count=0,
                judge_status="passed",
                judge_reasons=None,
                judge_call_id=None,
                wall_clock_ms=200,
            )
        )
        await session.commit()

    sector_briefs = [
        _sector_brief_public(
            sector_entity_id=sector_entity_id,
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
    resolutions = {
        "ticker:AAPL": CompanyResolution(
            company_entity_id=company_entity_id, cik="0000320193"
        )
    }

    orchestrator = AsyncMock()

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
        )

    assert outcome.selected_count == 1
    assert outcome.persisted_count == 1
    assert outcome.skipped_count == 0
    assert outcome.failed_count == 0

    async with session_factory() as session:
        company_rows = (
            await session.execute(
                select(CompanyThesisRow).where(CompanyThesisRow.run_id == run_id)
            )
        ).scalars().all()
        events = (
            await session.execute(
                select(RunEvent).where(RunEvent.run_id == run_id)
            )
        ).scalars().all()

    assert len(company_rows) == 1
    assert any(
        isinstance(event.data, dict)
        and event.data.get("event") == "company_resumed"
        and event.data.get("company") == "Apple Inc."
        for event in events
    )


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


def _populated_company_fetcher() -> CompanySourceFetcher:
    aggs_payload = PolygonAggregatesResponse(
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
    aggs_body = json.dumps(
        aggs_payload.model_dump(mode="json"), sort_keys=True
    ).encode("utf-8")
    aggs_hash = hashlib.sha256(aggs_body).hexdigest()

    news_items = [
        TiingoNewsItem(
            id=1,
            title="apple headline",
            description="...",
            url="https://example.com/aapl",
            publishedDate=datetime(2026, 5, 18, tzinfo=UTC),
            source="news.example.com",
            tickers=["AAPL"],
            tags=["tech"],
        ),
    ]
    news_body = json.dumps(
        [item.model_dump(mode="json") for item in news_items], sort_keys=True
    ).encode("utf-8")
    news_hash = hashlib.sha256(news_body).hexdigest()

    async def fetch_aggs(*_: Any) -> tuple[PolygonAggregatesResponse, str]:
        return aggs_payload, aggs_hash

    async def fetch_news(*_: Any) -> tuple[list[TiingoNewsItem], str]:
        return news_items, news_hash

    async def fetch_congress(*_: Any) -> CongressTradesResult:
        return CongressTradesResult(
            trades=[], source="ainvest_congress", content_hash="0" * 64
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
        polygon_aggregates=fetch_aggs,
        tiingo_news=fetch_news,
        congress_trades=fetch_congress,
        sec_submissions=fetch_sec,
    )


class _AssertionLlm:
    async def complete(self, **kwargs: Any) -> LlmCompletionResult:
        raise AssertionError("llm call not relevant for this test")


@pytest.mark.asyncio
async def test_run_company_fanout_ingests_polygon_evidence_when_unpersisted(
    initialized_schema: None,
) -> None:
    """Regression: the persisted check leaves the session in an implicit
    transaction; without releasing it, polygon ingest's `session.begin()` raises
    and the aggregate is silently dropped.
    """
    sector_entity_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
    async with session_factory() as session:
        run_id = await _seed_run(session)
        session.add_all(
            [
                Entity(
                    id=sector_entity_id,
                    type=EntityType.sector.value,
                    canonical_name="Information Technology",
                    aliases=[],
                    external_ids={},
                    attributes={},
                ),
                Entity(
                    id=company_entity_id,
                    type=EntityType.company.value,
                    canonical_name="Apple Inc.",
                    aliases=[],
                    external_ids={},
                    attributes={},
                ),
            ]
        )
        await session.commit()

    sector_briefs = [
        _sector_brief_public(
            sector_entity_id=sector_entity_id,
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
    resolutions = {
        "ticker:AAPL": CompanyResolution(
            company_entity_id=company_entity_id, cik="0000320193"
        )
    }

    orchestrator = AsyncMock()

    async with httpx.AsyncClient() as http_client:
        await run_company_fanout(
            session_factory=session_factory,
            run_id=run_id,
            sector_briefs=sector_briefs,
            digest_markdown="",
            company_resolutions=resolutions,
            llm_client=_AssertionLlm(),
            orchestrator=orchestrator,
            http_client=http_client,
            company_fetcher=_populated_company_fetcher(),
        )

    async with session_factory() as session:
        polygon_rows = (
            await session.execute(
                select(Evidence).where(Evidence.source == "polygon_aggregates")
            )
        ).scalars().all()
    assert len(polygon_rows) == 1
