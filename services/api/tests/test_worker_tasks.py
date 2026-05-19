from datetime import date
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.db.session import session_factory
from app.workers import tasks as worker_tasks


def test_execute_research_run_invokes_orchestrator_with_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeOrchestrator:
        def __init__(self, *, session_factory: Any, adapter: Any) -> None:
            captured["session_factory"] = session_factory
            captured["adapter"] = adapter

        async def execute(self, run_id: Any) -> None:
            captured["run_id"] = run_id

        async def fail(self, run_id: Any, reason: str) -> None:
            captured["failed_run_id"] = run_id
            captured["fail_reason"] = reason

    monkeypatch.setattr(worker_tasks, "RunOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(worker_tasks, "TradingAgentsAdapter", MagicMock())

    async def fake_load_strategy(_run_id: Any) -> str:
        return Strategy.tradingagents.value

    monkeypatch.setattr(worker_tasks, "_load_strategy", fake_load_strategy)

    run_id = uuid4()
    worker_tasks.execute_research_run(run_id.hex)

    assert captured["run_id"] == run_id
    assert captured["session_factory"] is session_factory
    assert captured["adapter"] is not None
    assert "failed_run_id" not in captured


@pytest.mark.usefixtures("initialized_schema")
async def test_execute_research_run_dispatches_funnel_research(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid4()
    async with session_factory() as session:
        session.add(
            ResearchRun(
                id=run_id,
                ticker="AAPL",
                trade_date=date(2026, 5, 16),
                strategy=Strategy.funnel_research.value,
                status=RunStatus.queued,
                config={},
            )
        )
        await session.commit()

    captured: dict[str, Any] = {}

    async def fake_run_macro_brief(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(worker_tasks, "run_macro_brief", fake_run_macro_brief)
    monkeypatch.setattr(
        worker_tasks, "_build_openai_client", lambda: MagicMock()
    )

    await worker_tasks._dispatch(run_id)

    assert captured["run_id"] == run_id
    assert captured["session_factory"] is session_factory
    assert "llm_client" in captured
    assert "orchestrator" in captured
    assert "http_client" in captured


def test_execute_research_run_rejects_invalid_uuid() -> None:
    with pytest.raises(ValueError):
        worker_tasks.execute_research_run("not-a-uuid")


def test_get_run_queue_returns_queue_named_constant(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.workers import queue as queue_module

    captured_urls: list[str] = []

    class FakeRedis:
        @classmethod
        def from_url(cls, url: str) -> "FakeRedis":
            captured_urls.append(url)
            return cls()

    monkeypatch.setattr(queue_module, "Redis", FakeRedis)

    result = queue_module.get_run_queue()

    assert result.name == queue_module.RESEARCH_RUN_QUEUE
    assert captured_urls, "expected Redis.from_url to be invoked"
