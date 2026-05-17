import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_runs import ResearchRun, RunEvent, RunEventLevel, RunStatus
from app.db.session import session_factory
from app.main import app
from app.services.run_events import COST_EVENT


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


async def _seed_succeeded_run_with_cost_event() -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker="AAPL",
        trade_date=date(2026, 5, 15),
        status=RunStatus.succeeded,
        config={},
    )
    async with session_factory() as session:
        session.add(run)
        await session.flush()
        session.add(
            RunEvent(
                run_id=run.id,
                level=RunEventLevel.info,
                message="llm call cost $0.05",
                data={"event": COST_EVENT, "model": "gpt-5", "cost_usd": "0.05"},
            )
        )
        await session.commit()
    return run.id


async def test_sse_stream_includes_data_field_for_cost_events(
    initialized_schema: None,
) -> None:
    _ = initialized_schema
    from app.api.routes.research_runs import _stream_run_events

    run_id = await _seed_succeeded_run_with_cost_event()

    payloads: list[dict[str, Any]] = []
    async for frame in _stream_run_events(run_id):
        for line in frame.splitlines():
            if line.startswith("data: "):
                payloads.append(json.loads(line[len("data: "):]))

    cost_payloads = [
        p
        for p in payloads
        if isinstance(p.get("data"), dict) and p["data"].get("event") == COST_EVENT
    ]
    assert len(cost_payloads) == 1
    cost_payload = cost_payloads[0]
    assert cost_payload["level"] == "info"
    assert cost_payload["message"] == "llm call cost $0.05"
    assert cost_payload["data"]["model"] == "gpt-5"
    assert cost_payload["data"]["cost_usd"] == "0.05"


async def _seed_succeeded_run_with_null_data_event() -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker="AAPL",
        trade_date=date(2026, 5, 15),
        status=RunStatus.succeeded,
        config={},
    )
    async with session_factory() as session:
        session.add(run)
        await session.flush()
        session.add(
            RunEvent(
                run_id=run.id,
                level=RunEventLevel.info,
                message="event without data",
                data=None,
            )
        )
        await session.commit()
    return run.id


async def test_sse_stream_serializes_null_data_field(
    initialized_schema: None,
) -> None:
    _ = initialized_schema
    from app.api.routes.research_runs import _stream_run_events

    run_id = await _seed_succeeded_run_with_null_data_event()

    payloads: list[dict[str, Any]] = []
    async for frame in _stream_run_events(run_id):
        for line in frame.splitlines():
            if line.startswith("data: "):
                payloads.append(json.loads(line[len("data: "):]))

    null_data_payloads = [
        p for p in payloads if p.get("message") == "event without data"
    ]
    assert len(null_data_payloads) == 1
    assert null_data_payloads[0]["data"] is None


async def _seed_run(ticker: str = "AAPL") -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=ticker,
        trade_date=date(2026, 5, 15),
        status=RunStatus.queued,
        config={},
    )
    async with session_factory() as session:
        session.add(run)
        await session.commit()
    return run.id


async def _insert_llm_call(
    run_id: uuid.UUID | None,
    *,
    created_at: datetime | None = None,
    model: str = "gpt-5",
    prompt_hash: str | None = None,
    input_hash: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_input_tokens: int = 0,
    reasoning_tokens: int = 0,
    cost_usd: Decimal = Decimal("0"),
    latency_ms: int = 0,
    call_status: LlmCallStatus = LlmCallStatus.success,
    evidence_ids: list[str] | None = None,
) -> uuid.UUID:
    log = LlmCallLog(
        id=uuid.uuid4(),
        run_id=run_id,
        model=model,
        prompt_hash=prompt_hash or ("a" * 64),
        input_hash=input_hash or ("b" * 64),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
        reasoning_tokens=reasoning_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        status=call_status,
        evidence_ids=evidence_ids,
    )
    if created_at is not None:
        log.created_at = created_at
    async with session_factory() as session:
        session.add(log)
        await session.commit()
    return log.id


