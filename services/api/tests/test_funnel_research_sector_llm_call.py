import json
import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.budget import TokenUsage
from app.schemas.macro_brief import (
    MacroBrief,
    SectorCall,
    SectorCallDirection,
    VerifierStatus,
)
from app.services.llm.client import (
    BudgetKilledError,
    BudgetPausedError,
    LlmCompletionResult,
)
from app.services.strategies.funnel_research._errors import FunnelResearchError
from app.services.strategies.funnel_research.sector.llm_call import (
    call_sector_synthesis,
)


def _sector_brief_json(sector_entity_id: uuid.UUID) -> str:
    return json.dumps(
        {
            "sector_entity_id": str(sector_entity_id),
            "sector_name": "Information Technology",
            "direction": "overweight",
            "themes": [],
            "companies": [],
            "watch_items": [],
            "cited_claims": [],
            "confidence": 0.7,
            "verifier_status": "verified",
            "regeneration_count": 0,
        }
    )


def _macro_brief() -> MacroBrief:
    return MacroBrief(
        themes=[],
        sector_calls=[],
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.7,
        evidence_ids=[],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


def _sector_call(sector_entity_id: uuid.UUID) -> SectorCall:
    return SectorCall(
        sector_entity_id=sector_entity_id,
        sector_name="Information Technology",
        direction=SectorCallDirection.overweight,
        conviction=0.85,
        evidence_ids=[],
    )


@pytest.mark.asyncio
async def test_call_sector_synthesis_returns_parsed_brief(
    db_session: AsyncSession,
) -> None:
    sector_entity_id = uuid.uuid4()

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        return LlmCompletionResult(
            content=_sector_brief_json(sector_entity_id),
            model="gpt-5-mini",
            usage=TokenUsage(input_tokens=1, output_tokens=1),
            cost_usd=Decimal("0.001"),
            latency_ms=12,
            log_id=uuid.uuid4(),
        )

    async def fake_pause(**_: Any) -> None:
        raise AssertionError("pause should not be called")

    async def fake_fail(**_: Any) -> None:
        raise AssertionError("fail should not be called")

    brief = await call_sector_synthesis(
        session=db_session,
        run_id=uuid.uuid4(),
        macro_brief=_macro_brief(),
        sector_call=_sector_call(sector_entity_id),
        digest_markdown="",
        chunks=[],
        evidence_ids=[],
        llm_complete=fake_complete,
        orchestrator_pause=fake_pause,
        orchestrator_fail=fake_fail,
        regeneration_feedback=None,
    )

    assert brief.sector_name == "Information Technology"
    assert brief.direction is SectorCallDirection.overweight
    assert brief.confidence == 0.7


@pytest.mark.asyncio
async def test_call_sector_synthesis_pause_raises_funnel_error(
    db_session: AsyncSession,
) -> None:
    sector_entity_id = uuid.uuid4()

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        from app.schemas.budget import BudgetAction, BudgetDecision

        raise BudgetPausedError(
            BudgetDecision(
                action=BudgetAction.pause,
                reason="soft cap",
                run_cost_usd=Decimal("5"),
                daily_cost_usd=Decimal("5"),
                threshold_crossed=None,
            )
        )

    pause_calls: list[dict[str, Any]] = []

    async def fake_pause(**kwargs: Any) -> None:
        pause_calls.append(kwargs)

    async def fake_fail(**_: Any) -> None:
        raise AssertionError("fail should not be called")

    with pytest.raises(FunnelResearchError) as info:
        await call_sector_synthesis(
            session=db_session,
            run_id=uuid.uuid4(),
            macro_brief=_macro_brief(),
            sector_call=_sector_call(sector_entity_id),
            digest_markdown="",
            chunks=[],
            evidence_ids=[],
            llm_complete=fake_complete,
            orchestrator_pause=fake_pause,
            orchestrator_fail=fake_fail,
            regeneration_feedback=None,
        )

    assert "Information Technology" in str(info.value)
    assert len(pause_calls) == 1


@pytest.mark.asyncio
async def test_call_sector_synthesis_kill_raises_funnel_error(
    db_session: AsyncSession,
) -> None:
    sector_entity_id = uuid.uuid4()

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        from app.schemas.budget import BudgetAction, BudgetDecision

        raise BudgetKilledError(
            BudgetDecision(
                action=BudgetAction.kill,
                reason="catastrophic",
                run_cost_usd=Decimal("100"),
                daily_cost_usd=Decimal("500"),
                threshold_crossed=None,
            )
        )

    fail_calls: list[dict[str, Any]] = []

    async def fake_pause(**_: Any) -> None:
        raise AssertionError("pause should not be called")

    async def fake_fail(**kwargs: Any) -> None:
        fail_calls.append(kwargs)

    with pytest.raises(FunnelResearchError):
        await call_sector_synthesis(
            session=db_session,
            run_id=uuid.uuid4(),
            macro_brief=_macro_brief(),
            sector_call=_sector_call(sector_entity_id),
            digest_markdown="",
            chunks=[],
            evidence_ids=[],
            llm_complete=fake_complete,
            orchestrator_pause=fake_pause,
            orchestrator_fail=fake_fail,
            regeneration_feedback=None,
        )

    assert len(fail_calls) == 1


@pytest.mark.asyncio
async def test_call_sector_synthesis_invalid_json_raises_funnel_error(
    db_session: AsyncSession,
) -> None:
    sector_entity_id = uuid.uuid4()

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        return LlmCompletionResult(
            content="not json",
            model="gpt-5-mini",
            usage=TokenUsage(input_tokens=1, output_tokens=1),
            cost_usd=Decimal("0.001"),
            latency_ms=10,
            log_id=uuid.uuid4(),
        )

    async def fake_pause(**_: Any) -> None:
        raise AssertionError("pause should not be called")

    async def fake_fail(**_: Any) -> None:
        raise AssertionError("fail should not be called")

    with pytest.raises(FunnelResearchError) as info:
        await call_sector_synthesis(
            session=db_session,
            run_id=uuid.uuid4(),
            macro_brief=_macro_brief(),
            sector_call=_sector_call(sector_entity_id),
            digest_markdown="",
            chunks=[],
            evidence_ids=[],
            llm_complete=fake_complete,
            orchestrator_pause=fake_pause,
            orchestrator_fail=fake_fail,
            regeneration_feedback=None,
        )

    assert "non-JSON" in str(info.value)
