from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

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

    monkeypatch.setattr(worker_tasks, "RunOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(worker_tasks, "TradingAgentsAdapter", MagicMock())

    run_id = uuid4()
    worker_tasks.execute_research_run(run_id.hex)

    assert captured["run_id"] == run_id
    assert captured["session_factory"] is session_factory
    assert captured["adapter"] is not None


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
