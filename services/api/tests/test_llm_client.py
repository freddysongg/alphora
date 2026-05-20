from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select

from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_runs import ResearchRun, RunEvent, RunEventLevel, RunStatus
from app.db.session import session_factory
from app.schemas.budget import BudgetAction, BudgetThresholds
from app.services.budget import BudgetGuard
from app.services.llm import (
    BudgetKilledError,
    BudgetPausedError,
    LlmClient,
    LlmMessage,
)
from app.services.model_pricing import UnknownModelError


def _fake_response(
    *,
    content: str = "ok",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    cached_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=content)),
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            prompt_tokens_details=SimpleNamespace(cached_tokens=cached_tokens),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning_tokens),
        ),
    )


class _FakeChatCompletions:
    def __init__(self, response: Any) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _FakeOpenAi:
    def __init__(self, response: Any) -> None:
        self.chat = SimpleNamespace(completions=_FakeChatCompletions(response))


async def _seed_run() -> UUID:
    async with session_factory() as session:
        run = ResearchRun(
            ticker="AAPL",
            trade_date=date(2026, 5, 16),
            status=RunStatus.running,
            config={},
        )
        session.add(run)
        await session.commit()
        return run.id


@pytest.mark.usefixtures("initialized_schema")
async def test_complete_returns_result_and_logs_call_on_success() -> None:
    run_id = await _seed_run()
    fake = _FakeOpenAi(_fake_response(prompt_tokens=1000, completion_tokens=500))
    client = LlmClient(openai_client=fake)  # type: ignore[arg-type]

    async with session_factory() as session:
        result = await client.complete(
            session=session,
            messages=[LlmMessage(role="user", content="hello")],
            model="gpt-5",
            run_id=run_id,
            evidence_ids=["ev_1", "ev_2"],
        )

    assert result.content == "ok"
    assert result.model == "gpt-5"
    assert result.usage.input_tokens == 1000
    assert result.usage.output_tokens == 500
    assert result.cost_usd > Decimal("0")
    assert result.log_id is not None

    async with session_factory() as session:
        logs = (await session.execute(select(LlmCallLog))).scalars().all()
        assert len(logs) == 1
        log = logs[0]
        assert log.status is LlmCallStatus.success
        assert log.cost_usd == result.cost_usd
        assert len(log.prompt_hash) == 64
        assert len(log.input_hash) == 64
        assert log.evidence_ids == ["ev_1", "ev_2"]
        assert log.budget_action == BudgetAction.allow.value

        events = (
            await session.execute(select(RunEvent).where(RunEvent.run_id == run_id))
        ).scalars().all()
        assert len(events) == 1
        event = events[0]
        assert event.level is RunEventLevel.info
        assert event.data is not None
        assert event.data["event"] == "cost"
        assert event.data["budget_action"] == BudgetAction.allow.value
        assert event.data["log_id"] == str(log.id)


@pytest.mark.usefixtures("initialized_schema")
async def test_complete_extracts_cached_and_reasoning_tokens() -> None:
    run_id = await _seed_run()
    fake = _FakeOpenAi(
        _fake_response(
            prompt_tokens=1000,
            completion_tokens=50,
            cached_tokens=200,
            reasoning_tokens=300,
        )
    )
    client = LlmClient(openai_client=fake)  # type: ignore[arg-type]

    async with session_factory() as session:
        result = await client.complete(
            session=session,
            messages=[LlmMessage(role="user", content="hello")],
            model="gpt-5",
            run_id=run_id,
        )

    assert result.usage.input_tokens == 1000
    assert result.usage.output_tokens == 50
    assert result.usage.cached_input_tokens == 200
    assert result.usage.reasoning_tokens == 300

    async with session_factory() as session:
        log = (await session.execute(select(LlmCallLog))).scalars().one()
        assert log.input_tokens == 1000
        assert log.output_tokens == 50
        assert log.cached_input_tokens == 200
        assert log.reasoning_tokens == 300


@pytest.mark.usefixtures("initialized_schema")
async def test_complete_pause_threshold_raises_budget_paused_error() -> None:
    run_id = await _seed_run()
    fake = _FakeOpenAi(
        _fake_response(prompt_tokens=1_000_000, completion_tokens=1_000_000)
    )
    guard = BudgetGuard(
        BudgetThresholds(
            soft_run_usd=Decimal("0.001"),
            hard_run_usd=Decimal("0.002"),
            catastrophic_run_usd=Decimal("100"),
            daily_usd=Decimal("500"),
        )
    )
    client = LlmClient(openai_client=fake, budget_guard=guard)  # type: ignore[arg-type]

    with pytest.raises(BudgetPausedError) as exc_info:
        async with session_factory() as session:
            await client.complete(
                session=session,
                messages=[LlmMessage(role="user", content="hello")],
                model="gpt-5",
                run_id=run_id,
            )

    assert exc_info.value.decision.action is BudgetAction.pause

    async with session_factory() as session:
        logs = (await session.execute(select(LlmCallLog))).scalars().all()
        assert len(logs) == 1
        assert logs[0].status is LlmCallStatus.budget_paused
        assert logs[0].budget_action == BudgetAction.pause.value

        events = (
            await session.execute(select(RunEvent).where(RunEvent.run_id == run_id))
        ).scalars().all()
        assert len(events) == 1
        assert events[0].level is RunEventLevel.warn
        assert events[0].data is not None
        assert events[0].data["budget_action"] == BudgetAction.pause.value
        assert events[0].data["log_id"] == str(logs[0].id)


