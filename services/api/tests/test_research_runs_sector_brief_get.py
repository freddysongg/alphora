import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType, Evidence, EvidenceChunk
from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.db.models_sector import SectorBrief as SectorBriefRow


@pytest.fixture()
async def async_client(initialized_schema: None, fake_queue) -> AsyncClient:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _seed_funnel_run_with_sector_brief(
    session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 19),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.succeeded,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.flush()

    sector_entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.sector.value,
        canonical_name="Energy",
        aliases=[],
        external_ids={},
        attributes={"gics_code": "10", "gics_level": 1, "parent_gics_code": None},
    )
    session.add(sector_entity)
    await session.flush()

    evidence = Evidence(
        source="tiingo_news",
        document_id="news-1",
        raw_url=None,
        content_hash="c" * 64,
        structured=None,
    )
    session.add(evidence)
    await session.flush()

    chunk = EvidenceChunk(
        evidence_id=evidence.id,
        chunk_index=0,
        text="OPEC announced unexpected production cuts overnight as supply tightened.",
        start_offset=None,
        end_offset=None,
        attributes={"source": "tiingo_news"},
        content_hash="d" * 64,
    )
    session.add(chunk)
    await session.flush()

    judge_log = LlmCallLog(
        id=uuid.uuid4(),
        run_id=run.id,
        model="gpt-5-mini",
        prompt_hash="0" * 64,
        input_hash="0" * 64,
        latency_ms=10,
        status=LlmCallStatus.success,
        cost_usd=Decimal("0.001"),
    )
    session.add(judge_log)
    await session.flush()

    sector_payload = {
        "sector_entity_id": str(sector_entity.id),
        "sector_name": "Energy",
        "direction": "overweight",
        "themes": [],
        "companies": [
            {
                "name": "ExxonMobil",
                "ticker": "XOM",
                "direction": "overweight",
                "conviction": 0.75,
                "evidence_ids": [str(evidence.id)],
            }
        ],
        "watch_items": [],
        "cited_claims": [
            {
                "claim_text": "OPEC cut production.",
                "exact_quote": "OPEC announced unexpected production cuts",
                "chunk_id": str(chunk.id),
                "source": "tiingo_news",
            }
        ],
        "confidence": 0.8,
        "verifier_status": "verified",
        "regeneration_count": 0,
    }
    session.add(
        SectorBriefRow(
            run_id=run.id,
            sector_entity_id=sector_entity.id,
            direction="overweight",
            payload=sector_payload,
            verifier_status="verified",
            regeneration_count=0,
            judge_status="passed",
            judge_reasons=None,
            judge_call_id=judge_log.id,
            wall_clock_ms=1234,
        )
    )
    await session.commit()
    return run.id, sector_entity.id, chunk.id, evidence.id


@pytest.mark.asyncio
async def test_get_sector_brief_returns_brief_judge_and_chunks(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run_id, sector_entity_id, chunk_id, evidence_id = (
        await _seed_funnel_run_with_sector_brief(db_session)
    )

    response = await async_client.get(
        f"/api/research-runs/{run_id}/sectors/{sector_entity_id}"
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["brief"]["sector_name"] == "Energy"
    assert body["brief"]["direction"] == "overweight"
    assert body["brief"]["companies"][0]["ticker"] == "XOM"
    assert body["judge"]["status"] == "passed"

    assert len(body["chunks"]) == 1
    chunk_lookup = body["chunks"][0]
    assert chunk_lookup["chunk_id"] == str(chunk_id)
    assert chunk_lookup["evidence_id"] == str(evidence_id)
    assert chunk_lookup["source"] == "tiingo_news"
    assert "OPEC announced unexpected production cuts" in chunk_lookup["text"]


@pytest.mark.asyncio
async def test_get_sector_brief_returns_404_for_unknown_run(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(
        f"/api/research-runs/{uuid.uuid4()}/sectors/{uuid.uuid4()}"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_sector_brief_returns_404_for_non_funnel_strategy(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker="AAPL",
        trade_date=date(2026, 5, 19),
        strategy=Strategy.tradingagents.value,
        status=RunStatus.succeeded,
        config={},
        scope_payload=None,
    )
    db_session.add(run)
    await db_session.commit()
    response = await async_client.get(
        f"/api/research-runs/{run.id}/sectors/{uuid.uuid4()}"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_sector_brief_returns_404_when_sector_missing(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 19),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.succeeded,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    db_session.add(run)
    await db_session.commit()
    response = await async_client.get(
        f"/api/research-runs/{run.id}/sectors/{uuid.uuid4()}"
    )
    assert response.status_code == 404