def test_list_llm_calls_returns_404_for_unknown_run(initialized_schema: None) -> None:
    _ = initialized_schema
    missing_id = uuid.uuid4()
    with TestClient(app) as client:
        response = client.get(f"/api/research-runs/{missing_id}/llm-calls")
    assert response.status_code == 404
    assert response.json()["detail"] == "research run not found"


async def test_list_llm_calls_returns_empty_for_run_without_calls(
    initialized_schema: None,
) -> None:
    _ = initialized_schema
    run_id = await _seed_run()
    with TestClient(app) as client:
        response = client.get(f"/api/research-runs/{run_id}/llm-calls")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_llm_calls_returns_logs_for_run_only(
    initialized_schema: None,
) -> None:
    _ = initialized_schema
    run_a_id = await _seed_run(ticker="AAPL")
    run_b_id = await _seed_run(ticker="MSFT")
    await _insert_llm_call(run_a_id)
    await _insert_llm_call(run_b_id)
    await _insert_llm_call(run_b_id)
    with TestClient(app) as client:
        response = client.get(f"/api/research-runs/{run_b_id}/llm-calls")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    for row in body:
        assert row["run_id"] == str(run_b_id)


async def test_list_llm_calls_paginates(initialized_schema: None) -> None:
    _ = initialized_schema
    run_id = await _seed_run()
    base_dt = datetime(2026, 5, 15, 12, 0, 0, tzinfo=UTC)
    for i in range(5):
        await _insert_llm_call(run_id, created_at=base_dt + timedelta(seconds=i))
    with TestClient(app) as client:
        page_one = client.get(
            f"/api/research-runs/{run_id}/llm-calls",
            params={"limit": 2, "offset": 0},
        )
        page_two = client.get(
            f"/api/research-runs/{run_id}/llm-calls",
            params={"limit": 2, "offset": 2},
        )
        page_three = client.get(
            f"/api/research-runs/{run_id}/llm-calls",
            params={"limit": 2, "offset": 4},
        )
    assert page_one.status_code == 200
    assert page_two.status_code == 200
    assert page_three.status_code == 200
    page_one_body = page_one.json()
    page_two_body = page_two.json()
    page_three_body = page_three.json()
    assert len(page_one_body) == 2
    assert len(page_two_body) == 2
    assert len(page_three_body) == 1
    page_one_timestamps = [row["created_at"] for row in page_one_body]
    page_two_timestamps = [row["created_at"] for row in page_two_body]
    assert page_one_timestamps == sorted(page_one_timestamps, reverse=True)
    assert page_two_timestamps == sorted(page_two_timestamps, reverse=True)
    assert page_one_timestamps[-1] > page_two_timestamps[0]
    assert page_two_timestamps[-1] > page_three_body[0]["created_at"]


async def test_list_llm_calls_returns_call_fields_correctly(
    initialized_schema: None,
) -> None:
    _ = initialized_schema
    run_id = await _seed_run()
    log_id = await _insert_llm_call(
        run_id,
        model="gpt-5",
        prompt_hash="a" * 64,
        input_hash="b" * 64,
        input_tokens=100,
        output_tokens=50,
        cached_input_tokens=10,
        reasoning_tokens=5,
        cost_usd=Decimal("0.001234"),
        latency_ms=500,
        call_status=LlmCallStatus.success,
        evidence_ids=["e1", "e2"],
    )
    with TestClient(app) as client:
        response = client.get(f"/api/research-runs/{run_id}/llm-calls")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    row = body[0]
    assert row["id"] == str(log_id)
    assert row["run_id"] == str(run_id)
    assert row["model"] == "gpt-5"
    assert row["prompt_hash"] == "a" * 64
    assert row["input_hash"] == "b" * 64
    assert row["input_tokens"] == 100
    assert row["output_tokens"] == 50
    assert row["cached_input_tokens"] == 10
    assert row["reasoning_tokens"] == 5
    assert Decimal(row["cost_usd"]) == Decimal("0.001234")
    assert row["latency_ms"] == 500
    assert row["status"] == "success"
    assert row["evidence_ids"] == ["e1", "e2"]
    assert row["error_message"] is None
    assert "created_at" in row
