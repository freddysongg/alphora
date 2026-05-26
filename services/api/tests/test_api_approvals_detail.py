"""GET /api/approvals/{id} surfaces the row + linked judge verdict."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_approval import PendingApprovalRow, PendingApprovalStatus
from app.db.models_judge import JudgeDecisionDb, JudgeVerdictRow
from app.db.models_strategy_runner import (
    StrategyRun,
    StrategyRunMode,
    StrategyRunStatus,
)
from app.main import app


@pytest.mark.asyncio
async def test_detail_surfaces_judge_verdict_when_linked(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = uuid.uuid4()
    verdict_id = uuid.uuid4()
    pending_id = uuid.uuid4()
    async with session_maker() as session:
        session.add(
            StrategyRun(
                id=run_id,
                strategy_key="macd_rsi_adx",
                ticker="SPY",
                mode=StrategyRunMode.live.value,
                status=StrategyRunStatus.running.value,
                params={},
            )
        )
        await session.flush()
        session.add(
            JudgeVerdictRow(
                id=verdict_id,
                run_id=run_id,
                bar_ts=datetime(2026, 5, 25, 14, 30, tzinfo=UTC),
                ticker="SPY",
                strategy_key="macd_rsi_adx",
                side="buy",
                proposed_qty=Decimal("1"),
                decision=JudgeDecisionDb.approve.value,
                size_multiplier=None,
                reasoning_md="thesis is strong",
                context_payload={"active_hypotheses": []},
                llm_model="gpt-4o-mini",
                prompt_version="v1",
                llm_call_log_id=None,
            )
        )
        await session.flush()
        session.add(
            PendingApprovalRow(
                id=pending_id,
                run_id=run_id,
                judge_verdict_id=verdict_id,
                strategy_key="macd_rsi_adx",
                ticker="SPY",
                side="buy",
                qty=Decimal("1"),
                estimated_fill_price=Decimal("100"),
                mode="live",
                status=PendingApprovalStatus.pending.value,
                decided_by=None,
                decided_at=None,
                reject_reason=None,
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )
        await session.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/approvals/{pending_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(pending_id)
    assert body["judge_verdict"] is not None
    assert body["judge_verdict"]["id"] == str(verdict_id)
    assert body["judge_verdict"]["reasoning_md"] == "thesis is strong"
    assert body["judge_verdict"]["context_payload"] == {"active_hypotheses": []}


@pytest.mark.asyncio
async def test_detail_judge_verdict_null_when_unlinked(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = uuid.uuid4()
    pending_id = uuid.uuid4()
    async with session_maker() as session:
        session.add(
            StrategyRun(
                id=run_id,
                strategy_key="macd_rsi_adx",
                ticker="SPY",
                mode=StrategyRunMode.paper.value,
                status=StrategyRunStatus.running.value,
                params={},
            )
        )
        await session.flush()
        session.add(
            PendingApprovalRow(
                id=pending_id,
                run_id=run_id,
                judge_verdict_id=None,
                strategy_key="macd_rsi_adx",
                ticker="SPY",
                side="buy",
                qty=Decimal("1"),
                estimated_fill_price=Decimal("100"),
                mode="paper",
                status=PendingApprovalStatus.approved.value,
                decided_by="auto",
                decided_at=datetime.now(UTC),
                reject_reason=None,
                expires_at=None,
            )
        )
        await session.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/approvals/{pending_id}")
    assert resp.status_code == 200
    assert resp.json()["judge_verdict"] is None


@pytest.mark.asyncio
async def test_detail_404_when_not_found(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/approvals/{uuid.uuid4()}")
    assert resp.status_code == 404
