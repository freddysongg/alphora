import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_portfolio import PortfolioBrief as PortfolioBriefRow
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.schemas.macro_brief import VerifierStatus
from app.schemas.portfolio_brief import (
    PortfolioBrief,
    PortfolioCoverage,
    PortfolioMacroSummary,
    PortfolioSectorEntry,
)
from app.schemas.sector_brief import JudgeStatus


@pytest.fixture()
async def async_client(initialized_schema: None, fake_queue) -> AsyncClient:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _brief(run_id: uuid.UUID) -> PortfolioBrief:
    return PortfolioBrief(
        run_id=run_id,
        macro=PortfolioMacroSummary(
            themes=[],
            watch_items=[],
            confidence=0.6,
            judge_status=JudgeStatus.passed,
        ),
        sectors=[
            PortfolioSectorEntry(
                sector_entity_id=uuid.uuid4(),
                sector_name="Information Technology",
                direction="overweight",
                conviction=0.8,
                verifier_status=VerifierStatus.verified,
                judge_status=JudgeStatus.passed,
                rank=1,
            )
        ],
        companies=[],
        cited_claims=[],
        cited_chunk_ids=[],
        coverage=PortfolioCoverage(
            sectors_selected=1,
            sectors_verified=1,
            sectors_judge_passed=1,
            sectors_judge_flagged=0,
            companies_selected=0,
            companies_verified=0,
            companies_judge_passed=0,
            companies_judge_flagged=0,
        ),
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


async def _seed_funnel_run_with_portfolio(
    session: AsyncSession, judge_status: JudgeStatus = JudgeStatus.passed
) -> tuple[uuid.UUID, uuid.UUID | None]:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.succeeded,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.flush()

    judge_call_id: uuid.UUID | None = None
    if judge_status is not JudgeStatus.not_run:
        log = LlmCallLog(
            id=uuid.uuid4(),
            run_id=run.id,
            model="gpt-5-mini",
            prompt_hash="0" * 64,
            input_hash="0" * 64,
            latency_ms=10,
            status=LlmCallStatus.success,
            cost_usd=Decimal("0.001"),
        )
        session.add(log)
        await session.flush()
        judge_call_id = log.id

    portfolio = PortfolioBriefRow(
        run_id=run.id,
        payload=_brief(run.id).model_dump(mode="json"),
        verifier_status="verified",
        regeneration_count=0,
        judge_status=judge_status.value,
        judge_reasons=None,
        judge_call_id=judge_call_id,
        wall_clock_ms=42,
    )
    session.add(portfolio)
    await session.commit()
    return run.id, judge_call_id


@pytest.mark.asyncio
async def test_get_portfolio_brief_returns_brief_and_judge(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run_id, judge_call_id = await _seed_funnel_run_with_portfolio(db_session)

    response = await async_client.get(
        f"/api/research-runs/{run_id}/portfolio-brief"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["brief"]["verifier_status"] == "verified"
    assert body["brief"]["sectors"][0]["sector_name"] == "Information Technology"
    assert body["brief"]["sectors"][0]["rank"] == 1
    assert body["brief"]["coverage"]["sectors_selected"] == 1
    assert body["judge"]["status"] == "passed"
    assert body["judge"]["call_id"] == str(judge_call_id)


@pytest.mark.asyncio
async def test_get_portfolio_brief_404_for_unknown_run(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(
        f"/api/research-runs/{uuid.uuid4()}/portfolio-brief"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_portfolio_brief_404_for_tradingagents_run(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker="AAPL",
        trade_date=date(2026, 5, 18),
        strategy=Strategy.tradingagents.value,
        status=RunStatus.succeeded,
        config={},
    )
    db_session.add(run)
    await db_session.commit()

    response = await async_client.get(
        f"/api/research-runs/{run.id}/portfolio-brief"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_portfolio_brief_404_when_not_yet_persisted(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    db_session.add(run)
    await db_session.commit()

    response = await async_client.get(
        f"/api/research-runs/{run.id}/portfolio-brief"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_portfolio_brief_returns_not_run_judge(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run_id, _ = await _seed_funnel_run_with_portfolio(
        db_session, judge_status=JudgeStatus.not_run
    )

    response = await async_client.get(
        f"/api/research-runs/{run_id}/portfolio-brief"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["judge"]["status"] == "not_run"
    assert body["judge"]["call_id"] is None
