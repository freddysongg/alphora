import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.budget import BudgetAction, BudgetDecision, TokenUsage
from app.services.llm import (
    BudgetKilledError,
    BudgetPausedError,
    LlmCompletionResult,
    LlmMessage,
)


@pytest.fixture()
async def populated_session(initialized_schema: None) -> AsyncIterator[AsyncSession]:
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


def _decision(action: BudgetAction, reason: str) -> BudgetDecision:
    return BudgetDecision(
        action=action,
        reason=reason,
        run_cost_usd=Decimal("0"),
        daily_cost_usd=Decimal("0"),
        threshold_crossed=None,
    )


def _completion_result(content: str) -> LlmCompletionResult:
    return LlmCompletionResult(
        content=content,
        model="gpt-4o-mini-2024-07-18",
        usage=TokenUsage(),
        cost_usd=Decimal("0"),
        latency_ms=0,
        log_id=uuid.uuid4(),
    )


async def test_call_llm_for_extraction_returns_completion_result(
    populated_session: AsyncSession,
) -> None:
    from app.services.extraction._llm_call import call_llm_for_extraction

    captured_kwargs: dict[str, Any] = {}

    async def fake_complete(**kwargs: Any) -> LlmCompletionResult:
        captured_kwargs.update(kwargs)
        return _completion_result("{}")

    async def fake_pause(**_: Any) -> None:
        return None

    async def fake_fail(**_: Any) -> None:
        return None

    response = await call_llm_for_extraction(
        session=populated_session,
        run_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        chunk_text="hello world",
        evidence_id=uuid.uuid4(),
        llm_complete=fake_complete,
        orchestrator_pause=fake_pause,
        orchestrator_fail=fake_fail,
    )

    assert response.content == "{}"
    assert response.model == "gpt-4o-mini-2024-07-18"


async def test_call_llm_for_extraction_passes_messages_as_llm_message_instances(
    populated_session: AsyncSession,
) -> None:
    from app.services.extraction._llm_call import call_llm_for_extraction

    captured_kwargs: dict[str, Any] = {}

    async def fake_complete(**kwargs: Any) -> LlmCompletionResult:
        captured_kwargs.update(kwargs)
        return _completion_result("{}")

    await call_llm_for_extraction(
        session=populated_session,
        run_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        chunk_text="hello",
        evidence_id=uuid.uuid4(),
        llm_complete=fake_complete,
        orchestrator_pause=lambda **_: _async_none(),
        orchestrator_fail=lambda **_: _async_none(),
    )

    messages = captured_kwargs["messages"]
    assert all(isinstance(m, LlmMessage) for m in messages)
    assert messages[0].role == "system"
    assert messages[-1].role == "user"


async def test_call_llm_for_extraction_passes_evidence_ids_as_strings(
    populated_session: AsyncSession,
) -> None:
    from app.services.extraction._llm_call import call_llm_for_extraction

    captured_kwargs: dict[str, Any] = {}
    evidence_id = uuid.uuid4()

    async def fake_complete(**kwargs: Any) -> LlmCompletionResult:
        captured_kwargs.update(kwargs)
        return _completion_result("{}")

    await call_llm_for_extraction(
        session=populated_session,
        run_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        chunk_text="hello",
        evidence_id=evidence_id,
        llm_complete=fake_complete,
        orchestrator_pause=lambda **_: _async_none(),
        orchestrator_fail=lambda **_: _async_none(),
    )

    assert captured_kwargs["evidence_ids"] == [str(evidence_id)]


