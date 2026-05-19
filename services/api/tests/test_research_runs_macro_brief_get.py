import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType, Evidence, EvidenceChunk
from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.db.models_sector import SectorBrief as SectorBriefRow


@pytest.fixture()
async def async_client(initialized_schema: None, fake_queue) -> AsyncClient:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _seed_funnel_run_with_brief(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
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

    evidence = Evidence(
        source="fred",
        document_id="GDP",
        raw_url=None,
        content_hash="a" * 64,
        structured=None,
    )
    session.add(evidence)
    await session.flush()

    chunk = EvidenceChunk(
        evidence_id=evidence.id,
        chunk_index=0,
        text="FRED series GDP observation date=2026-01-01 value=27.0",
        start_offset=None,
        end_offset=None,
        attributes={"series_id": "GDP"},
        content_hash="b" * 64,
    )
    session.add(chunk)
    await session.flush()

    brief = MacroBriefRow(
        run_id=run.id,
        themes=[],
        sector_calls=[],
        watch_items=[],
        cited_claims=[
            {
                "claim_text": "GDP printed",
                "exact_quote": "value=27.0",
                "chunk_id": str(chunk.id),
                "source": "fred",
            }
        ],
        proposed_hypotheses=[],
        confidence=0.5,
        verifier_status="verified",
        regeneration_count=0,
        evidence_ids=[str(evidence.id)],
    )
    session.add(brief)
    await session.commit()
    return run.id, chunk.id


@pytest.mark.asyncio
async def test_get_macro_brief_returns_brief_and_chunks(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run_id, chunk_id = await _seed_funnel_run_with_brief(db_session)
    response = await async_client.get(f"/api/research-runs/{run_id}/macro-brief")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["brief"]["verifier_status"] == "verified"
    assert len(body["chunks"]) == 1
    assert body["chunks"][0]["chunk_id"] == str(chunk_id)
    assert body["chunks"][0]["source"] == "fred"


@pytest.mark.asyncio
async def test_get_macro_brief_404_for_unknown_run(async_client: AsyncClient) -> None:
    response = await async_client.get(f"/api/research-runs/{uuid.uuid4()}/macro-brief")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_macro_brief_404_for_tradingagents_run(
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

    response = await async_client.get(f"/api/research-runs/{run.id}/macro-brief")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_macro_brief_404_when_brief_not_yet_persisted(
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

    response = await async_client.get(f"/api/research-runs/{run.id}/macro-brief")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_macro_brief_returns_sector_briefs_and_merged_chunks(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run_id, macro_chunk_id = await _seed_funnel_run_with_brief(db_session)

    sector_entity = Entity(
        type=EntityType.sector.value,
        canonical_name="Energy",
        attributes={"gics_code": "10", "gics_level": 1, "parent_gics_code": None},
    )
    db_session.add(sector_entity)
    await db_session.flush()

    sector_evidence = Evidence(
        source="tiingo_news",
        document_id="news-1",
        raw_url=None,
        content_hash="c" * 64,
        structured=None,
    )
    db_session.add(sector_evidence)
    await db_session.flush()

    sector_chunk = EvidenceChunk(
        evidence_id=sector_evidence.id,
        chunk_index=0,
        text="OPEC announced unexpected production cuts overnight",
        start_offset=None,
        end_offset=None,
        attributes={"source": "tiingo_news"},
        content_hash="d" * 64,
    )
    db_session.add(sector_chunk)
    await db_session.flush()

    judge_log = LlmCallLog(
        id=uuid.uuid4(),
        run_id=run_id,
        model="gpt-5-mini",
        prompt_hash="0" * 64,
        input_hash="0" * 64,
        latency_ms=10,
        status=LlmCallStatus.success,
        cost_usd=Decimal("0.001"),
    )
    db_session.add(judge_log)
    await db_session.flush()

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
                "evidence_ids": [str(sector_evidence.id)],
            }
        ],
        "watch_items": [],
        "cited_claims": [
            {
                "claim_text": "OPEC cut production",
                "exact_quote": "OPEC announced unexpected production cuts",
                "chunk_id": str(sector_chunk.id),
                "source": "tiingo_news",
            }
        ],
        "confidence": 0.8,
        "verifier_status": "verified",
        "regeneration_count": 0,
    }
    sector_row = SectorBriefRow(
        run_id=run_id,
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
    db_session.add(sector_row)
    await db_session.commit()

    response = await async_client.get(f"/api/research-runs/{run_id}/macro-brief")
    assert response.status_code == 200, response.text
    body = response.json()

    assert len(body["sector_briefs"]) == 1
    sector_public = body["sector_briefs"][0]
    assert sector_public["brief"]["sector_name"] == "Energy"
    assert sector_public["brief"]["companies"][0]["ticker"] == "XOM"
    assert sector_public["judge"]["status"] == "passed"
    assert sector_public["judge"]["call_id"] == str(judge_log.id)

    chunk_ids = {chunk["chunk_id"] for chunk in body["chunks"]}
    assert str(macro_chunk_id) in chunk_ids
    assert str(sector_chunk.id) in chunk_ids
