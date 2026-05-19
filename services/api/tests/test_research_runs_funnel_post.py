import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_runs import ResearchRun, Strategy


@pytest.fixture()
async def async_client(initialized_schema: None, fake_queue) -> AsyncClient:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_funnel_post_creates_one_run_with_null_ticker(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    payload = {
        "strategy": "funnel_research",
        "trade_date": "2026-05-18",
        "scope_payload": {"kind": "macro", "universe": "us_equities"},
    }
    response = await async_client.post("/api/research-runs", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["ticker"] is None
    assert body[0]["strategy"] == "funnel_research"

    rows = (await db_session.execute(select(ResearchRun))).scalars().all()
    assert len(rows) == 1
    assert rows[0].strategy == Strategy.funnel_research.value
    assert rows[0].ticker is None
    assert rows[0].scope_payload == {"kind": "macro", "universe": "us_equities"}


@pytest.mark.asyncio
async def test_funnel_post_rejects_tickers(async_client: AsyncClient) -> None:
    payload = {
        "strategy": "funnel_research",
        "trade_date": "2026-05-18",
        "tickers": ["AAPL"],
        "scope_payload": {"kind": "macro", "universe": "us_equities"},
    }
    response = await async_client.post("/api/research-runs", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_funnel_post_requires_scope_payload(async_client: AsyncClient) -> None:
    payload = {
        "strategy": "funnel_research",
        "trade_date": "2026-05-18",
    }
    response = await async_client.post("/api/research-runs", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_funnel_post_rejects_wrong_scope_kind(async_client: AsyncClient) -> None:
    payload = {
        "strategy": "funnel_research",
        "trade_date": "2026-05-18",
        "scope_payload": {"kind": "sector", "universe": "us_equities"},
    }
    response = await async_client.post("/api/research-runs", json=payload)
    assert response.status_code == 422
