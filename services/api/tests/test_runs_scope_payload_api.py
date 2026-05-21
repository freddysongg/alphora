import asyncio
import uuid
from datetime import date
from typing import Any

from fastapi.testclient import TestClient

from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.db.session import session_factory
from app.main import app


def test_create_funnel_run_echoes_scope_payload_on_summary(
    initialized_schema: None, fake_queue: Any
) -> None:
    _ = initialized_schema
    _ = fake_queue
    payload: dict[str, Any] = {
        "strategy": "funnel_research",
        "trade_date": "2026-05-19",
        "scope_payload": {"kind": "macro", "universe": "us_equities"},
    }
    with TestClient(app) as client:
        response = client.post("/api/research-runs", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert len(body) == 1
    summary = body[0]
    assert summary["strategy"] == "funnel_research"
    assert summary["scope_payload"] == {"kind": "macro", "universe": "us_equities"}
    assert summary["ticker"] is None


def test_get_funnel_run_returns_scope_payload_on_detail(
    initialized_schema: None, fake_queue: Any
) -> None:
    _ = initialized_schema
    _ = fake_queue
    payload: dict[str, Any] = {
        "strategy": "funnel_research",
        "trade_date": "2026-05-19",
        "scope_payload": {"kind": "macro", "universe": "us_equities"},
    }
    with TestClient(app) as client:
        create_response = client.post("/api/research-runs", json=payload)
        run_id = create_response.json()[0]["id"]
        detail_response = client.get(f"/api/research-runs/{run_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["scope_payload"] == {"kind": "macro", "universe": "us_equities"}
    assert detail["strategy"] == "funnel_research"


def test_list_runs_includes_scope_payload_per_row(
    initialized_schema: None, fake_queue: Any
) -> None:
    _ = initialized_schema
    _ = fake_queue
    funnel_payload: dict[str, Any] = {
        "strategy": "funnel_research",
        "trade_date": "2026-05-19",
        "scope_payload": {"kind": "macro", "universe": "us_equities"},
    }

    async def _seed_tradingagents_row() -> None:
        async with session_factory() as session:
            session.add(
                ResearchRun(
                    id=uuid.uuid4(),
                    ticker="AAPL",
                    trade_date=date(2026, 5, 19),
                    strategy=Strategy.tradingagents.value,
                    status=RunStatus.queued,
                    config={},
                )
            )
            await session.commit()

    with TestClient(app) as client:
        funnel_response = client.post("/api/research-runs", json=funnel_payload)
        assert funnel_response.status_code == 201, funnel_response.text
        asyncio.run(_seed_tradingagents_row())
        list_response = client.get("/api/research-runs")
    assert list_response.status_code == 200
    rows = list_response.json()
    by_strategy = {row["strategy"]: row for row in rows}
    assert by_strategy["funnel_research"]["scope_payload"] == {
        "kind": "macro",
        "universe": "us_equities",
    }
    assert by_strategy["tradingagents"]["scope_payload"] is None
