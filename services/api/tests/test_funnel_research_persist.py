import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_runs import ResearchRun, RunEvent, RunStatus, Strategy
from app.schemas.macro_brief import (
    CitedClaim,
    MacroBrief,
    ProposedHypothesis,
    SectorCall,
    SectorCallDirection,
    Theme,
    VerifierStatus,
    WatchItem,
)
from app.schemas.sector_brief import JudgePublic, JudgeStatus


async def _make_run(session: AsyncSession) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
    )
    session.add(run)
    await session.flush()
    return run.id


@pytest.mark.asyncio
async def test_persist_writes_macro_brief_and_terminal_event(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research._persist import persist_macro_brief

    run_id = await _make_run(db_session)
    chunk_id = uuid.uuid4()
    sector_eid = uuid.uuid4()
    ev_a = uuid.uuid4()
    ev_b = uuid.uuid4()
    brief = MacroBrief(
        themes=[Theme(name="rates", evidence_ids=[ev_a], confidence=0.5)],
        sector_calls=[
            SectorCall(
                sector_entity_id=sector_eid,
                sector_name="Energy",
                direction=SectorCallDirection.overweight,
                conviction=0.5,
                evidence_ids=[ev_b],
            )
        ],
        watch_items=[WatchItem(name="x", reason="y", evidence_ids=[])],
        cited_claims=[
            CitedClaim(claim_text="c", exact_quote="q", chunk_id=chunk_id, source="fred"),
        ],
        proposed_hypotheses=[
            ProposedHypothesis(claim_text="h", scope_entity_ids=[sector_eid], evidence_ids=[]),
        ],
        confidence=0.6,
        evidence_ids=[ev_a, ev_b],
        verifier_status=VerifierStatus.verified,
        regeneration_count=1,
    )

    await persist_macro_brief(
        session=db_session,
        run_id=run_id,
        brief=brief,
        wall_clock_ms=4200,
    )
    await db_session.commit()

    row = (await db_session.execute(select(MacroBriefRow).where(MacroBriefRow.run_id == run_id))).scalar_one()
    assert row.verifier_status == "verified"
    assert row.regeneration_count == 1
    assert set(row.evidence_ids) == {str(ev_a), str(ev_b)}

    run = (await db_session.execute(select(ResearchRun).where(ResearchRun.id == run_id))).scalar_one()
    assert run.status == RunStatus.succeeded
    assert run.wall_clock_ms == 4200

    terminal = (
        await db_session.execute(
            select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.at.desc())
        )
    ).scalars().first()
    assert terminal is not None
    assert terminal.data is not None
    assert terminal.data.get("stage_name") == "succeeded"
    assert terminal.data.get("stage_index") == 9
    assert terminal.data.get("total_stages") == 9


@pytest.mark.asyncio
async def test_persist_does_not_overwrite_cancelled_status(db_session: AsyncSession) -> None:
    """If a run was cancelled while the strategy was finishing, persist the brief but don't reanimate."""
    from app.services.strategies.funnel_research._persist import persist_macro_brief

    run_id = await _make_run(db_session)
    run = (await db_session.execute(select(ResearchRun).where(ResearchRun.id == run_id))).scalar_one()
    run.status = RunStatus.cancelled
    await db_session.commit()

    brief = MacroBrief(
        themes=[],
        sector_calls=[],
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.5,
        evidence_ids=[],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )
    await persist_macro_brief(session=db_session, run_id=run_id, brief=brief, wall_clock_ms=100)
    await db_session.commit()

    loaded = (await db_session.execute(select(ResearchRun).where(ResearchRun.id == run_id))).scalar_one()
    assert loaded.status == RunStatus.cancelled
    row = (await db_session.execute(select(MacroBriefRow).where(MacroBriefRow.run_id == run_id))).scalar_one()
    assert row.verifier_status == "verified"


@pytest.mark.asyncio
async def test_persist_writes_judge_columns_when_provided(
    db_session: AsyncSession,
) -> None:
    from app.services.strategies.funnel_research._persist import persist_macro_brief

    run_id = await _make_run(db_session)
    log = LlmCallLog(
        id=uuid.uuid4(),
        run_id=run_id,
        model="gpt-5-mini",
        prompt_hash="0" * 64,
        input_hash="0" * 64,
        latency_ms=10,
        status=LlmCallStatus.success,
        cost_usd=Decimal("0.001"),
    )
    db_session.add(log)
    await db_session.flush()

    brief = MacroBrief(
        themes=[],
        sector_calls=[],
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.5,
        evidence_ids=[],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )
    judge = JudgePublic(
        status=JudgeStatus.flagged,
        reasons=["contradicts cited evidence"],
        call_id=log.id,
    )
    await persist_macro_brief(
        session=db_session,
        run_id=run_id,
        brief=brief,
        wall_clock_ms=100,
        mark_succeeded=False,
        judge=judge,
    )
    await db_session.commit()

    row = (
        await db_session.execute(
            select(MacroBriefRow).where(MacroBriefRow.run_id == run_id)
        )
    ).scalar_one()
    assert row.judge_status == "flagged"
    assert row.judge_reasons == ["contradicts cited evidence"]
    assert row.judge_call_id == log.id


@pytest.mark.asyncio
async def test_persist_judge_defaults_to_not_run_when_omitted(
    db_session: AsyncSession,
) -> None:
    from app.services.strategies.funnel_research._persist import persist_macro_brief

    run_id = await _make_run(db_session)
    brief = MacroBrief(
        themes=[],
        sector_calls=[],
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.5,
        evidence_ids=[],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )
    await persist_macro_brief(
        session=db_session,
        run_id=run_id,
        brief=brief,
        wall_clock_ms=100,
        mark_succeeded=False,
    )
    await db_session.commit()

    row = (
        await db_session.execute(
            select(MacroBriefRow).where(MacroBriefRow.run_id == run_id)
        )
    ).scalar_one()
    assert row.judge_status == "not_run"
    assert row.judge_reasons is None
    assert row.judge_call_id is None
