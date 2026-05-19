import json
import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.budget import BudgetAction, BudgetDecision, TokenUsage
from app.schemas.macro_brief import MacroBriefScope
from app.services.llm.client import (
    BudgetKilledError,
    BudgetPausedError,
    LlmCompletionResult,
)


def _fake_brief_json() -> str:
    return json.dumps(
        {
            "themes": [],
            "sector_calls": [],
            "watch_items": [],
            "cited_claims": [],
            "proposed_hypotheses": [],
            "confidence": 0.5,
            "evidence_ids": [],
            "verifier_status": "verified",
            "regeneration_count": 0,
        }
    )


def _decision(action: BudgetAction, reason: str) -> BudgetDecision:
    return BudgetDecision(
        action=action,
        reason=reason,
        run_cost_usd=Decimal("0"),
        daily_cost_usd=Decimal("0"),
        threshold_crossed=None,
    )


@pytest.mark.asyncio
async def test_llm_call_returns_parsed_macro_brief(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research._llm_call import call_synthesis

    async def fake_complete(**kwargs: Any) -> LlmCompletionResult:
        return LlmCompletionResult(
            content=_fake_brief_json(),
            model="gpt-5-mini",
            usage=TokenUsage(input_tokens=1, output_tokens=1, cached_input_tokens=0, reasoning_tokens=0),
            cost_usd=Decimal("0.001"),
            latency_ms=10,
            log_id=uuid.uuid4(),
        )

    async def fake_pause(**kwargs: Any) -> None:
        raise AssertionError("pause should not be called")

    async def fake_fail(**kwargs: Any) -> None:
        raise AssertionError("fail should not be called")

    brief = await call_synthesis(
        session=db_session,
        run_id=uuid.uuid4(),
        scope=MacroBriefScope(kind="macro", universe="us_equities"),
        digest_markdown="",
        chunks=[],
        sector_entity_ids={"Energy": uuid.uuid4()},
        llm_complete=fake_complete,
        orchestrator_pause=fake_pause,
        orchestrator_fail=fake_fail,
        evidence_ids=[],
        regeneration_feedback=None,
    )
    assert brief.confidence == 0.5
    assert brief.verifier_status.value == "verified"


@pytest.mark.asyncio
async def test_llm_call_routes_pause_via_orchestrator(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research import FunnelResearchError
    from app.services.strategies.funnel_research._llm_call import call_synthesis

    pause_calls: list[str] = []

    async def fake_complete(**kwargs: Any) -> LlmCompletionResult:
        raise BudgetPausedError(_decision(BudgetAction.pause, "paused"))

    async def fake_pause(*, run_id: uuid.UUID, reason: str) -> None:
        pause_calls.append(reason)

    async def fake_fail(*, run_id: uuid.UUID, reason: str) -> None:
        raise AssertionError("fail should not be called")

    with pytest.raises(FunnelResearchError):
        await call_synthesis(
            session=db_session,
            run_id=uuid.uuid4(),
            scope=MacroBriefScope(kind="macro", universe="us_equities"),
            digest_markdown="",
            chunks=[],
            sector_entity_ids={"Energy": uuid.uuid4()},
            llm_complete=fake_complete,
            orchestrator_pause=fake_pause,
            orchestrator_fail=fake_fail,
            evidence_ids=[],
            regeneration_feedback=None,
        )
    assert pause_calls and pause_calls[0] == "paused"


@pytest.mark.asyncio
async def test_llm_call_routes_kill_via_orchestrator(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research import FunnelResearchError
    from app.services.strategies.funnel_research._llm_call import call_synthesis

    fail_calls: list[str] = []

    async def fake_complete(**kwargs: Any) -> LlmCompletionResult:
        raise BudgetKilledError(_decision(BudgetAction.kill, "killed"))

    async def fake_pause(*, run_id: uuid.UUID, reason: str) -> None:
        raise AssertionError("pause should not be called")

    async def fake_fail(*, run_id: uuid.UUID, reason: str) -> None:
        fail_calls.append(reason)

    with pytest.raises(FunnelResearchError):
        await call_synthesis(
            session=db_session,
            run_id=uuid.uuid4(),
            scope=MacroBriefScope(kind="macro", universe="us_equities"),
            digest_markdown="",
            chunks=[],
            sector_entity_ids={"Energy": uuid.uuid4()},
            llm_complete=fake_complete,
            orchestrator_pause=fake_pause,
            orchestrator_fail=fake_fail,
            evidence_ids=[],
            regeneration_feedback=None,
        )
    assert fail_calls and fail_calls[0] == "killed"


@pytest.mark.asyncio
async def test_llm_call_invalid_json_raises_funnel_error(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research import FunnelResearchError
    from app.services.strategies.funnel_research._llm_call import call_synthesis

    async def fake_complete(**kwargs: Any) -> LlmCompletionResult:
        return LlmCompletionResult(
            content="not json",
            model="gpt-5-mini",
            usage=TokenUsage(),
            cost_usd=Decimal("0"),
            latency_ms=0,
            log_id=uuid.uuid4(),
        )

    async def fake_pause(**kwargs: Any) -> None:
        return None

    async def fake_fail(**kwargs: Any) -> None:
        return None

    with pytest.raises(FunnelResearchError):
        await call_synthesis(
            session=db_session,
            run_id=uuid.uuid4(),
            scope=MacroBriefScope(kind="macro", universe="us_equities"),
            digest_markdown="",
            chunks=[],
            sector_entity_ids={"Energy": uuid.uuid4()},
            llm_complete=fake_complete,
            orchestrator_pause=fake_pause,
            orchestrator_fail=fake_fail,
            evidence_ids=[],
            regeneration_feedback=None,
        )
