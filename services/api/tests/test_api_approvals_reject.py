"""POST /api/approvals/{id}/reject — token gate + reject_reason + 422."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_approval import PendingApprovalRow, PendingApprovalStatus
from app.db.models_strategy_runner import (
    StrategyRun,
    StrategyRunMode,
    StrategyRunStatus,
)
from app.main import app

_GOOD_TOKEN = "the-real-token-32chars-ok-xxxxxx"


async def _seed_pending(
    session_maker: async_sessionmaker[AsyncSession],
) -> uuid.UUID:
    run_id = uuid.uuid4()
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
            PendingApprovalRow(
                id=pending_id,
                run_id=run_id,
                judge_verdict_id=None,
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
    return pending_id


@pytest.mark.asyncio
async def test_reject_persists_reason(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("HUMAN_APPROVAL_TOKEN", _GOOD_TOKEN)
    get_settings.cache_clear()
    pending_id = await _seed_pending(session_maker)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/approvals/{pending_id}/reject",
            headers={"X-Human-Token": _GOOD_TOKEN},
            json={"reject_reason": "thesis weakened by latest filing"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["reject_reason"] == "thesis weakened by latest filing"
    async with session_maker() as session:
        row = await session.scalar(
            select(PendingApprovalRow).where(PendingApprovalRow.id == pending_id)
        )
    assert row is not None
    assert row.status == "rejected"
    assert row.reject_reason == "thesis weakened by latest filing"
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_reject_without_reason_persists_null(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("HUMAN_APPROVAL_TOKEN", _GOOD_TOKEN)
    get_settings.cache_clear()
    pending_id = await _seed_pending(session_maker)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/approvals/{pending_id}/reject",
            headers={"X-Human-Token": _GOOD_TOKEN},
            json={},
        )
    assert resp.status_code == 200
    assert resp.json()["reject_reason"] is None
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_reject_401_when_token_missing(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("HUMAN_APPROVAL_TOKEN", _GOOD_TOKEN)
    get_settings.cache_clear()
    pending_id = await _seed_pending(session_maker)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/approvals/{pending_id}/reject",
            json={"reject_reason": "no"},
        )
    assert resp.status_code == 401
    get_settings.cache_clear()
