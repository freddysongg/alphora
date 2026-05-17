import uuid
from datetime import date
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models_runs import ResearchRun, RunStatus
from app.db.session import session_factory
from app.main import app


def test_create_research_runs_persists_rows_and_enqueues(
    initialized_schema: None, fake_queue: Any
) -> None:
    _ = initialized_schema
    payload: dict[str, Any] = {
        "tickers": ["aapl", "msft"],
        "trade_date": "2026-05-15",
        "llm_provider": "openai",
        "llm_model": "gpt-4o-mini",
        "debate_depth": 3,
    }
    with TestClient(app) as client:
        response = client.post("/api/research-runs", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2
    tickers_returned = {row["ticker"] for row in body}
    assert tickers_returned == {"AAPL", "MSFT"}
    for row in body:
        assert row["status"] == "queued"
        assert "id" in row
    assert len(fake_queue.calls) == 2
    enqueue_args = [call[0] for call in fake_queue.calls]
    assert enqueue_args[0][0] == "app.workers.tasks.execute_research_run"


def test_list_research_runs_returns_recent_first(
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
        create_response = client.post("/api/research-runs", json=payload)
        assert create_response.status_code == 201
        list_response = client.get("/api/research-runs")
    assert list_response.status_code == 200
    runs = list_response.json()
    assert len(runs) == 1
    assert runs[0]["ticker"] == "AAPL"
    assert runs[0]["status"] == "queued"


def test_get_research_run_returns_detail_with_nested_arrays(
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
        create_response = client.post("/api/research-runs", json=payload)
        run_id = create_response.json()[0]["id"]
        detail_response = client.get(f"/api/research-runs/{run_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["ticker"] == "AAPL"
    assert detail["status"] == "queued"
    assert detail["reports"] == []
    assert detail["events"] == []
    assert detail["provenance"] == []
    assert detail["config"]["llm_provider"] == "openai"


def test_get_research_run_returns_404_when_missing(initialized_schema: None) -> None:
    _ = initialized_schema
    missing_id = uuid.uuid4()
    with TestClient(app) as client:
        response = client.get(f"/api/research-runs/{missing_id}")
    assert response.status_code == 404


def test_list_research_runs_filters_by_status(
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
        client.post("/api/research-runs", json=payload)
        no_match = client.get("/api/research-runs", params={"status": "succeeded"})
        match = client.get("/api/research-runs", params={"status": "queued"})
    assert no_match.status_code == 200
    assert no_match.json() == []
    assert match.status_code == 200
    assert len(match.json()) == 1


def test_list_research_runs_grouped_view(
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
        client.post("/api/research-runs", json=payload)
        grouped = client.get("/api/research-runs", params={"group": "status"})
    assert grouped.status_code == 200
    body = grouped.json()
    assert set(body.keys()) == {"queued", "running", "recent", "failed"}
    assert len(body["queued"]) == 1


def test_cancel_research_run_marks_cancelled(
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
        create_response = client.post("/api/research-runs", json=payload)
        run_id = create_response.json()[0]["id"]
        cancel_response = client.post(f"/api/research-runs/{run_id}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"


def test_cancel_research_run_returns_409_when_already_terminal(
    initialized_schema: None,
) -> None:
    _ = initialized_schema

    async def _seed_succeeded_run() -> uuid.UUID:
        run = ResearchRun(
            id=uuid.uuid4(),
            ticker="AAPL",
            trade_date=date(2026, 5, 15),
            status=RunStatus.succeeded,
            config={},
        )
        async with session_factory() as session:
            session.add(run)
            await session.commit()
        return run.id

    import asyncio

    run_id = asyncio.run(_seed_succeeded_run())
    with TestClient(app) as client:
        response = client.post(f"/api/research-runs/{run_id}/cancel")
    assert response.status_code == 409


def test_cancel_research_run_returns_404_when_missing(initialized_schema: None) -> None:
    _ = initialized_schema
    missing_id = uuid.uuid4()
    with TestClient(app) as client:
        response = client.post(f"/api/research-runs/{missing_id}/cancel")
    assert response.status_code == 404


def test_create_research_runs_rejects_empty_tickers(initialized_schema: None) -> None:
    _ = initialized_schema
    payload: dict[str, Any] = {
        "tickers": [],
        "trade_date": "2026-05-15",
        "llm_provider": "openai",
        "llm_model": "gpt-4o-mini",
    }
    with TestClient(app) as client:
        response = client.post("/api/research-runs", json=payload)
    assert response.status_code == 422


def test_create_research_runs_actually_persists(
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
    assert response.status_code == 201

    import asyncio

    async def _count_rows() -> int:
        async with session_factory() as session:
            rows = (await session.execute(select(ResearchRun))).scalars().all()
            return len(rows)

    assert asyncio.run(_count_rows()) == 1


def _seed_run_with_status(run_status: RunStatus) -> uuid.UUID:
    import asyncio

    async def _seed() -> uuid.UUID:
        run = ResearchRun(
            id=uuid.uuid4(),
            ticker="AAPL",
            trade_date=date(2026, 5, 15),
            status=run_status,
            config={},
        )
        async with session_factory() as session:
            session.add(run)
            await session.commit()
        return run.id

    return asyncio.run(_seed())


def test_resume_research_run_returns_404_when_missing(
    initialized_schema: None, fake_queue: Any
) -> None:
    _ = initialized_schema
    _ = fake_queue
    missing_id = uuid.uuid4()
    with TestClient(app) as client:
        response = client.post(f"/api/research-runs/{missing_id}/resume")
    assert response.status_code == 404


def test_resume_research_run_returns_409_when_not_paused(
    initialized_schema: None, fake_queue: Any
) -> None:
    _ = initialized_schema
    run_id = _seed_run_with_status(RunStatus.queued)
    with TestClient(app) as client:
        response = client.post(f"/api/research-runs/{run_id}/resume")
    assert response.status_code == 409
    assert len(fake_queue.calls) == 0


def test_resume_paused_run_returns_queued_and_enqueues(
    initialized_schema: None, fake_queue: Any
) -> None:
    _ = initialized_schema
    run_id = _seed_run_with_status(RunStatus.paused)
    with TestClient(app) as client:
        response = client.post(f"/api/research-runs/{run_id}/resume")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert len(fake_queue.calls) == 1
    args, _kwargs = fake_queue.calls[0]
    assert args[0] == "app.workers.tasks.execute_research_run"
    assert args[1] == run_id.hex


def test_cancel_paused_run_transitions_to_cancelled(
    initialized_schema: None, fake_queue: Any
) -> None:
    _ = initialized_schema
    _ = fake_queue
    run_id = _seed_run_with_status(RunStatus.paused)
    with TestClient(app) as client:
        response = client.post(f"/api/research-runs/{run_id}/cancel")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
