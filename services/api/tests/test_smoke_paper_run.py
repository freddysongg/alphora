"""Smoke test for app.scripts.smoke_paper_run.

Runs the script entry against a test database session and asserts that:
  - strategy_runs gets exactly one row,
  - judge_verdicts gets at least one row,
  - pending_approvals gets at least one row with status=approved + decided_by=auto.

We do NOT pin exact counts beyond `>=1` because the stub broker emits a fixed
5 bars; the strategy's evaluate may emit 0..N signals depending on internal
state, so the contract is "at least one signal made it through".
"""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_approval import PendingApprovalRow
from app.db.models_judge import JudgeVerdictRow
from app.db.models_strategy_runner import StrategyRun
from app.scripts.smoke_paper_run import run_smoke


@pytest.mark.asyncio
async def test_smoke_paper_run_populates_phase7_tables(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    summary = await run_smoke(
        session_factory=session_maker,
        ticker="SPY",
        bar_count=5,
    )

    assert summary.strategy_runs == 1
    assert summary.judge_verdicts >= 1
    assert summary.pending_approvals >= 1

    async with session_maker() as session:
        runs = (await session.execute(select(StrategyRun))).scalars().all()
        verdicts = (await session.execute(select(JudgeVerdictRow))).scalars().all()
        approvals = (await session.execute(select(PendingApprovalRow))).scalars().all()

    assert len(runs) == 1
    assert all(v.run_id == runs[0].id for v in verdicts)
    assert all(a.mode == "paper" for a in approvals)
    assert all(a.status == "approved" for a in approvals)
    assert all(a.decided_by == "auto" for a in approvals)


@pytest.mark.asyncio
async def test_smoke_paper_run_is_idempotent_on_watchlist(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    from app.db.models_market import Watchlist

    first = await run_smoke(
        session_factory=session_maker, ticker="SPY", bar_count=5
    )
    second = await run_smoke(
        session_factory=session_maker, ticker="SPY", bar_count=5
    )
    assert first.strategy_runs == 1
    assert second.strategy_runs == 2

    async with session_maker() as session:
        watchlists = (
            await session.execute(
                select(Watchlist).where(Watchlist.name == "demo-paper-SPY")
            )
        ).scalars().all()
    assert len(watchlists) == 1
