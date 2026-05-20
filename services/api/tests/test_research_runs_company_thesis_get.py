import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_company import CompanyThesis as CompanyThesisRow
from app.db.models_graph import Entity, EntityType
from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.schemas.company_thesis import (
    CompanyCatalyst,
    CompanyRisk,
    CompanyThesis,
)
from app.schemas.macro_brief import SectorCallDirection, VerifierStatus
from app.schemas.sector_brief import JudgeStatus


@pytest.fixture()
async def async_client(initialized_schema: None, fake_queue) -> AsyncClient:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _thesis(
    *, company_entity_id: uuid.UUID, sector_entity_id: uuid.UUID
) -> CompanyThesis:
    return CompanyThesis(
        company_entity_id=company_entity_id,
        company_name="Apple Inc.",
        sector_entity_id=sector_entity_id,
        sector_name="Information Technology",
        ticker="AAPL",
        direction=SectorCallDirection.overweight,
        conviction=0.8,
        bull_case="Services growth accelerates.",
        bear_case="iPhone demand decelerates.",
        catalysts=[
            CompanyCatalyst(
                name="WWDC 2026",
                expected_timing="Q3 2026",
                evidence_ids=[uuid.uuid4()],
            )
        ],
        risks=[
            CompanyRisk(
                name="Regulatory pressure in EU",
                severity=0.6,
                evidence_ids=[uuid.uuid4()],
            )
        ],
        cited_claims=[],
        confidence=0.7,
        evidence_ids=[uuid.uuid4()],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


async def _seed_funnel_run_with_company_thesis(
    session: AsyncSession, judge_status: JudgeStatus = JudgeStatus.passed
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID | None]:
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

    sector_entity_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()
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

    thesis_row = CompanyThesisRow(
        run_id=run.id,
        company_entity_id=company_entity_id,
        sector_entity_id=sector_entity_id,
        ticker="AAPL",
        direction=SectorCallDirection.overweight.value,
        payload=_thesis(
            company_entity_id=company_entity_id,
            sector_entity_id=sector_entity_id,
        ).model_dump(mode="json"),
        verifier_status="verified",
        regeneration_count=0,
        judge_status=judge_status.value,
        judge_reasons=None,
        judge_call_id=judge_call_id,
        wall_clock_ms=42,
    )
    session.add(thesis_row)
    await session.commit()
    return run.id, company_entity_id, judge_call_id


@pytest.mark.asyncio
async def test_get_company_thesis_returns_thesis_and_judge(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run_id, company_entity_id, judge_call_id = (
        await _seed_funnel_run_with_company_thesis(db_session)
    )

    response = await async_client.get(
        f"/api/research-runs/{run_id}/companies/{company_entity_id}"
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["thesis"]["company_entity_id"] == str(company_entity_id)
    assert body["thesis"]["company_name"] == "Apple Inc."
    assert body["thesis"]["ticker"] == "AAPL"
    assert body["thesis"]["direction"] == "overweight"
    assert body["thesis"]["bull_case"] == "Services growth accelerates."
    assert body["thesis"]["bear_case"] == "iPhone demand decelerates."
    assert body["thesis"]["catalysts"][0]["name"] == "WWDC 2026"
    assert body["thesis"]["risks"][0]["name"] == "Regulatory pressure in EU"
    assert body["judge"]["status"] == "passed"
    assert body["judge"]["call_id"] == str(judge_call_id)


@pytest.mark.asyncio
async def test_get_company_thesis_returns_404_for_unknown_run(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(
        f"/api/research-runs/{uuid.uuid4()}/companies/{uuid.uuid4()}"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_company_thesis_returns_404_for_non_funnel_strategy(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker="AAPL",
        trade_date=date(2026, 5, 18),
        strategy=Strategy.tradingagents.value,
        status=RunStatus.succeeded,
        config={},
        scope_payload=None,
    )
    db_session.add(run)
    await db_session.commit()
    response = await async_client.get(
        f"/api/research-runs/{run.id}/companies/{uuid.uuid4()}"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_company_thesis_returns_404_when_thesis_missing(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.succeeded,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    db_session.add(run)
    await db_session.commit()
    response = await async_client.get(
        f"/api/research-runs/{run.id}/companies/{uuid.uuid4()}"
    )
    assert response.status_code == 404
