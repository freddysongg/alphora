"""POST /api/approvals/{id}/approve — token gate + 422 cases."""
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
    *,
    status_val: str = PendingApprovalStatus.pending.value,
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
                status=status_val,
                decided_by=("auto" if status_val != "pending" else None),
                decided_at=(
                    datetime.now(UTC) if status_val != "pending" else None
                ),
                reject_reason=None,
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )
        await session.commit()
    return pending_id


@pytest.mark.asyncio
async def test_approve_503_when_token_unset(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("HUMAN_APPROVAL_TOKEN", "")
    get_settings.cache_clear()
    pending_id = await _seed_pending(session_maker)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/approvals/{pending_id}/approve",
            headers={"X-Human-Token": "anything"},
        )
    assert resp.status_code == 503
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_approve_401_when_missing_or_wrong_header(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("HUMAN_APPROVAL_TOKEN", _GOOD_TOKEN)
    get_settings.cache_clear()
    pending_id = await _seed_pending(session_maker)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.post(f"/api/approvals/{pending_id}/approve")
        wrong = await client.post(
            f"/api/approvals/{pending_id}/approve",
            headers={"X-Human-Token": "wrong"},
        )
    assert missing.status_code == 401
    assert wrong.status_code == 401
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_approve_flips_status_and_records_decided_by(
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
            f"/api/approvals/{pending_id}/approve",
            headers={"X-Human-Token": _GOOD_TOKEN},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["decided_by"] == "human:default"
    assert body["decided_at"] is not None
    async with session_maker() as session:
        row = await session.scalar(
            select(PendingApprovalRow).where(PendingApprovalRow.id == pending_id)
        )
    assert row is not None
    assert row.status == "approved"
    assert row.decided_by == "human:default"
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_approve_422_when_already_decided(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("HUMAN_APPROVAL_TOKEN", _GOOD_TOKEN)
    get_settings.cache_clear()
    pending_id = await _seed_pending(
        session_maker, status_val=PendingApprovalStatus.approved.value
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/approvals/{pending_id}/approve",
            headers={"X-Human-Token": _GOOD_TOKEN},
        )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    # detail may be a dict OR a serialized string depending on FastAPI version;
    # assert "current_status" appears either way.
    assert "current_status" in str(detail)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_approve_404_when_not_found(
    monkeypatch: pytest.MonkeyPatch,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("HUMAN_APPROVAL_TOKEN", _GOOD_TOKEN)
    get_settings.cache_clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/approvals/{uuid.uuid4()}/approve",
            headers={"X-Human-Token": _GOOD_TOKEN},
        )
    assert resp.status_code == 404
    get_settings.cache_clear()
