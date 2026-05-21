from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import select

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

    async def fake_bootstrap() -> None:
        return None

    monkeypatch.setattr(worker_tasks, "_load_strategy", fake_load_strategy)
    monkeypatch.setattr(
        worker_tasks, "_bootstrap_data_sources_for_run", fake_bootstrap
    )

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


@pytest.mark.usefixtures("initialized_schema")
async def test_dispatch_builds_llm_client_with_per_stage_budget_caps_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid4()
    async with session_factory() as session:
        session.add(
            ResearchRun(
                id=run_id,
                ticker="AAPL",
                trade_date=date(2026, 5, 20),
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

    from app.config import Settings

    def _fake_settings() -> Settings:
        return Settings(
            per_stage_budget_caps_usd={
                "belief_update": Decimal("0.50"),
                "synthesize": Decimal("2.00"),
            }
        )

    monkeypatch.setattr(worker_tasks, "get_settings", _fake_settings)

    await worker_tasks._dispatch(run_id)

    llm_client = captured["llm_client"]
    per_stage = llm_client._guard.thresholds.per_stage_usd
    assert per_stage["belief_update"] == Decimal("0.50")
    assert per_stage["synthesize"] == Decimal("2.00")


@pytest.mark.usefixtures("initialized_schema")
async def test_persist_cache_stats_writes_payload_to_research_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy import select

    from app.services.source_clients._request_cache import RequestCache

    run_id = uuid4()
    async with session_factory() as session:
        session.add(
            ResearchRun(
                id=run_id,
                ticker="MSFT",
                trade_date=date(2026, 5, 20),
                strategy=Strategy.funnel_research.value,
                status=RunStatus.running,
                config={},
            )
        )
        await session.commit()

    cache = RequestCache(ttl_seconds=300.0)
    cache._hits = 7  # type: ignore[attr-defined]
    cache._misses = 3  # type: ignore[attr-defined]
    cache._evictions = 1  # type: ignore[attr-defined]

    await worker_tasks._persist_cache_stats(run_id=run_id, request_cache=cache)

    async with session_factory() as session:
        row = (
            await session.execute(
                select(ResearchRun).where(ResearchRun.id == run_id)
            )
        ).scalar_one()
    payload = row.source_client_cache_stats
    assert isinstance(payload, dict)
    assert payload["hits"] == 7
    assert payload["misses"] == 3
    assert payload["evictions"] == 1
    assert payload["hit_rate"] == pytest.approx(0.7)


def test_execute_research_run_rejects_invalid_uuid() -> None:
    with pytest.raises(ValueError):
        worker_tasks.execute_research_run("not-a-uuid")


@pytest.mark.usefixtures("initialized_schema")
async def test_dispatch_fails_run_when_openai_client_construction_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid4()
    async with session_factory() as session:
        session.add(
            ResearchRun(
                id=run_id,
                ticker=None,
                trade_date=date(2026, 5, 19),
                strategy=Strategy.funnel_research.value,
                status=RunStatus.queued,
                config={},
                scope_payload={"kind": "macro", "universe": "us_equities"},
            )
        )
        await session.commit()

    def boom() -> Any:
        raise RuntimeError("openai_api_key is not configured")

    monkeypatch.setattr(worker_tasks, "_build_openai_client", boom)

    async def fake_run_macro_brief(**_: Any) -> None:
        raise AssertionError("run_macro_brief should not be called")

    monkeypatch.setattr(worker_tasks, "run_macro_brief", fake_run_macro_brief)

    await worker_tasks._dispatch(run_id)

    async with session_factory() as session:
        loaded = (
            await session.execute(
                select(ResearchRun).where(ResearchRun.id == run_id)
            )
        ).scalar_one()
        assert loaded.status == RunStatus.failed
        assert loaded.error_message is not None
        assert "openai" in loaded.error_message.lower()


@pytest.mark.usefixtures("initialized_schema")
async def test_dispatch_fails_run_for_unknown_strategy() -> None:
    run_id = uuid4()
    async with session_factory() as session:
        session.add(
            ResearchRun(
                id=run_id,
                ticker=None,
                trade_date=date(2026, 5, 19),
                strategy="experimental_strategy_v9",
                status=RunStatus.queued,
                config={},
            )
        )
        await session.commit()

    await worker_tasks._dispatch(run_id)

    async with session_factory() as session:
        loaded = (
            await session.execute(
                select(ResearchRun).where(ResearchRun.id == run_id)
            )
        ).scalar_one()
        assert loaded.status == RunStatus.failed
        assert loaded.error_message is not None
        assert "experimental_strategy_v9" in loaded.error_message


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