@pytest.mark.usefixtures("initialized_schema")
async def test_complete_kill_threshold_raises_budget_killed_error() -> None:
    run_id = await _seed_run()
    fake = _FakeOpenAi(
        _fake_response(prompt_tokens=1_000_000, completion_tokens=1_000_000)
    )
    guard = BudgetGuard(
        BudgetThresholds(
            soft_run_usd=Decimal("0.001"),
            hard_run_usd=Decimal("0.002"),
            catastrophic_run_usd=Decimal("0.005"),
            daily_usd=Decimal("500"),
        )
    )
    client = LlmClient(openai_client=fake, budget_guard=guard)  # type: ignore[arg-type]

    with pytest.raises(BudgetKilledError) as exc_info:
        async with session_factory() as session:
            await client.complete(
                session=session,
                messages=[LlmMessage(role="user", content="hello")],
                model="gpt-5",
                run_id=run_id,
            )

    assert exc_info.value.decision.action is BudgetAction.kill

    async with session_factory() as session:
        logs = (await session.execute(select(LlmCallLog))).scalars().all()
        assert len(logs) == 1
        assert logs[0].status is LlmCallStatus.budget_killed
        assert logs[0].budget_action == BudgetAction.kill.value

        events = (
            await session.execute(select(RunEvent).where(RunEvent.run_id == run_id))
        ).scalars().all()
        assert len(events) == 1
        assert events[0].data is not None
        assert events[0].data["budget_action"] == BudgetAction.kill.value
        assert events[0].data["log_id"] == str(logs[0].id)


@pytest.mark.usefixtures("initialized_schema")
async def test_complete_hashes_are_stable_across_identical_inputs() -> None:
    run_id = await _seed_run()
    messages = [LlmMessage(role="user", content="same prompt")]

    fake1 = _FakeOpenAi(_fake_response())
    client1 = LlmClient(openai_client=fake1)  # type: ignore[arg-type]
    async with session_factory() as session:
        await client1.complete(
            session=session, messages=messages, model="gpt-5", run_id=run_id
        )

    fake2 = _FakeOpenAi(_fake_response())
    client2 = LlmClient(openai_client=fake2)  # type: ignore[arg-type]
    async with session_factory() as session:
        await client2.complete(
            session=session, messages=messages, model="gpt-5", run_id=run_id
        )

    fake3 = _FakeOpenAi(_fake_response())
    client3 = LlmClient(openai_client=fake3)  # type: ignore[arg-type]
    async with session_factory() as session:
        await client3.complete(
            session=session, messages=messages, model="gpt-5-mini", run_id=run_id
        )

    async with session_factory() as session:
        logs = (
            await session.execute(select(LlmCallLog).order_by(LlmCallLog.created_at))
        ).scalars().all()
        assert len(logs) == 3
        assert logs[0].prompt_hash == logs[1].prompt_hash
        assert logs[0].input_hash == logs[1].input_hash
        assert logs[0].prompt_hash == logs[2].prompt_hash
        assert logs[0].input_hash != logs[2].input_hash


@pytest.mark.usefixtures("initialized_schema")
async def test_complete_openai_error_persists_error_log_and_reraises() -> None:
    run_id = await _seed_run()
    fake = _FakeOpenAi(RuntimeError("upstream timeout"))
    client = LlmClient(openai_client=fake)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="upstream timeout"):
        async with session_factory() as session:
            await client.complete(
                session=session,
                messages=[LlmMessage(role="user", content="hello")],
                model="gpt-5",
                run_id=run_id,
            )

    async with session_factory() as session:
        logs = (await session.execute(select(LlmCallLog))).scalars().all()
        assert len(logs) == 1
        log = logs[0]
        assert log.status is LlmCallStatus.error
        assert log.error_message is not None
        assert "upstream timeout" in log.error_message
        assert log.input_tokens == 0
        assert log.output_tokens == 0
        assert log.cached_input_tokens == 0
        assert log.reasoning_tokens == 0
        assert log.cost_usd == Decimal("0")


