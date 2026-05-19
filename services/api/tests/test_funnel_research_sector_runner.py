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

from app.db.models_graph import Entity, EntityType, Evidence
from app.db.models_runs import ResearchRun, RunEvent, RunStatus, Strategy
from app.db.models_sector import SectorBrief as SectorBriefRow
from app.db.session import session_factory
from app.schemas.macro_brief import (
    MacroBrief,
    SectorCall,
    SectorCallDirection,
    VerifierStatus,
)
from app.services.llm.client import LlmCompletionResult
from app.services.source_clients.polygon import (
    PolygonAggregateBar,
    PolygonAggregatesResponse,
)
from app.services.source_clients.tiingo_news import TiingoNewsItem
from app.services.strategies.funnel_research.sector.evidence import (
    SectorSourceFetcher,
)
from app.services.strategies.funnel_research.sector.runner import run_sector_fanout
from app.services.strategies.funnel_research.sector_constituents import (
    SectorConstituents,
)


def _macro_brief(sector_calls: list[SectorCall]) -> MacroBrief:
    return MacroBrief(
        themes=[],
        sector_calls=sector_calls,
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.5,
        evidence_ids=[],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
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


def _empty_sector_fetcher() -> SectorSourceFetcher:
    async def fetch_aggs(*_: Any) -> tuple[PolygonAggregatesResponse, str]:
        return (
            PolygonAggregatesResponse(
                ticker="XLE",
                queryCount=0,
                resultsCount=0,
                adjusted=True,
                status="OK",
                results=[],
            ),
            "0" * 64,
        )

    async def fetch_news(*_: Any) -> tuple[list[TiingoNewsItem], str]:
        return ([], "0" * 64)

    return SectorSourceFetcher(polygon_aggregates=fetch_aggs, tiingo_news=fetch_news)


class _UnusedLlm:
    async def complete(self, **kwargs: Any) -> LlmCompletionResult:
        raise AssertionError("llm should not be invoked when no sectors persist")


@pytest.mark.asyncio
async def test_run_sector_fanout_short_circuits_when_sector_brief_already_persisted(
    initialized_schema: None,
) -> None:
    """A resumed funnel run with a sector_brief row already persisted must
    skip evidence fetch, extraction, synthesis, and judge for that sector.
    """
    from app.schemas.sector_brief import (
        JudgePublic,
        JudgeStatus,
        SectorBrief,
    )

    sector_entity_id = uuid.uuid4()
    async with session_factory() as session:
        run_id = await _seed_run(session)
        sector_entity = Entity(
            id=sector_entity_id,
            type=EntityType.sector.value,
            canonical_name="Energy",
            aliases=[],
            external_ids={},
            attributes={},
        )
        session.add(sector_entity)
        await session.flush()

        prior_brief = SectorBrief(
            sector_entity_id=sector_entity_id,
            sector_name="Energy",
            direction=SectorCallDirection.overweight,
            themes=[],
            companies=[],
            watch_items=[],
            cited_claims=[],
            confidence=0.7,
            verifier_status=VerifierStatus.verified,
            regeneration_count=0,
        )
        prior_judge = JudgePublic(
            status=JudgeStatus.passed, reasons=[], call_id=None
        )
        session.add(
            SectorBriefRow(
                run_id=run_id,
                sector_entity_id=sector_entity_id,
                direction="overweight",
                payload=prior_brief.model_dump(mode="json"),
                verifier_status="verified",
                regeneration_count=0,
                judge_status=prior_judge.status.value,
                judge_reasons=None,
                judge_call_id=None,
                wall_clock_ms=100,
            )
        )
        await session.commit()

    macro = _macro_brief(
        sector_calls=[
            SectorCall(
                sector_entity_id=sector_entity_id,
                sector_name="Energy",
                direction=SectorCallDirection.overweight,
                conviction=0.8,
                evidence_ids=[],
            )
        ]
    )

    orchestrator = AsyncMock()
    constituents = {
        "Energy": SectorConstituents(
            proxy_ticker="XLE", representative_tickers=("XOM",)
        )
    }

    async with httpx.AsyncClient() as http_client:
        outcome = await run_sector_fanout(
            session_factory=session_factory,
            run_id=run_id,
            macro_brief=macro,
            digest_markdown="",
            sector_constituents=constituents,
            llm_client=_UnusedLlm(),
            orchestrator=orchestrator,
            http_client=http_client,
            sector_fetcher=_empty_sector_fetcher(),
        )

    assert outcome.selected_count == 1
    assert outcome.persisted_count == 1
    assert outcome.skipped_count == 0
    assert outcome.failed_count == 0

    async with session_factory() as session:
        sector_rows = (
            await session.execute(
                select(SectorBriefRow).where(SectorBriefRow.run_id == run_id)
            )
        ).scalars().all()
        events = (
            await session.execute(
                select(RunEvent).where(RunEvent.run_id == run_id)
            )
        ).scalars().all()

    assert len(sector_rows) == 1
    assert any(
        isinstance(event.data, dict)
        and event.data.get("event") == "sector_resumed"
        and event.data.get("sector") == "Energy"
        for event in events
    )


@pytest.mark.asyncio
async def test_run_sector_fanout_returns_zero_when_no_non_neutral_calls(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)

    macro = _macro_brief(
        sector_calls=[
            SectorCall(
                sector_entity_id=uuid.uuid4(),
                sector_name="Energy",
                direction=SectorCallDirection.neutral,
                conviction=0.5,
                evidence_ids=[],
            )
        ]
    )

    orchestrator = AsyncMock()

    async with httpx.AsyncClient() as http_client:
        outcome = await run_sector_fanout(
            session_factory=session_factory,
            run_id=run_id,
            macro_brief=macro,
            digest_markdown="",
            sector_constituents={},
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
async def test_run_sector_fanout_skips_sector_with_no_constituents(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)

    macro = _macro_brief(
        sector_calls=[
            SectorCall(
                sector_entity_id=uuid.uuid4(),
                sector_name="Energy",
                direction=SectorCallDirection.overweight,
                conviction=0.8,
                evidence_ids=[],
            )
        ]
    )

    orchestrator = AsyncMock()

    async with httpx.AsyncClient() as http_client:
        outcome = await run_sector_fanout(
            session_factory=session_factory,
            run_id=run_id,
            macro_brief=macro,
            digest_markdown="",
            sector_constituents={},
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
        and event.data.get("event") == "sector_skipped"
        and event.data.get("reason") == "no constituents configured"
        for event in events
    )


@pytest.mark.asyncio
async def test_run_sector_fanout_skips_sector_with_empty_evidence(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)

    macro = _macro_brief(
        sector_calls=[
            SectorCall(
                sector_entity_id=uuid.uuid4(),
                sector_name="Energy",
                direction=SectorCallDirection.overweight,
                conviction=0.8,
                evidence_ids=[],
            )
        ]
    )

    orchestrator = AsyncMock()
    constituents = {
        "Energy": SectorConstituents(
            proxy_ticker="XLE", representative_tickers=("XOM",)
        )
    }

    async with httpx.AsyncClient() as http_client:
        outcome = await run_sector_fanout(
            session_factory=session_factory,
            run_id=run_id,
            macro_brief=macro,
            digest_markdown="",
            sector_constituents=constituents,
            llm_client=_UnusedLlm(),
            orchestrator=orchestrator,
            http_client=http_client,
            sector_fetcher=_empty_sector_fetcher(),
        )

    assert outcome.selected_count == 1
    assert outcome.skipped_count == 1
    assert outcome.persisted_count == 0
    assert outcome.failed_count == 0


@pytest.mark.asyncio
async def test_run_sector_fanout_respects_max_sectors_cap(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)

    sectors = [
        SectorCall(
            sector_entity_id=uuid.uuid4(),
            sector_name=name,
            direction=SectorCallDirection.overweight,
            conviction=conv,
            evidence_ids=[],
        )
        for name, conv in [
            ("Energy", 0.9),
            ("Materials", 0.8),
            ("Information Technology", 0.7),
            ("Utilities", 0.6),
        ]
    ]
    macro = _macro_brief(sector_calls=sectors)
    orchestrator = AsyncMock()

    async with httpx.AsyncClient() as http_client:
        outcome = await run_sector_fanout(
            session_factory=session_factory,
            run_id=run_id,
            macro_brief=macro,
            digest_markdown="",
            sector_constituents={},
            llm_client=_UnusedLlm(),
            orchestrator=orchestrator,
            http_client=http_client,
        )

    assert outcome.selected_count == 3
    assert outcome.skipped_count == 3


def _populated_sector_fetcher() -> SectorSourceFetcher:
    aggs_payload = PolygonAggregatesResponse(
        ticker="XLE",
        queryCount=1,
        resultsCount=1,
        adjusted=True,
        status="OK",
        results=[
            PolygonAggregateBar(
                o=100.0, c=101.0, h=102.0, l=99.5, v=1000.0, t=1715040000000
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
            title="energy headline",
            description="...",
            url="https://example.com/1",
            publishedDate=datetime(2026, 5, 18, tzinfo=UTC),
            source="news.example.com",
            tickers=["XOM"],
            tags=["energy"],
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

    return SectorSourceFetcher(polygon_aggregates=fetch_aggs, tiingo_news=fetch_news)


class _AssertionLlm:
    async def complete(self, **kwargs: Any) -> LlmCompletionResult:
        raise AssertionError("llm call not relevant for this test")


@pytest.mark.asyncio
async def test_run_sector_fanout_ingests_polygon_evidence_when_unpersisted(
    initialized_schema: None,
) -> None:
    """Regression: the persisted check leaves the session in an implicit
    transaction; without releasing it, polygon ingest's `session.begin()` raises
    and the aggregate is silently dropped.
    """
    sector_entity_id = uuid.uuid4()
    async with session_factory() as session:
        run_id = await _seed_run(session)
        session.add(
            Entity(
                id=sector_entity_id,
                type=EntityType.sector.value,
                canonical_name="Energy",
                aliases=[],
                external_ids={},
                attributes={},
            )
        )
        await session.commit()

    macro = _macro_brief(
        sector_calls=[
            SectorCall(
                sector_entity_id=sector_entity_id,
                sector_name="Energy",
                direction=SectorCallDirection.overweight,
                conviction=0.8,
                evidence_ids=[],
            )
        ]
    )

    orchestrator = AsyncMock()
    constituents = {
        "Energy": SectorConstituents(
            proxy_ticker="XLE", representative_tickers=("XOM",)
        )
    }

    async with httpx.AsyncClient() as http_client:
        await run_sector_fanout(
            session_factory=session_factory,
            run_id=run_id,
            macro_brief=macro,
            digest_markdown="",
            sector_constituents=constituents,
            llm_client=_AssertionLlm(),
            orchestrator=orchestrator,
            http_client=http_client,
            sector_fetcher=_populated_sector_fetcher(),
        )

    async with session_factory() as session:
        polygon_rows = (
            await session.execute(
                select(Evidence).where(Evidence.source == "polygon_aggregates")
            )
        ).scalars().all()
    assert len(polygon_rows) == 1
