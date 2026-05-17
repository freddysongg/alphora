from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models_runs import ResearchRun, Strategy
from app.db.session import session_factory
from app.main import app


def test_create_research_runs_defaults_strategy_to_tradingagents(
    initialized_schema: None, fake_queue: Any
) -> None:
    _ = initialized_schema
    _ = fake_queue
    payload: dict[str, Any] = {
        "tickers": ["AAPL"],
        "trade_date": "2026-05-15",
        "llm_provider": "openai",
        "llm_model": "gpt-4o-mini",
    }
    with TestClient(app) as client:
        response = client.post("/api/research-runs", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body[0]["strategy"] == Strategy.tradingagents.value

    import asyncio

    async def _load_strategies() -> list[str]:
        async with session_factory() as session:
            rows = (await session.execute(select(ResearchRun))).scalars().all()
            return [row.strategy for row in rows]

    persisted = asyncio.run(_load_strategies())
    assert persisted == [Strategy.tradingagents.value]


def test_create_research_runs_persists_requested_strategy(
    initialized_schema: None, fake_queue: Any
) -> None:
    _ = initialized_schema
    _ = fake_queue
    payload: dict[str, Any] = {
        "tickers": ["AAPL", "MSFT"],
        "trade_date": "2026-05-15",
        "llm_provider": "openai",
        "llm_model": "gpt-4o-mini",
        "strategy": "funnel_research",
    }
    with TestClient(app) as client:
        response = client.post("/api/research-runs", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert {row["strategy"] for row in body} == {Strategy.funnel_research.value}

    import asyncio

    async def _load_strategies() -> list[str]:
        async with session_factory() as session:
            rows = (await session.execute(select(ResearchRun))).scalars().all()
            return sorted(row.strategy for row in rows)

    persisted = asyncio.run(_load_strategies())
    assert persisted == [
        Strategy.funnel_research.value,
        Strategy.funnel_research.value,
    ]


def test_create_research_runs_rejects_unknown_strategy(
    initialized_schema: None, fake_queue: Any
) -> None:
    _ = initialized_schema
    _ = fake_queue
    payload: dict[str, Any] = {
        "tickers": ["AAPL"],
        "trade_date": "2026-05-15",
        "llm_provider": "openai",
        "llm_model": "gpt-4o-mini",
        "strategy": "not_a_real_strategy",
    }
    with TestClient(app) as client:
        response = client.post("/api/research-runs", json=payload)
    assert response.status_code == 422


def test_get_research_run_detail_exposes_strategy(
    initialized_schema: None, fake_queue: Any
) -> None:
    _ = initialized_schema
    _ = fake_queue
    payload: dict[str, Any] = {
        "tickers": ["AAPL"],
        "trade_date": "2026-05-15",
        "llm_provider": "openai",
        "llm_model": "gpt-4o-mini",
        "strategy": "funnel_research",
    }
    with TestClient(app) as client:
        create_response = client.post("/api/research-runs", json=payload)
        assert create_response.status_code == 201
        run_id = create_response.json()[0]["id"]
        detail_response = client.get(f"/api/research-runs/{run_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["strategy"] == Strategy.funnel_research.value