@pytest.mark.usefixtures("initialized_schema")
async def test_complete_without_run_id_logs_call_but_emits_no_event() -> None:
    fake = _FakeOpenAi(_fake_response())
    client = LlmClient(openai_client=fake)  # type: ignore[arg-type]

    async with session_factory() as session:
        await client.complete(
            session=session,
            messages=[LlmMessage(role="user", content="hello")],
            model="gpt-5",
            run_id=None,
        )

    async with session_factory() as session:
        logs = (await session.execute(select(LlmCallLog))).scalars().all()
        assert len(logs) == 1
        assert logs[0].run_id is None

        events = (await session.execute(select(RunEvent))).scalars().all()
        assert len(events) == 0


@pytest.mark.usefixtures("initialized_schema")
async def test_complete_daily_cost_accumulates_across_calls() -> None:
    run_id = await _seed_run()

    async with session_factory() as session:
        prior = LlmCallLog(
            run_id=run_id,
            model="gpt-5",
            prompt_hash="a" * 64,
            input_hash="b" * 64,
            input_tokens=0,
            output_tokens=0,
            cached_input_tokens=0,
            reasoning_tokens=0,
            cost_usd=Decimal("4.99"),
            latency_ms=10,
            status=LlmCallStatus.success,
            created_at=datetime.now(UTC),
        )
        session.add(prior)
        await session.commit()

    fake = _FakeOpenAi(_fake_response(prompt_tokens=80_000, completion_tokens=0))
    guard = BudgetGuard(
        BudgetThresholds(
            soft_run_usd=Decimal("5.00"),
            hard_run_usd=Decimal("20.00"),
            catastrophic_run_usd=Decimal("100.00"),
            daily_usd=Decimal("500.00"),
        )
    )
    client = LlmClient(openai_client=fake, budget_guard=guard)  # type: ignore[arg-type]

    async with session_factory() as session:
        result = await client.complete(
            session=session,
            messages=[LlmMessage(role="user", content="hello")],
            model="gpt-5",
            run_id=run_id,
        )

    assert result.cost_usd == Decimal("0.100000")

    async with session_factory() as session:
        new_logs = (
            await session.execute(
                select(LlmCallLog)
                .where(LlmCallLog.run_id == run_id)
                .where(LlmCallLog.cost_usd == Decimal("0.100000"))
            )
        ).scalars().all()
        assert len(new_logs) == 1
        assert new_logs[0].status is LlmCallStatus.success
        assert new_logs[0].budget_action == BudgetAction.warn.value

        events = (
            await session.execute(select(RunEvent).where(RunEvent.run_id == run_id))
        ).scalars().all()
        assert len(events) == 1
        assert events[0].data is not None
        assert events[0].data["budget_action"] == BudgetAction.warn.value
        assert events[0].data["log_id"] == str(new_logs[0].id)


@pytest.mark.usefixtures("initialized_schema")
async def test_complete_unknown_model_logs_error_and_does_not_call_openai() -> None:
    run_id = await _seed_run()
    fake = _FakeOpenAi(_fake_response())
    client = LlmClient(openai_client=fake)  # type: ignore[arg-type]

    with pytest.raises(UnknownModelError):
        async with session_factory() as session:
            await client.complete(
                session=session,
                messages=[LlmMessage(role="user", content="hello")],
                model="unknown-model-xyz",
                run_id=run_id,
            )

    assert fake.chat.completions.calls == []

    async with session_factory() as session:
        logs = (await session.execute(select(LlmCallLog))).scalars().all()
        assert len(logs) == 1
        log = logs[0]
        assert log.status is LlmCallStatus.error
        assert log.cost_usd == Decimal("0")
        assert log.latency_ms == 0
        assert log.error_message is not None
        assert "unknown-model-xyz" in log.error_message


@pytest.mark.usefixtures("initialized_schema")
async def test_complete_handles_response_with_no_usage_field() -> None:
    run_id = await _seed_run()
    response = _fake_response()
    response.usage = None
    client = LlmClient(openai_client=_FakeOpenAi(response))  # type: ignore[arg-type]

    async with session_factory() as session:
        result = await client.complete(
            session=session,
            messages=[LlmMessage(role="user", content="hi")],
            model="gpt-5",
            run_id=run_id,
        )

    assert result.usage.input_tokens == 0
    assert result.usage.output_tokens == 0
    assert result.cost_usd == Decimal("0.000000")

    async with session_factory() as session:
        logs = (
            await session.execute(
                select(LlmCallLog).where(LlmCallLog.run_id == run_id)
            )
        ).scalars().all()
        assert len(logs) == 1
        assert logs[0].status is LlmCallStatus.success
        assert logs[0].input_tokens == 0
        assert logs[0].output_tokens == 0
