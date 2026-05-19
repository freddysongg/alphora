import uuid
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Evidence, EvidenceChunk
from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_runs import ResearchRun, RunStatus, Strategy


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