async def test_call_llm_for_extraction_passes_extraction_model(
    populated_session: AsyncSession,
) -> None:
    from app.services.extraction._llm_call import call_llm_for_extraction
    from app.services.extraction.config import EXTRACTION_MODEL

    captured_kwargs: dict[str, Any] = {}

    async def fake_complete(**kwargs: Any) -> LlmCompletionResult:
        captured_kwargs.update(kwargs)
        return _completion_result("{}")

    await call_llm_for_extraction(
        session=populated_session,
        run_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        chunk_text="hello",
        evidence_id=uuid.uuid4(),
        llm_complete=fake_complete,
        orchestrator_pause=lambda **_: _async_none(),
        orchestrator_fail=lambda **_: _async_none(),
    )

    assert captured_kwargs["model"] == EXTRACTION_MODEL


async def test_call_llm_routes_budget_paused_to_orchestrator_pause(
    populated_session: AsyncSession,
) -> None:
    from app.services.extraction._llm_call import (
        ExtractionBudgetHaltError,
        call_llm_for_extraction,
    )

    pause_calls: list[dict[str, Any]] = []
    fail_calls: list[dict[str, Any]] = []

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        raise BudgetPausedError(_decision(BudgetAction.pause, "soft limit"))

    async def fake_pause(**kwargs: Any) -> None:
        pause_calls.append(kwargs)

    async def fake_fail(**kwargs: Any) -> None:
        fail_calls.append(kwargs)

    run_id = uuid.uuid4()
    with pytest.raises(ExtractionBudgetHaltError) as exc_info:
        await call_llm_for_extraction(
            session=populated_session,
            run_id=run_id,
            chunk_id=uuid.uuid4(),
            chunk_text="hello",
            evidence_id=uuid.uuid4(),
            llm_complete=fake_complete,
            orchestrator_pause=fake_pause,
            orchestrator_fail=fake_fail,
        )

    assert "paused" in str(exc_info.value).lower()
    assert len(pause_calls) == 1
    assert pause_calls[0]["run_id"] == run_id
    assert "soft limit" in pause_calls[0]["reason"]
    assert fail_calls == []


async def test_call_llm_routes_budget_killed_to_orchestrator_fail(
    populated_session: AsyncSession,
) -> None:
    from app.services.extraction._llm_call import (
        ExtractionBudgetHaltError,
        call_llm_for_extraction,
    )

    fail_calls: list[dict[str, Any]] = []
    pause_calls: list[dict[str, Any]] = []

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        raise BudgetKilledError(_decision(BudgetAction.kill, "catastrophic"))

    async def fake_pause(**kwargs: Any) -> None:
        pause_calls.append(kwargs)

    async def fake_fail(**kwargs: Any) -> None:
        fail_calls.append(kwargs)

    run_id = uuid.uuid4()
    with pytest.raises(ExtractionBudgetHaltError) as exc_info:
        await call_llm_for_extraction(
            session=populated_session,
            run_id=run_id,
            chunk_id=uuid.uuid4(),
            chunk_text="hello",
            evidence_id=uuid.uuid4(),
            llm_complete=fake_complete,
            orchestrator_pause=fake_pause,
            orchestrator_fail=fake_fail,
        )

    assert "killed" in str(exc_info.value).lower()
    assert len(fail_calls) == 1
    assert fail_calls[0]["run_id"] == run_id
    assert "catastrophic" in fail_calls[0]["reason"]
    assert pause_calls == []


async def test_call_llm_preserves_budget_exception_as_cause(
    populated_session: AsyncSession,
) -> None:
    from app.services.extraction._llm_call import (
        ExtractionBudgetHaltError,
        call_llm_for_extraction,
    )

    paused = BudgetPausedError(_decision(BudgetAction.pause, "x"))

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        raise paused

    async def noop(**_: Any) -> None:
        return None

    with pytest.raises(ExtractionBudgetHaltError) as exc_info:
        await call_llm_for_extraction(
            session=populated_session,
            run_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            chunk_text="x",
            evidence_id=uuid.uuid4(),
            llm_complete=fake_complete,
            orchestrator_pause=noop,
            orchestrator_fail=noop,
        )

    assert exc_info.value.__cause__ is paused


async def _async_none() -> None:
    return None
