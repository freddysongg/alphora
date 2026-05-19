import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_runs import (
    ResearchRun,
    RunEvent,
    RunEventLevel,
    RunStatus,
    Strategy,
)
from app.schemas.budget import TokenUsage
from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import (
    MacroBrief,
    SectorCall,
    SectorCallDirection,
    VerifierStatus,
)
from app.schemas.sector_brief import (
    JudgeStatus,
    SectorBrief,
)
from app.services.llm.client import LlmCompletionResult
from app.services.strategies.funnel_research._judge import run_judge


async def _noop_pause(**_: Any) -> None:
    return None


async def _noop_fail(**_: Any) -> None:
    return None


async def _seed_run(session: AsyncSession) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 19),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.commit()
    return run.id


def _macro_brief() -> MacroBrief:
    return MacroBrief(
        themes=[],
        sector_calls=[
            SectorCall(
                sector_entity_id=uuid.uuid4(),
                sector_name="Energy",
                direction=SectorCallDirection.overweight,
                conviction=0.7,
                evidence_ids=[],
            )
        ],
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.6,
        evidence_ids=[],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


def _sector_brief() -> SectorBrief:
    return SectorBrief(
        sector_entity_id=uuid.uuid4(),
        sector_name="Information Technology",
        direction=SectorCallDirection.overweight,
        themes=[],
        companies=[],
        watch_items=[],
        cited_claims=[],
        confidence=0.7,
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


def _completion(content: str, log_id: uuid.UUID | None = None) -> LlmCompletionResult:
    return LlmCompletionResult(
        content=content,
        model="gpt-5-mini",
        usage=TokenUsage(input_tokens=10, output_tokens=5),
        cost_usd=Decimal("0.001"),
        latency_ms=10,
        log_id=log_id or uuid.uuid4(),
    )


@pytest.mark.asyncio
async def test_run_judge_passes_returns_public(db_session: AsyncSession) -> None:
    run_id = await _seed_run(db_session)
    log_id = uuid.uuid4()

    async def llm(**_: Any) -> LlmCompletionResult:
        return _completion(
            json.dumps({"status": "passed", "reasons": []}), log_id=log_id
        )

    outcome = await run_judge(
        session=db_session,
        run_id=run_id,
        brief=_macro_brief(),
        brief_kind="macro",
        chunks=[],
        llm_complete=llm,
        orchestrator_pause=_noop_pause,
        orchestrator_fail=_noop_fail,
    )
    assert outcome.public.status is JudgeStatus.passed
    assert outcome.public.reasons == []
    assert outcome.public.call_id == log_id
    assert outcome.regenerate_reasons == []


@pytest.mark.asyncio
async def test_run_judge_flagged_includes_reasons(db_session: AsyncSession) -> None:
    run_id = await _seed_run(db_session)

    async def llm(**_: Any) -> LlmCompletionResult:
        return _completion(
            json.dumps(
                {"status": "flagged", "reasons": ["contradicts cited evidence"]}
            )
        )

    outcome = await run_judge(
        session=db_session,
        run_id=run_id,
        brief=_sector_brief(),
        brief_kind="sector",
        chunks=[],
        llm_complete=llm,
        orchestrator_pause=_noop_pause,
        orchestrator_fail=_noop_fail,
    )
    assert outcome.public.status is JudgeStatus.flagged
    assert outcome.public.reasons == ["contradicts cited evidence"]
    assert outcome.regenerate_reasons == ["contradicts cited evidence"]


@pytest.mark.asyncio
async def test_run_judge_llm_error_returns_not_run_and_warns(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)

    async def llm(**_: Any) -> LlmCompletionResult:
        raise RuntimeError("llm down")

    outcome = await run_judge(
        session=db_session,
        run_id=run_id,
        brief=_macro_brief(),
        brief_kind="macro",
        chunks=[],
        llm_complete=llm,
        orchestrator_pause=_noop_pause,
        orchestrator_fail=_noop_fail,
    )
    assert outcome.public.status is JudgeStatus.not_run
    assert outcome.public.call_id is None
    events = (
        await db_session.execute(
            select(RunEvent).where(RunEvent.level == RunEventLevel.warn)
        )
    ).scalars().all()
    assert any(
        isinstance(event.data, dict)
        and event.data.get("event") == "judge_failure"
        for event in events
    )


@pytest.mark.asyncio
async def test_run_judge_unparseable_output_returns_not_run(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)

    async def llm(**_: Any) -> LlmCompletionResult:
        return _completion("not valid json")

    outcome = await run_judge(
        session=db_session,
        run_id=run_id,
        brief=_macro_brief(),
        brief_kind="macro",
        chunks=[],
        llm_complete=llm,
        orchestrator_pause=_noop_pause,
        orchestrator_fail=_noop_fail,
    )
    assert outcome.public.status is JudgeStatus.not_run


@pytest.mark.asyncio
async def test_run_judge_rejects_invalid_status(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)

    async def llm(**_: Any) -> LlmCompletionResult:
        return _completion(json.dumps({"status": "uncertain", "reasons": []}))

    outcome = await run_judge(
        session=db_session,
        run_id=run_id,
        brief=_macro_brief(),
        brief_kind="macro",
        chunks=[],
        llm_complete=llm,
        orchestrator_pause=_noop_pause,
        orchestrator_fail=_noop_fail,
    )
    assert outcome.public.status is JudgeStatus.not_run


@pytest.mark.asyncio
async def test_run_judge_with_chunks_includes_them_in_prompt(
    db_session: AsyncSession,
) -> None:
    run_id = await _seed_run(db_session)
    received_messages: list[Any] = []

    async def llm(**kwargs: Any) -> LlmCompletionResult:
        received_messages.append(kwargs.get("messages"))
        return _completion(json.dumps({"status": "passed", "reasons": []}))

    chunks = [
        EvidenceChunkRef(
            chunk_id=uuid.uuid4(),
            evidence_id=uuid.uuid4(),
            chunk_index=0,
            text="distinctive marker string",
            attributes={"source": "tiingo_news"},
        )
    ]

    await run_judge(
        session=db_session,
        run_id=run_id,
        brief=_macro_brief(),
        brief_kind="macro",
        chunks=chunks,
        llm_complete=llm,
        orchestrator_pause=_noop_pause,
        orchestrator_fail=_noop_fail,
    )

    assert received_messages, "judge should call the llm"
    rendered = "".join(m.content for m in received_messages[0])
    assert "distinctive marker string" in rendered


@pytest.mark.asyncio
async def test_run_judge_budget_pause_routes_to_orchestrator_and_raises(
    db_session: AsyncSession,
) -> None:
    from app.schemas.budget import BudgetAction, BudgetDecision
    from app.services.llm.client import BudgetPausedError
    from app.services.strategies.funnel_research._errors import FunnelResearchError

    run_id = await _seed_run(db_session)
    pause_calls: list[dict[str, Any]] = []
    fail_calls: list[dict[str, Any]] = []

    async def llm(**_: Any) -> LlmCompletionResult:
        raise BudgetPausedError(
            BudgetDecision(
                action=BudgetAction.pause,
                reason="soft cap",
                run_cost_usd=Decimal("5"),
                daily_cost_usd=Decimal("5"),
                threshold_crossed=None,
            )
        )

    async def pause(**kwargs: Any) -> None:
        pause_calls.append(kwargs)

    async def fail(**kwargs: Any) -> None:
        fail_calls.append(kwargs)

    with pytest.raises(FunnelResearchError):
        await run_judge(
            session=db_session,
            run_id=run_id,
            brief=_macro_brief(),
            brief_kind="macro",
            chunks=[],
            llm_complete=llm,
            orchestrator_pause=pause,
            orchestrator_fail=fail,
        )

    assert len(pause_calls) == 1
    assert pause_calls[0]["run_id"] == run_id
    assert fail_calls == []


@pytest.mark.asyncio
async def test_run_judge_budget_kill_routes_to_orchestrator_and_raises(
    db_session: AsyncSession,
) -> None:
    from app.schemas.budget import BudgetAction, BudgetDecision
    from app.services.llm.client import BudgetKilledError
    from app.services.strategies.funnel_research._errors import FunnelResearchError

    run_id = await _seed_run(db_session)
    pause_calls: list[dict[str, Any]] = []
    fail_calls: list[dict[str, Any]] = []

    async def llm(**_: Any) -> LlmCompletionResult:
        raise BudgetKilledError(
            BudgetDecision(
                action=BudgetAction.kill,
                reason="hard cap",
                run_cost_usd=Decimal("100"),
                daily_cost_usd=Decimal("500"),
                threshold_crossed=None,
            )
        )

    async def pause(**kwargs: Any) -> None:
        pause_calls.append(kwargs)

    async def fail(**kwargs: Any) -> None:
        fail_calls.append(kwargs)

    with pytest.raises(FunnelResearchError):
        await run_judge(
            session=db_session,
            run_id=run_id,
            brief=_macro_brief(),
            brief_kind="macro",
            chunks=[],
            llm_complete=llm,
            orchestrator_pause=pause,
            orchestrator_fail=fail,
        )

    assert pause_calls == []
    assert len(fail_calls) == 1
    assert fail_calls[0]["run_id"] == run_id
