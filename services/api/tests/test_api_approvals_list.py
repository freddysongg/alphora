"""GET /api/approvals — filter by status + mode."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_approval import PendingApprovalRow, PendingApprovalStatus
from app.db.models_strategy_runner import (
    StrategyRun,
    StrategyRunMode,
    StrategyRunStatus,
)
from app.main import app


async def _seed(session_maker: async_sessionmaker[AsyncSession]) -> list[uuid.UUID]:
    run_id = uuid.uuid4()
    pending_id = uuid.uuid4()
    approved_id = uuid.uuid4()
    paper_id = uuid.uuid4()
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
        for row_id, status, mode in [
            (pending_id, PendingApprovalStatus.pending.value, "live"),
            (approved_id, PendingApprovalStatus.approved.value, "live"),
            (paper_id, PendingApprovalStatus.approved.value, "paper"),
        ]:
            session.add(
                PendingApprovalRow(
                    id=row_id,
                    run_id=run_id,
                    judge_verdict_id=None,
                    strategy_key="macd_rsi_adx",
                    ticker="SPY",
                    side="buy",
                    qty=Decimal("1"),
                    estimated_fill_price=Decimal("100"),
                    mode=mode,
                    status=status,
                    decided_by=("auto" if status == "approved" else None),
                    decided_at=(datetime.now(UTC) if status == "approved" else None),
                    reject_reason=None,
                    expires_at=(
                        datetime.now(UTC) + timedelta(minutes=5)
                        if status == "pending"
                        else None
                    ),
                )
            )
        await session.commit()
    return [pending_id, approved_id, paper_id]


@pytest.mark.asyncio
async def test_list_pending_live_only(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    pending_id, _, _ = await _seed(session_maker)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/approvals", params={"status": "pending", "mode": "live"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == str(pending_id)
    assert body[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_list_default_returns_all(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(session_maker)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/approvals")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


@pytest.mark.asyncio
async def test_list_by_mode_only(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, paper_id = await _seed(session_maker)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/approvals", params={"mode": "paper"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == str(paper_id)
